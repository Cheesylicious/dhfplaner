# gui/tabs/user_shift_plan_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
import calendar
from database.db_manager import (
    get_shifts_for_month, get_wunschfrei_requests_for_month, get_daily_shift_counts_for_month,
    get_ordered_shift_abbrevs, get_ordered_users_for_schedule, submit_user_request,
    get_wunschfrei_requests_by_user_for_month, get_wunschfrei_request_by_user_and_date,
    withdraw_wunschfrei_request
)
from gui.request_config_manager import RequestConfigManager


class UserShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_widgets = {}
        self.setup_ui()
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def setup_ui(self):
        main_view_container = ttk.Frame(self, padding="10")
        main_view_container.pack(fill="both", expand=True)
        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(nav_frame, text="< Voriger Monat", command=self.show_previous_month).pack(side="left")
        self.month_label_var = tk.StringVar()
        ttk.Label(nav_frame, textvariable=self.month_label_var, font=("Segoe UI", 14, "bold"), anchor="center").pack(
            side="left", expand=True, fill="x")
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

    def build_shift_plan_grid(self, year, month):
        for widget in self.plan_grid_frame.winfo_children():
            widget.destroy()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
        if year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(year)
        users = get_ordered_users_for_schedule(include_hidden=False)
        shifts = get_shifts_for_month(year, month)
        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
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
        header_bg, summary_bg = "#E0E0E0", "#D0D0FF"
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
            bg = "#FFD700" if self.app.is_holiday(current_date) else (
                "#EAF4FF" if current_date.weekday() >= 5 else header_bg)
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
            total_hours = 0
            for day in range(1, days_in_month + 1):
                date_str = date(year, month, day).strftime('%Y-%m-%d')
                shift = shifts.get(user_id_str, {}).get(date_str, "")
                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)
                display_shift = shift

                if request_info:
                    status, requested_shift = request_info
                    if status == 'Ausstehend':
                        display_shift = 'WF' if requested_shift == 'WF' else f"{requested_shift}?"
                    elif status == 'Genehmigt' and requested_shift == 'WF':
                        display_shift = 'X'
                    elif status == 'Abgelehnt':
                        display_shift = ""  # Zelle explizit leeren

                if shift in self.app.shift_types_data:
                    total_hours += self.app.shift_types_data[shift].get('hours', 0)

                label = tk.Label(self.plan_grid_frame, text=display_shift, font=("Segoe UI", 10), bd=1, relief="solid")
                label.grid(row=current_row, column=day + 1, sticky="nsew")
                if is_logged_in_user:
                    label.config(cursor="hand2")
                    label.bind("<Button-1>",
                               lambda e, u_id=user_id, d=day, y=year, m=month: self.on_user_cell_click(e, u_id, d, y,
                                                                                                       m))
                self.grid_widgets['cells'][user_id_str][day] = label
            total_hours_label = tk.Label(self.plan_grid_frame, text=str(total_hours), font=row_font, bg="white",
                                         fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e")
            total_hours_label.grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            self.grid_widgets['user_totals'][user_id_str] = total_hours_label
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
        pending_color = rules.get('Ausstehend', 'orange')
        approved_color = rules.get('Genehmigt', 'lightgreen')
        rejected_color = rules.get('Abgelehnt', 'lightcoral')

        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)

        for user_data_row in users:
            user_id_str = str(user_data_row['id'])
            is_logged_in_user = user_data_row['id'] == self.app.user_data['id']
            for day in range(1, days_in_month + 1):
                cell = self.grid_widgets['cells'].get(user_id_str, {}).get(day)
                if not cell: continue
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                shift_abbrev = cell.cget("text").replace("?", "")
                shift_data = self.app.shift_types_data.get(shift_abbrev)

                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)

                bg_color = "white"
                if self.app.is_holiday(current_date):
                    bg_color = "#FFD700"
                elif current_date.weekday() >= 5:
                    bg_color = "#EAF4FF"
                elif is_logged_in_user:
                    bg_color = "#E8F5E9"

                is_exception = shift_abbrev in ["EU", "X"]
                if request_info:
                    status = request_info[0]
                    if status == 'Ausstehend':
                        is_exception = True
                        bg_color = pending_color
                    elif status == 'Genehmigt':
                        is_exception = True
                        if shift_data and shift_data.get('color'):
                            bg_color = shift_data.get('color')
                        else:
                            bg_color = approved_color
                    elif status == 'Abgelehnt':
                        # Keine spezielle Farbe, nur die Zelle ist leer.
                        # Der Basishintergrund (weiß, WE, Feiertag) bleibt.
                        pass

                if shift_data and not (self.app.is_holiday(current_date) or current_date.weekday() >= 5):
                    if not is_exception:
                        bg_color = shift_data.get('color', bg_color)

                fg_color = self.app.get_contrast_color(bg_color)
                cell.config(bg=bg_color, fg=fg_color)

        daily_counts = get_daily_shift_counts_for_month(year, month)
        for abbrev, day_map in self.grid_widgets['daily_counts'].items():
            for day, label in day_map.items():
                current_date = date(year, month, day)
                count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                min_req = self.get_min_staffing_for_date(current_date).get(abbrev)
                bg = "#D0D0FF"
                if self.app.is_holiday(current_date):
                    bg = "#FFD700"
                elif current_date.weekday() >= 5:
                    bg = "#EAF4FF"
                if min_req is not None:
                    if count < min_req:
                        bg = rules.get('alert_bg', "#FF5555")
                    elif count > min_req:
                        bg = rules.get('overstaffed_bg', "#FFFF99")
                    else:
                        bg = rules.get('success_bg', "#90EE90")
                label.config(bg=bg, fg=self.app.get_contrast_color(bg))

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
        if request_date < date.today():
            messagebox.showwarning("Aktion nicht erlaubt", "Anfragen für vergangene Tage sind nicht möglich.",
                                   parent=self)
            return
        date_str = request_date.strftime('%Y-%m-%d')
        existing_request = get_wunschfrei_request_by_user_and_date(user_id, date_str)
        if existing_request and existing_request['status'] == 'Genehmigt':
            messagebox.showinfo("Info",
                                "Ein bereits genehmigter Antrag kann hier nicht geändert werden.\nBitte ziehe den Antrag im Reiter 'Meine Anfragen' zurück, um einen neuen zu stellen.",
                                parent=self)
            return
        context_menu = tk.Menu(self, tearoff=0)
        request_config = RequestConfigManager.load_config()
        if existing_request:
            context_menu.add_command(label="Wunsch zurückziehen",
                                     command=lambda: self._withdraw_request(existing_request['id'], user_id))
            context_menu.add_separator()
        if request_config.get("WF", True):
            label = "Wunschfrei beantragen" if not existing_request else "Wunsch auf 'Frei' ändern"
            context_menu.add_command(label=label, command=lambda: self._handle_user_request(year, month, day, None))
        shift_options_available = any(request_config.get(s, False) for s in ["T.", "N.", "6", "24"])
        if shift_options_available:
            context_menu.add_separator()
        for shift in ["T.", "N.", "6", "24"]:
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

    def _withdraw_request(self, request_id, user_id):
        success, message = withdraw_wunschfrei_request(request_id, user_id)
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)
            if "Meine Anfragen" in self.app.tab_frames:
                self.app.tab_frames["Meine Anfragen"].refresh_wunschfrei_tab()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def _handle_user_request(self, year, month, day, request_type):
        request_date = date(year, month, day)
        if request_type is None:  # WF
            request_count = get_wunschfrei_requests_by_user_for_month(self.app.user_data['id'], year, month)
            existing_request = get_wunschfrei_request_by_user_and_date(self.app.user_data['id'],
                                                                       request_date.strftime('%Y-%m-%d'))
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
        success, message = submit_user_request(self.app.user_data['id'], request_date.strftime('%Y-%m-%d'),
                                               request_type)
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.build_shift_plan_grid(year, month)
            if "Meine Anfragen" in self.app.tab_frames:
                self.app.tab_frames["Meine Anfragen"].refresh_wunschfrei_tab()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def show_previous_month(self):
        self.app.current_display_date = (self.app.current_display_date.replace(day=1) - timedelta(days=1)).replace(
            day=1)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def show_next_month(self):
        days_in_month = calendar.monthrange(self.app.current_display_date.year, self.app.current_display_date.month)[1]
        self.app.current_display_date = self.app.current_display_date.replace(day=1) + timedelta(days=days_in_month)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)