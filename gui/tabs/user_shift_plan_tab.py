# gui/tabs/user_shift_plan_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
import calendar

# --- Hier sind die korrigierten Importe ---
from database.db_shifts import (
    get_shifts_for_month, get_daily_shift_counts_for_month,
    get_ordered_shift_abbrevs, save_shift_entry
)
from database.db_requests import (
    get_wunschfrei_requests_for_month, submit_user_request,
    get_wunschfrei_requests_by_user_for_month, get_wunschfrei_request_by_user_and_date,
    withdraw_wunschfrei_request, get_all_vacation_requests_for_month,
    user_respond_to_request, get_wunschfrei_request_by_id
)
from database.db_users import get_ordered_users_for_schedule
# --- Ende der Korrektur ---

from gui.request_lock_manager import RequestLockManager
from gui.request_config_manager import RequestConfigManager
from gui.dialogs.custom_messagebox import CustomMessagebox
from gui.tooltip import Tooltip


class UserShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app  # app ist MainUserWindow
        self.grid_widgets = {}
        self.tooltips = {}
        self.shifts = {}
        self.wunschfrei_data = {}
        self.processed_vacations = {}
        self.setup_ui()

        # HINWEIS: Das User-Tab nutzt (im Gegensatz zum Admin-Tab) nicht den
        # vorgeladenen DataManager (P5), sondern lädt Daten (noch) direkt.
        # Der Preloader (P1, P4) lädt jedoch im Hintergrund in den P5-Cache.
        # Wenn der User blättert, wird der *nächste* Monat vorgeladen.

        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def _process_vacations(self, year, month):
        raw_vacations = get_all_vacation_requests_for_month(year, month)
        processed = {}
        for req in raw_vacations:
            user_id_str = str(req['user_id'])
            if user_id_str not in processed:
                processed[user_id_str] = {}

            try:
                start = datetime.strptime(req['start_date'], '%Y-%m-%d').date()
                end = datetime.strptime(req['end_date'], '%Y-%m-%d').date()

                current_date = start
                while current_date <= end:
                    if current_date.year == year and current_date.month == month:
                        processed[user_id_str][current_date] = req['status']
                    current_date += timedelta(days=1)
            except (ValueError, TypeError):
                continue
        return processed

    def setup_ui(self):
        main_view_container = ttk.Frame(self, padding="10")
        main_view_container.pack(fill="both", expand=True)
        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(nav_frame, text="< Voriger Monat", command=self.show_previous_month).pack(side="left")
        self.month_label_var = tk.StringVar()

        # --- NEU: Monats-Label klickbar gemacht (für Dialog) ---
        self.month_label = ttk.Label(nav_frame, textvariable=self.month_label_var,
                                     font=("Segoe UI", 14, "bold"),
                                     anchor="center", cursor="hand2")
        self.month_label.pack(side="left", expand=True, fill="x")
        self.month_label.bind("<Button-1>", self._on_month_label_click)
        # --- ENDE NEU ---

        ttk.Button(nav_frame, text="Nächster Monat >", command=self.show_next_month).pack(side="right")
        grid_container_frame = ttk.Frame(main_view_container)
        grid_container_frame.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(grid_container_frame, orient="vertical")
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=vsb.set, xscrollcommand=hsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self.canvas.yview)
        hsb.config(command=self.canvas.xview)
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig('inner_frame', width=e.width))
        self.inner_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)

    # --- NEU: Monats-Auswahl-Dialog (analog zu Admin-Seite) ---
    def _on_month_label_click(self, event):
        self._show_month_chooser_dialog()

    def _show_month_chooser_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Monatsauswahl")
        dialog.transient(self.app)  # self.app ist MainUserWindow
        dialog.grab_set()
        dialog.focus_set()

        current_date = self.app.current_display_date
        current_year = current_date.year
        current_month = current_date.month
        month_names_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                          "August", "September", "Oktober", "November", "Dezember"]

        start_year = date.today().year - 5
        end_year = date.today().year + 5
        years = [str(y) for y in range(start_year, end_year + 1)]

        selected_month_var = tk.StringVar(value=month_names_de[current_month - 1])
        selected_year_var = tk.StringVar(value=str(current_year))

        ttk.Label(dialog, text="Monat auswählen:").pack(padx=10, pady=(10, 0))
        month_combo = ttk.Combobox(dialog, textvariable=selected_month_var, values=month_names_de, state="readonly",
                                   width=15)
        month_combo.pack(padx=10, pady=(0, 10))

        ttk.Label(dialog, text="Jahr auswählen:").pack(padx=10, pady=(10, 0))
        year_combo = ttk.Combobox(dialog, textvariable=selected_year_var, values=years, state="readonly", width=15)
        year_combo.pack(padx=10, pady=(0, 10))

        def on_ok():
            try:
                new_month_index = month_names_de.index(selected_month_var.get())
                new_month = new_month_index + 1
                new_year = int(selected_year_var.get())
                new_date = date(new_year, new_month, 1)

                if new_date.year != current_date.year or new_date.month != current_date.month:
                    self.app.current_display_date = new_date
                    if current_year != new_year:
                        self.app._load_holidays_for_year(new_year)
                        self.app._load_events_for_year(new_year)

                    # --- NEU (P4): Preloader beim Monatswechsel per Dialog triggern ---
                    if hasattr(self.app, 'trigger_shift_plan_preload'):
                        self.app.trigger_shift_plan_preload(new_year, new_month)
                    # --- ENDE NEU ---

                    self.build_shift_plan_grid(new_year, new_month)
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Fehler", "Ungültige Monats- oder Jahresauswahl.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=dialog)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=10, pady=10)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=5)
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side="left", padx=5)

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.app.winfo_x() + (self.app.winfo_width() // 2) - (width // 2)
        y = self.app.winfo_y() + (self.app.winfo_height() // 2) - (height // 2)
        dialog.geometry(f'+{x}+{y}')
        dialog.wait_window()

    # --- ENDE NEU ---

    def build_shift_plan_grid(self, year, month):
        for widget in self.plan_grid_frame.winfo_children():
            widget.destroy()
        self.tooltips.clear()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        # Kleiner Fix: `_load_holidays_for_year` erwartet ein Jahr als int
        self.app._load_holidays_for_year(year)
        self.app._load_events_for_year(year)

        self.processed_vacations = self._process_vacations(year, month)
        users = get_ordered_users_for_schedule(include_hidden=False)
        self.shifts = get_shifts_for_month(year, month)
        self.wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
        daily_counts = get_daily_shift_counts_for_month(year, month)
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        month_name_german = {"January": "Januar", "February": "Februar", "March": "März", "April": "April",
                             "May": "Mai", "June": "Juni", "July": "Juli", "August": "August",
                             "September": "September", "October": "Oktober", "November": "November",
                             "December": "Dezember"}
        month_name_en = date(year, month, 1).strftime('%B')
        self.month_label_var.set(f"{month_name_german.get(month_name_en, month_name_en)} {year}")
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        days_in_month = calendar.monthrange(year, month)[1]

        rules = self.app.staffing_rules.get('Colors', {})
        header_bg, summary_bg = "#E0E0E0", "#D0D0FF"
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        ausbildung_bg = rules.get('quartals_ausbildung_bg', "#ADD8E6")
        schiessen_bg = rules.get('schiessen_bg', "#FFB6C1")

        MIN_NAME_WIDTH, MIN_DOG_WIDTH = 150, 100

        tk.Label(self.plan_grid_frame, text="Mitarbeiter", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black",
                 padx=5, pady=5, bd=1, relief="solid").grid(row=0, column=0, columnspan=2, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Name", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=1, column=0, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Diensthund", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black",
                 padx=5, pady=5, bd=1, relief="solid").grid(row=1, column=1, sticky="nsew")
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_abbr = day_map[current_date.weekday()]

            bg = header_bg
            event_type = self.app.get_event_type(current_date)
            if self.app.is_holiday(current_date):
                bg = holiday_bg
            elif event_type == "Quartals Ausbildung":
                bg = ausbildung_bg
            elif event_type == "Schießen":
                bg = schiessen_bg
            elif current_date.weekday() >= 5:
                bg = weekend_bg

            tk.Label(self.plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), bg=bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=0, column=day + 1, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=str(day), font=("Segoe UI", 9), bg=bg, fg="black", padx=5, pady=5, bd=1,
                     relief="solid").grid(row=1, column=day + 1, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Std.", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=0, column=days_in_month + 2, rowspan=2, sticky="nsew")
        current_row = 2
        for user_data_row in users:
            user_id, user_id_str = user_data_row['id'], str(user_data_row['id'])
            self.grid_widgets['cells'][user_id_str] = {}
            is_logged_in_user = user_id == self.app.user_data['id']
            row_font = ("Segoe UI", 10, "bold") if is_logged_in_user else ("Segoe UI", 10)
            tk.Label(self.plan_grid_frame, text=f"{user_data_row['vorname']} {user_data_row['name']}", font=row_font,
                     bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="w").grid(row=current_row,
                                                                                                    column=0,
                                                                                                    sticky="nsew")
            tk.Label(self.plan_grid_frame, text=user_data_row.get('diensthund', '---'), font=row_font, bg="white",
                     fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=current_row, column=1, sticky="nsew")

            for day in range(1, days_in_month + 1):
                current_date_obj = date(year, month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')

                vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date_obj)
                shift = self.shifts.get(user_id_str, {}).get(date_str, "")
                request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)
                display_shift = shift

                if vacation_status == 'Genehmigt':
                    display_shift = 'U'
                elif vacation_status == 'Ausstehend':
                    display_shift = "U?"
                elif request_info:
                    status, requested_shift, requested_by, _ = request_info
                    if status == 'Ausstehend':
                        if requested_by == 'admin':
                            display_shift = f"{requested_shift} (A)?"
                        else:
                            if requested_shift == 'WF':
                                display_shift = 'WF'
                            elif requested_shift == 'T/N':
                                display_shift = 'T./N.?'  # Hier war der Syntaxfehler
                            else:
                                display_shift = f"{requested_shift}?"
                    elif "Akzeptiert" in status or "Genehmigt" in status:
                        if requested_shift == 'WF':
                            display_shift = 'X'
                        # --- KORREKTUR: Fehlende Logik ergänzt ---
                        else:
                            display_shift = requested_shift
                # --- ENDE KORREKTUR ---

                frame = tk.Frame(self.plan_grid_frame, bd=1, relief="solid")
                frame.grid(row=current_row, column=day + 1, sticky="nsew")
                label = tk.Label(frame, text=display_shift, font=("Segoe UI", 10))
                label.pack(expand=True, fill="both")

                if is_logged_in_user and not vacation_status:
                    label.config(cursor="hand2")
                    label.bind("<Button-1>",
                               lambda e, u_id=user_id, d=day, y=year, m=month: self.on_user_cell_click(e, u_id, d, y,
                                                                                                       m))

                self.grid_widgets['cells'][user_id_str][day] = {'frame': frame, 'label': label}

            total_hours_label = tk.Label(self.plan_grid_frame, text="", font=row_font, bg="white",
                                         fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e")
            total_hours_label.grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            self.grid_widgets['user_totals'][user_id_str] = total_hours_label
            self._update_user_total_hours(user_id_str)

            current_row += 1

        tk.Label(self.plan_grid_frame, text="", bg=header_bg, bd=0).grid(row=current_row, column=0,
                                                                         columnspan=days_in_month + 3, sticky="nsew",
                                                                         pady=1)
        current_row += 1
        for item in ordered_abbrevs_to_show:
            abbrev = item['abbreviation']
            self.grid_widgets['daily_counts'][abbrev] = {}
            tk.Label(self.plan_grid_frame, text=abbrev, font=("Segoe UI", 9, "bold"), bg=summary_bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=item.get('name', 'N/A'), font=("Segoe UI", 9), bg=summary_bg,
                     fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="w").grid(row=current_row, column=1,
                                                                                        sticky="nsew")
            for day in range(1, days_in_month + 1):
                current_date = date(year, month, day)
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)

                display_text = ""
                if not (abbrev == "6" and (not is_friday or is_holiday)):
                    count = daily_counts.get(date(year, month, day).strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                    min_required = self.get_min_staffing_for_date(date(year, month, day)).get(abbrev)
                    display_text = f"{count}/{min_required}" if min_required is not None else str(count)

                count_label = tk.Label(self.plan_grid_frame, text=display_text, font=("Segoe UI", 9), bd=1,
                                       relief="solid")
                count_label.grid(row=current_row, column=day + 1, sticky="nsew")
                self.grid_widgets['daily_counts'][abbrev][day] = count_label
            tk.Label(self.plan_grid_frame, text="---", font=("Segoe UI", 9), bg=summary_bg, fg="black", padx=5, pady=5,
                     bd=1, relief="solid", anchor="e").grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            current_row += 1
        self.apply_grid_colors()
        self.plan_grid_frame.grid_columnconfigure(0, minsize=MIN_NAME_WIDTH)
        self.plan_grid_frame.grid_columnconfigure(1, minsize=MIN_DOG_WIDTH)
        for day_col in range(2, days_in_month + 3):
            self.plan_grid_frame.grid_columnconfigure(day_col, weight=1)
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def apply_grid_colors(self):
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        users = get_ordered_users_for_schedule(include_hidden=False)
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        pending_color = rules.get('Ausstehend', 'orange')
        admin_pending_color = rules.get('Admin_Ausstehend', '#E0B0FF')

        self.wunschfrei_data = get_wunschfrei_requests_for_month(year, month)

        for user_data_row in users:
            user_id_str = str(user_data_row['id'])
            is_logged_in_user = user_data_row['id'] == self.app.user_data['id']
            for day in range(1, days_in_month + 1):
                cell_widgets = self.grid_widgets['cells'].get(user_id_str, {}).get(day)
                if not cell_widgets: continue

                frame = cell_widgets['frame']
                label = cell_widgets['label']
                current_date = date(year, month, day)
                is_weekend = current_date.weekday() >= 5
                is_holiday = self.app.is_holiday(current_date)

                frame.config(bg="black", bd=1)

                vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date)
                if vacation_status == 'Ausstehend':
                    frame.config(bg="gold", bd=2)

                original_text = label.cget("text")
                shift_abbrev = original_text.replace("?", "").replace(" (A)", "")
                shift_data = self.app.shift_types_data.get(shift_abbrev)
                request_info = self.wunschfrei_data.get(user_id_str, {}).get(current_date.strftime('%Y-%m-%d'))

                bg_color = "white"
                if is_holiday:
                    bg_color = holiday_bg
                elif is_weekend:
                    bg_color = weekend_bg
                elif is_logged_in_user:
                    bg_color = "#E8F5E9"

                if shift_data and shift_data.get('color'):
                    if shift_abbrev in ["U", "X", "EU"]:
                        bg_color = shift_data.get('color')
                    elif not is_holiday and not is_weekend:
                        bg_color = shift_data.get('color')

                if vacation_status == 'Ausstehend':
                    bg_color = pending_color
                elif request_info and request_info[0] == 'Ausstehend':
                    if request_info[2] == 'admin':
                        bg_color = admin_pending_color
                    else:
                        bg_color = pending_color

                fg_color = self.app.get_contrast_color(bg_color)
                label.config(bg=bg_color, fg=fg_color)

        daily_counts = get_daily_shift_counts_for_month(year, month)
        summary_bg = "#D0D0FF"
        for abbrev, day_map in self.grid_widgets['daily_counts'].items():
            for day, label in day_map.items():
                current_date = date(year, month, day)
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)

                if abbrev == "6" and (not is_friday or is_holiday):
                    label.config(bg=summary_bg, bd=0)
                    continue

                bg = summary_bg
                if self.app.is_holiday(current_date):
                    bg = holiday_bg
                elif current_date.weekday() >= 5:
                    bg = weekend_bg

                count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                min_req = self.get_min_staffing_for_date(current_date).get(abbrev)
                if min_req is not None:
                    if count < min_req:
                        bg = rules.get('alert_bg', "#FF5555")
                    elif count > min_req:
                        bg = rules.get('overstaffed_bg', "#FFFF99")
                    else:
                        bg = rules.get('success_bg', "#90EE90")
                label.config(bg=bg, fg=self.app.get_contrast_color(bg), bd=1)

    def get_min_staffing_for_date(self, current_date):
        rules, min_staffing = self.app.staffing_rules, {}
        min_staffing.update(rules.get('Daily', {}))
        if self.app.is_holiday(current_date):
            min_staffing.update(rules.get('Holiday', {}))
        elif current_date.weekday() >= 5:
            min_staffing.update(rules.get('Sa-So', {}))
        elif current_date.weekday() == 4:
            min_staffing.update(rules.get('Fr', {}))
        else:
            min_staffing.update(rules.get('Mo-Do', {}))
        return {k: int(v) for k, v in min_staffing.items() if str(v).isdigit()}

    def on_user_cell_click(self, event, user_id, day, year, month):
        request_date = date(year, month, day)

        if RequestLockManager.is_month_locked(year, month):
            messagebox.showinfo("Anträge gesperrt",
                                "Für diesen Monat können keine neuen Anträge gestellt oder bestehende bearbeitet werden.",
                                parent=self)
            return

        if request_date < date.today():
            messagebox.showwarning("Aktion nicht erlaubt", "Anfragen für vergangene Tage sind nicht möglich.",
                                   parent=self)
            return
        date_str = request_date.strftime('%Y-%m-%d')
        existing_request = get_wunschfrei_request_by_user_and_date(user_id, date_str)

        if existing_request and existing_request.get('requested_by') == 'admin' and existing_request.get(
                'status') == 'Ausstehend':
            self.handle_admin_request(event, existing_request)
            return

        if existing_request and (
                "Akzeptiert" in existing_request['status'] or "Genehmigt" in existing_request['status']):
            messagebox.showinfo("Info",
                                "Ein bereits akzeptierter Antrag kann hier nicht geändert werden.\nBitte ziehe den Antrag im Reiter 'Meine Anfragen' zurück, um einen neuen zu stellen.",
                                parent=self)
            return

        context_menu = tk.Menu(self, tearoff=0)
        request_config = RequestConfigManager.load_config()
        if existing_request:
            context_menu.add_command(label="Wunsch zurückziehen",
                                     command=lambda: self._withdraw_request(existing_request['id'], user_id, date_str))
            context_menu.add_separator()

        if request_config.get("WF", True):
            label = "Wunschfrei beantragen" if not existing_request else "Wunsch auf 'Frei' ändern"
            context_menu.add_command(label=label, command=lambda: self._handle_user_request(year, month, day, None))

        context_menu.add_separator()

        label_t = f"Wunsch: 'T.' eintragen" if not existing_request else f"Wunsch auf 'T.' ändern"
        context_menu.add_command(label=label_t,
                                 command=lambda: self._handle_user_request(year, month, day, "T."))

        label_n = f"Wunsch: 'N.' eintragen" if not existing_request else f"Wunsch auf 'N.' ändern"
        context_menu.add_command(label=label_n,
                                 command=lambda: self._handle_user_request(year, month, day, "N."))

        label_tn = f"Wunsch: 'T. oder N.' eintragen" if not existing_request else f"Wunsch auf 'T. oder N.' ändern"
        context_menu.add_command(label=label_tn,
                                 command=lambda: self._handle_user_request(year, month, day, "T/N"))

        other_shifts_available = any(request_config.get(s, False) for s in ["6", "24"])
        if other_shifts_available:
            context_menu.add_separator()
        for shift in ["6", "24"]:
            if request_config.get(shift, False):
                is_friday = request_date.weekday() == 4
                is_holiday = self.app.is_holiday(request_date)
                if shift == "6" and (not is_friday or is_holiday):
                    continue
                label = f"Wunsch: '{shift}' eintragen" if not existing_request else f"Wunsch auf '{shift}' ändern"
                context_menu.add_command(label=label,
                                         command=lambda s=shift: self._handle_user_request(year, month, day, s))

        if context_menu.index("end") is not None:
            context_menu.post(event.x_root, event.y_root)
        else:
            messagebox.showinfo("Keine Aktionen", "Aktuell sind keine Anfragetypen für diesen Tag verfügbar.",
                                parent=self)

    def handle_admin_request(self, event, request_info):
        context_menu = tk.Menu(self, tearoff=0)
        if request_info.get('requested_shift') == 'T/N':
            context_menu.add_command(label="Als Tagschicht annehmen",
                                     command=lambda: self.respond_to_admin_request(request_info['id'], 'Genehmigt',
                                                                                   'T.'))
            context_menu.add_command(label="Als Nachtschicht annehmen",
                                     command=lambda: self.respond_to_admin_request(request_info['id'], 'Genehmigt',
                                                                                   'N.'))
            context_menu.add_separator()
            context_menu.add_command(label="Ablehnen",
                                     command=lambda: self.respond_to_admin_request(request_info['id'], 'Abgelehnt'))
        else:
            context_menu.add_command(label="Einverstanden",
                                     command=lambda: self.respond_to_admin_request(request_info['id'], 'Genehmigt'))
            context_menu.add_command(label="Ablehnen",
                                     command=lambda: self.respond_to_admin_request(request_info['id'], 'Abgelehnt'))
        context_menu.post(event.x_root, event.y_root)

    def respond_to_admin_request(self, request_id, response, shift_to_set=None):
        request_info_before = get_wunschfrei_request_by_id(request_id)
        if not request_info_before:
            messagebox.showerror("Fehler", "Anfrage nicht gefunden.", parent=self)
            return

        success, message = user_respond_to_request(request_id, response)

        if success:
            if response == 'Genehmigt':
                final_shift = shift_to_set if shift_to_set else request_info_before['requested_shift']
                save_shift_entry(
                    request_info_before['user_id'],
                    request_info_before['request_date'],
                    final_shift,
                    keep_request_record=True
                )
            self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)
            if "Meine Anfragen" in self.app.tab_frames:
                self.app.tab_frames["Meine Anfragen"].refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def _update_user_total_hours(self, user_id_str):
        total_hours_label = self.grid_widgets['user_totals'].get(user_id_str)
        if not total_hours_label:
            return

        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]

        user_shifts = self.shifts.get(user_id_str, {})
        user_wunschanfragen = self.wunschfrei_data.get(user_id_str, {})

        planned_hours = 0
        wish_hours = 0
        has_pending_requests = False

        prev_month_date = date(year, month, 1) - timedelta(days=1)
        prev_month_shifts = get_shifts_for_month(prev_month_date.year, prev_month_date.month)
        if prev_month_shifts.get(user_id_str, {}).get(prev_month_date.strftime('%Y-%m-%d')) == 'N.':
            planned_hours += 6

        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            shift = user_shifts.get(date_str, "")

            if shift in self.app.shift_types_data:
                hours = self.app.shift_types_data[shift].get('hours', 0)
                if shift == 'N.' and day == days_in_month:
                    hours = 6
                planned_hours += hours

            request_info = user_wunschanfragen.get(date_str)
            if request_info and request_info[0] == 'Ausstehend':
                has_pending_requests = True
                requested_shift = request_info[1]
                if requested_shift in self.app.shift_types_data:
                    hours = self.app.shift_types_data[requested_shift].get('hours', 0)
                    if requested_shift == 'N.' and day == days_in_month:
                        hours = 6
                    wish_hours += hours

        total_hours = planned_hours + wish_hours
        total_hours_label.config(text=str(total_hours))

        tooltip_key = f"tooltip_{user_id_str}"
        if has_pending_requests:
            total_hours_label.config(background="orange")
            tooltip_text = f"Geplant: {planned_hours} Std.\nWunsch: {wish_hours} Std."
            if tooltip_key in self.tooltips:
                self.tooltips[tooltip_key].text = tooltip_text
            else:
                self.tooltips[tooltip_key] = Tooltip(total_hours_label, tooltip_text)
        else:
            total_hours_label.config(background="white")
            if tooltip_key in self.tooltips:
                self.tooltips[tooltip_key].hidetip()
                self.tooltips[tooltip_key].widget.unbind("<Enter>")
                self.tooltips[tooltip_key].widget.unbind("<Leave>")
                del self.tooltips[tooltip_key]

    def _update_cell_ui(self, user_id, date_str):
        user_id_str = str(user_id)
        year, month, day = map(int, date_str.split('-'))

        request_info = get_wunschfrei_request_by_user_and_date(user_id, date_str)
        shift = self.shifts.get(user_id_str, {}).get(date_str, "")

        if user_id_str not in self.wunschfrei_data:
            self.wunschfrei_data[user_id_str] = {}
        if request_info:
            self.wunschfrei_data[user_id_str][date_str] = (
                request_info['status'], request_info['requested_shift'], request_info.get('requested_by', 'user'),
                None)  # No timestamp
        elif date_str in self.wunschfrei_data.get(user_id_str, {}):
            del self.wunschfrei_data[user_id_str][date_str]

        display_shift = shift
        if request_info:
            status, requested_shift, requested_by = request_info['status'], request_info[
                'requested_shift'], request_info.get(
                'requested_by', 'user')
            if status == 'Ausstehend':
                if requested_by == 'admin':
                    display_shift = f"{requested_shift} (A)?"
                else:
                    if requested_shift == 'WF':
                        display_shift = 'WF'
                    elif requested_shift == 'T/N':
                        display_shift = 'T./N.?'
                    else:
                        display_shift = f"{requested_shift}?"
            elif "Akzeptiert" in status or "Genehmigt" in status:
                if requested_shift == 'WF':
                    display_shift = 'X'
                else:
                    display_shift = requested_shift

        cell_widgets = self.grid_widgets['cells'].get(user_id_str, {}).get(day)
        if cell_widgets:
            cell_widgets['label'].config(text=display_shift)

        self.apply_grid_colors()
        self._update_user_total_hours(user_id_str)

    def _withdraw_request(self, request_id, user_id, date_str):
        success, message = withdraw_wunschfrei_request(request_id, user_id)
        if success:
            if self.app.show_request_popups:
                CustomMessagebox(self, "Erfolg", message, lambda: setattr(self.app, 'show_request_popups', False))
            self._update_cell_ui(user_id, date_str)
            if "Meine Anfragen" in self.app.tab_frames:
                self.app.tab_frames["Meine Anfragen"].refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def _handle_user_request(self, year, month, day, request_type):
        request_date = date(year, month, day)
        date_str = request_date.strftime('%Y-%m-%d')

        if request_type is None:
            request_count = get_wunschfrei_requests_by_user_for_month(self.app.user_data['id'], year, month)
            existing_request = get_wunschfrei_request_by_user_and_date(self.app.user_data['id'], date_str)
            is_new_wf_request = not existing_request or existing_request['requested_shift'] != 'WF'
            if is_new_wf_request and request_count >= 3:
                messagebox.showwarning("Limit erreicht",
                                       "Du hast das Maximum von 3 'Wunschfrei'-Anfragen für diesen Monat erreicht.",
                                       parent=self)
                return
            action_text = "beantragen" if not existing_request else "ändern"
            msg = f"Möchtest du für den {request_date.strftime('%d.%m.%Y')} 'Wunschfrei' {action_text}?"
            if is_new_wf_request:
                msg += f"\nDu hast noch {3 - request_count} Anfrage(n) frei."
            if not messagebox.askyesno("Bestätigen", msg, parent=self):
                return

        success, message = submit_user_request(self.app.user_data['id'], date_str, request_type)
        if success:
            if self.app.show_request_popups:
                CustomMessagebox(self, "Erfolg", message, lambda: setattr(self.app, 'show_request_popups', False))
            self._update_cell_ui(self.app.user_data['id'], date_str)
            if "Meine Anfragen" in self.app.tab_frames:
                self.app.tab_frames["Meine Anfragen"].refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def show_previous_month(self):
        # (Angepasst)
        current_date = self.app.current_display_date
        self.app.current_display_date = (self.app.current_display_date.replace(day=1) - timedelta(days=1)).replace(
            day=1)
        new_year, new_month = self.app.current_display_date.year, self.app.current_display_date.month

        if current_date.year != new_year:
            self.app._load_holidays_for_year(new_year)
            self.app._load_events_for_year(new_year)

        # --- NEU (P4): Preloader beim Blättern triggern ---
        if hasattr(self.app, 'trigger_shift_plan_preload'):
            self.app.trigger_shift_plan_preload(new_year, new_month)
        # --- ENDE NEU ---

        self.build_shift_plan_grid(new_year, new_month)

    def show_next_month(self):
        # (Angepasst)
        current_date = self.app.current_display_date
        days_in_month = calendar.monthrange(self.app.current_display_date.year, self.app.current_display_date.month)[1]
        self.app.current_display_date = self.app.current_display_date.replace(day=1) + timedelta(days=days_in_month)
        new_year, new_month = self.app.current_display_date.year, self.app.current_display_date.month

        if current_date.year != new_year:
            self.app._load_holidays_for_year(new_year)
            self.app._load_events_for_year(new_year)

        # --- NEU (P4): Preloader beim Blättern triggern ---
        if hasattr(self.app, 'trigger_shift_plan_preload'):
            self.app.trigger_shift_plan_preload(new_year, new_month)
        # --- ENDE NEU ---

        self.build_shift_plan_grid(new_year, new_month)