# gui/tabs/shift_plan_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
import calendar

from database.db_manager import (
    get_shifts_for_month, get_wunschfrei_requests_for_month, get_daily_shift_counts_for_month,
    get_ordered_shift_abbrevs, get_ordered_users_for_schedule, save_shift_entry,
    get_wunschfrei_request_by_user_and_date
)
from gui.admin_menu_config_manager import AdminMenuConfigManager


class ShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_widgets = {}
        self.violation_cells = set()
        self.current_user_order = []
        self.shift_schedule_data = {}
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
        settings_frame = ttk.Frame(main_view_container)
        settings_frame.pack(fill="x", pady=(0, 5))
        settings_frame.columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
        ttk.Button(settings_frame, text="Mitarbeiter-Sortierung", command=self.app.open_user_order_window).grid(row=0,
                                                                                                                column=0,
                                                                                                                sticky="ew",
                                                                                                                padx=2)
        ttk.Button(settings_frame, text="Schicht-Sortierung", command=self.app.open_shift_order_window).grid(row=0,
                                                                                                             column=1,
                                                                                                             sticky="ew",
                                                                                                             padx=2)
        ttk.Button(settings_frame, text="Besetzungsregeln", command=self.app.open_staffing_rules_window).grid(row=0,
                                                                                                              column=2,
                                                                                                              sticky="ew",
                                                                                                              padx=2)
        ttk.Button(settings_frame, text="Feiertage", command=self.app.open_holiday_settings_window).grid(row=0,
                                                                                                         column=3,
                                                                                                         sticky="ew",
                                                                                                         padx=2)
        ttk.Button(settings_frame, text="Anfragen verwalten", command=self.app.open_request_settings_window).grid(row=0,
                                                                                                                  column=4,
                                                                                                                  sticky="ew",
                                                                                                                  padx=2)
        ttk.Button(settings_frame, text="Planungs-Helfer", command=self.app.open_planning_assistant_settings).grid(
            row=0, column=5, sticky="ew", padx=2)
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

        def _configure_inner_frame(event):
            self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame)
        self.inner_frame.bind('<Configure>', _configure_scrollregion)
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)
        check_frame = ttk.Frame(main_view_container)
        check_frame.pack(fill="x", pady=10)
        button_subframe = ttk.Frame(check_frame)
        button_subframe.pack()
        ttk.Button(button_subframe, text="Schichtplan Prüfen", command=self.check_understaffing).pack(side="left",
                                                                                                      padx=5)
        ttk.Button(button_subframe, text="Leeren", command=self.clear_understaffing_results).pack(side="left", padx=5)
        self.understaffing_result_frame = ttk.Frame(main_view_container, padding="10")

    def build_shift_plan_grid(self, year, month):
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
        self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)
        self.shift_schedule_data = get_shifts_for_month(year, month)
        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
        daily_counts = get_daily_shift_counts_for_month(year, month)
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        month_name = date(year, month, 1).strftime('%B')
        self.month_label_var.set(f"{month_name.capitalize()} {year}")
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
            is_weekend = current_date.weekday() >= 5
            is_holiday = self.app.is_holiday(current_date)
            bg = "#FFD700" if is_holiday else ("#EAF4FF" if is_weekend else header_bg)
            tk.Label(self.plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), bg=bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=0, column=day + 1, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=str(day), font=("Segoe UI", 9), bg=bg, fg="black", padx=5, pady=5, bd=1,
                     relief="solid").grid(row=1, column=day + 1, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Std.", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=0, column=days_in_month + 2, rowspan=2, sticky="nsew")
        current_row = 2
        for user_data_row in self.current_user_order:
            user_id, user_id_str = user_data_row['id'], str(user_data_row['id'])
            self.grid_widgets['cells'][user_id_str] = {}
            tk.Label(self.plan_grid_frame, text=f"{user_data_row['vorname']} {user_data_row['name']}",
                     font=("Segoe UI", 10, "bold"), bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid",
                     anchor="w").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=user_data_row.get('diensthund', '---'), font=("Segoe UI", 10),
                     bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=current_row, column=1,
                                                                                        sticky="nsew")
            total_hours = 0
            for day in range(1, days_in_month + 1):
                date_str = date(year, month, day).strftime('%Y-%m-%d')
                shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str, "")
                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)
                display_text = shift
                if request_info:
                    if request_info[0] == 'Ausstehend':
                        display_text = 'WF' if request_info[1] == 'WF' else f"{request_info[1]}?"
                    elif request_info[0] == 'Genehmigt' and request_info[1] == 'WF':
                        display_text = 'X'
                if shift in self.app.shift_types_data:
                    total_hours += self.app.shift_types_data[shift].get('hours', 0)
                label = tk.Label(self.plan_grid_frame, text=display_text, font=("Segoe UI", 10), bd=1, relief="solid",
                                 cursor="hand2")
                label.grid(row=current_row, column=day + 1, sticky="nsew")
                label.bind("<Button-1>",
                           lambda e, uid=user_id, d=day, y=year, m=month: self.on_grid_cell_click(e, uid, d, y, m))
                if '?' in display_text or display_text == 'WF':
                    label.bind("<Button-3>",
                               lambda e, uid=user_id, dt=date_str: self.show_wunschfrei_context_menu(e, uid, dt))
                self.grid_widgets['cells'][user_id_str][day] = label
            total_hours_label = tk.Label(self.plan_grid_frame, text=str(total_hours), font=("Segoe UI", 10, "bold"),
                                         bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e")
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

    def show_previous_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        self.app.current_display_date = last_day_of_previous_month.replace(day=1)
        if current_date.year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(self.app.current_display_date.year)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def show_next_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        first_day_of_next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        self.app.current_display_date = first_day_of_next_month
        if current_date.year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(self.app.current_display_date.year)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def apply_grid_colors(self):
        self.update_violation_set()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        weekend_bg, holiday_bg = "#EAF4FF", "#FFD700"
        rules = self.app.staffing_rules.get('Colors', {})
        pending_color = rules.get('Ausstehend', 'orange')
        approved_color = rules.get('Genehmigt', 'lightgreen')
        for user in self.current_user_order:
            user_id, user_id_str = user['id'], str(user['id'])
            for day in range(1, days_in_month + 1):
                cell = self.grid_widgets['cells'].get(user_id_str, {}).get(day)
                if not cell: continue
                current_date = date(year, month, day)
                original_text = cell.cget("text")
                shift_abbrev = original_text.replace("?", "")
                shift_data = self.app.shift_types_data.get(shift_abbrev)
                bg_color = "white"
                if self.app.is_holiday(current_date):
                    bg_color = holiday_bg
                elif current_date.weekday() >= 5:
                    bg_color = weekend_bg
                is_exception = "?" in original_text or original_text == "WF" or shift_abbrev in ["EU", "X"]
                if is_exception:
                    if "?" in original_text or original_text == "WF":
                        bg_color = pending_color
                    elif shift_data and shift_data.get('color'):
                        bg_color = shift_data.get('color')
                    elif shift_abbrev == "X":
                        bg_color = approved_color
                elif shift_data and not (self.app.is_holiday(current_date) or current_date.weekday() >= 5):
                    bg_color = shift_data.get('color', bg_color)
                fg_color = self.app.get_contrast_color(bg_color)
                if (user_id, day) in self.violation_cells:
                    bg_color = "#FF5555"
                    fg_color = "white"
                cell.config(bg=bg_color, fg=fg_color)
        daily_counts = get_daily_shift_counts_for_month(year, month)
        for abbrev, day_map in self.grid_widgets['daily_counts'].items():
            for day, label in day_map.items():
                current_date = date(year, month, day)
                count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                min_req = self.get_min_staffing_for_date(current_date).get(abbrev)
                bg = "#D0D0FF"
                if self.app.is_holiday(current_date):
                    bg = holiday_bg
                elif current_date.weekday() >= 5:
                    bg = weekend_bg
                if min_req is not None:
                    if count < min_req:
                        bg = rules.get('alert_bg', "#FF5555")
                    elif count > min_req:
                        bg = rules.get('overstaffed_bg', "#FFFF99")
                    else:
                        bg = rules.get('success_bg', "#90EE90")
                label.config(bg=bg, fg=self.app.get_contrast_color(bg))

    def refresh_plan(self):
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def on_grid_cell_click(self, event, user_id, day, year, month):
        current_shift = event.widget.cget("text")
        if '?' in current_shift or current_shift == 'WF': return

        shift_date_str = date(year, month, day).strftime('%Y-%m-%d')
        context_menu = tk.Menu(self, tearoff=0)
        context_menu.add_command(label="FREI (Dienst entfernen)",
                                 command=lambda: self._save_shift_and_update_ui(user_id, shift_date_str, current_shift,
                                                                                ""))
        context_menu.add_separator()
        all_abbrevs = list(self.app.shift_types_data.keys())
        menu_config = AdminMenuConfigManager.load_config(all_abbrevs)
        sorted_abbrevs = sorted(all_abbrevs, key=lambda s: self.app.shift_frequency.get(s, 0), reverse=True)
        for abbrev in sorted(sorted_abbrevs):
            if menu_config.get(abbrev, True):
                name = self.app.shift_types_data[abbrev].get('name', abbrev)
                count = self.app.shift_frequency.get(abbrev, 0)
                label_text = f"{abbrev} ({name})" + (f"  (Bisher {count}x)" if count > 0 else "")
                context_menu.add_command(label=label_text,
                                         command=lambda s=abbrev: self._save_shift_and_update_ui(user_id,
                                                                                                 shift_date_str,
                                                                                                 current_shift, s))
        context_menu.post(event.x_root, event.y_root)

    def show_wunschfrei_context_menu(self, event, user_id, date_str):
        request = get_wunschfrei_request_by_user_and_date(user_id, date_str)
        if not request or request['status'] != 'Ausstehend': return

        context_menu = tk.Menu(self, tearoff=0)

        wunschfrei_tab = self.app.tab_frames.get("Wunschanfragen")

        if wunschfrei_tab:
            context_menu.add_command(label="Genehmigen",
                                     command=lambda: wunschfrei_tab.process_wunschfrei_by_id(request['id'], True))
            context_menu.add_command(label="Ablehnen",
                                     command=lambda: wunschfrei_tab.process_wunschfrei_by_id(request['id'], False))
            context_menu.post(event.x_root, event.y_root)

    def _save_shift_and_update_ui(self, user_id, date_str, old_shift, new_shift):
        success, message = save_shift_entry(user_id, date_str, new_shift)
        if success:
            if new_shift and new_shift != "FREI":
                self.app.shift_frequency[new_shift] = self.app.shift_frequency.get(new_shift, 0) + 1
                self.app.save_shift_frequency()
            user_id_str = str(user_id)
            if user_id_str not in self.shift_schedule_data:
                self.shift_schedule_data[user_id_str] = {}
            if new_shift:
                self.shift_schedule_data[user_id_str][date_str] = new_shift
            elif date_str in self.shift_schedule_data[user_id_str]:
                del self.shift_schedule_data[user_id_str][date_str]
            self._update_ui_after_change(user_id, date_str, old_shift, new_shift)
        else:
            messagebox.showerror("Fehler", message, parent=self.app)

    def _update_ui_after_change(self, user_id, date_str, old_shift, new_shift):
        year, month, day = map(int, date_str.split('-'))
        user_id_str = str(user_id)
        cell_widget = self.grid_widgets['cells'][user_id_str][day]
        cell_widget.config(text=new_shift)
        self._update_user_total_hours(user_id_str)
        self._update_daily_counts_for_day(day, old_shift, new_shift)
        self.apply_grid_colors()

    def _update_user_total_hours(self, user_id_str):
        total_hours = 0
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        user_shifts = self.shift_schedule_data.get(user_id_str, {})
        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            shift = user_shifts.get(date_str, "")
            if shift in self.app.shift_types_data:
                total_hours += self.app.shift_types_data[shift].get('hours', 0)
        total_hours_label = self.grid_widgets['user_totals'].get(user_id_str)
        if total_hours_label:
            total_hours_label.config(text=str(total_hours))

    def _update_daily_counts_for_day(self, day, old_shift, new_shift):
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        current_date = date(year, month, day)
        date_str = current_date.strftime('%Y-%m-%d')
        daily_counts_for_day = get_daily_shift_counts_for_month(year, month).get(date_str, {})
        for abbrev, day_map in self.grid_widgets['daily_counts'].items():
            if day in day_map:
                count_label = day_map[day]
                count = daily_counts_for_day.get(abbrev, 0)
                min_required = self.get_min_staffing_for_date(current_date).get(abbrev)
                display_text = f"{count}/{min_required}" if min_required is not None else str(count)
                count_label.config(text=display_text)

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

    def update_violation_set(self):
        self.violation_cells.clear()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]

        # Sequenzregel (Nachtschicht)
        for user in self.current_user_order:
            user_id_str = str(user['id'])
            for day in range(1, days_in_month):
                date1 = date(year, month, day).strftime('%Y-%m-%d')
                date2 = date(year, month, day + 1).strftime('%Y-%m-%d')
                shift1 = self.shift_schedule_data.get(user_id_str, {}).get(date1, "")
                shift2 = self.shift_schedule_data.get(user_id_str, {}).get(date2, "")
                if shift1 == 'N.' and shift2 not in ['', 'FREI', 'N.']:
                    self.violation_cells.add((user['id'], day))
                    self.violation_cells.add((user['id'], day + 1))

        # --- Diensthund-Konfliktprüfung (JETZT MIT FILTER) ---
        NON_DUTY_SHIFTS = ["X", "EU", "U", "S", "KR",
                           "R"]  # Genehmigter Wunschfrei, Erholungsurlaub, Urlaub, Krankheit, Reserve etc.

        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            dog_schedule = {}
            for user in self.current_user_order:
                dog = user.get('diensthund')
                if dog and dog != '---':
                    shift = self.shift_schedule_data.get(str(user['id']), {}).get(date_str)

                    # KORREKTUR: Nur Schichten, die eine aktive Dienstzeit darstellen, prüfen.
                    if shift and shift not in NON_DUTY_SHIFTS:
                        if dog not in dog_schedule: dog_schedule[dog] = []
                        dog_schedule[dog].append((user['id'], shift))

            for dog, assignments in dog_schedule.items():
                if len(assignments) > 1:
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            if self._check_time_overlap(assignments[i][1], assignments[j][1]):
                                self.violation_cells.add((assignments[i][0], day))
                                self.violation_cells.add((assignments[j][0], day))

    def _get_shift_time_data(self, abbrev):
        """Hilfsfunktion, um Schichtdaten mit robustem Zeitformat-Handling zu holen."""

        # Standardzeiten für häufige hardcodierte Abkürzungen als Fallback
        default_times = {
            "6": {"start_time": "12:00", "end_time": "18:00"},
            "T.": {"start_time": "06:00", "end_time": "18:00"},
            "N.": {"start_time": "22:00", "end_time": "06:00"},
            "24": {"start_time": "00:00", "end_time": "00:00"},
        }

        db_data = self.app.shift_types_data.get(abbrev, {})
        hardcode_data = default_times.get(abbrev, {})

        # Bevorzugt DB-Daten. Nur wenn DB-Daten fehlen (None/leer), wird Hardcode verwendet.
        final_data = {
            'start_time': db_data.get('start_time') if db_data.get('start_time') else hardcode_data.get('start_time'),
            'end_time': db_data.get('end_time') if db_data.get('end_time') else hardcode_data.get('end_time')
        }

        return final_data

    def _check_time_overlap(self, shift1_abbrev, shift2_abbrev):

        s1_data = self._get_shift_time_data(shift1_abbrev)
        s2_data = self._get_shift_time_data(shift2_abbrev)

        s1_start_val = s1_data.get('start_time')
        s1_end_val = s1_data.get('end_time')
        s2_start_val = s2_data.get('start_time')
        s2_end_val = s2_data.get('end_time')

        # 1. Prüfen, ob wir die Zeiten überhaupt haben
        if not all([s1_start_val, s1_end_val, s2_start_val, s2_end_val]):
            return False

        try:
            # Funktion zur korrekten Konvertierung in Minuten
            def time_to_minutes(time_value):
                # Wenn es ein String ist (z.B. Hardcode-Fallback)
                if isinstance(time_value, str):
                    t = datetime.strptime(time_value, '%H:%M').time()
                    return t.hour * 60 + t.minute
                # Wenn es ein datetime.time Objekt ist (häufiger MySQL-Rückgabewert)
                elif isinstance(time_value, datetime.time):
                    return time_value.hour * 60 + time_value.minute
                # Wenn es ein timedelta Objekt ist
                elif isinstance(time_value, timedelta):
                    return int(time_value.total_seconds() / 60)
                return 0

            s1_min = time_to_minutes(s1_start_val)
            e1_min = time_to_minutes(s1_end_val)
            s2_min = time_to_minutes(s2_start_val)
            e2_min = time_to_minutes(s2_end_val)

            # 3. Endzeit für Schichten, die Mitternacht überschreiten, um 1440 Minuten (24h) erhöhen.
            s1_end_adjusted = e1_min + 1440 if e1_min <= s1_min else e1_min
            s2_end_adjusted = e2_min + 1440 if e2_min <= s2_min else e2_min

            # 4. Die einzelne, robuste Überlappungsprüfung:
            return max(s1_min, s2_min) < min(s1_end_adjusted, s2_end_adjusted)

        except Exception:
            return False

    def clear_understaffing_results(self):
        self.understaffing_result_frame.pack_forget()
        for widget in self.understaffing_result_frame.winfo_children():
            widget.destroy()

    def check_understaffing(self):
        self.clear_understaffing_results()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        daily_counts = get_daily_shift_counts_for_month(year, month)
        shifts_to_check = [s['abbreviation'] for s in get_ordered_shift_abbrevs(include_hidden=True) if
                           s.get('check_for_understaffing')]
        understaffing_found = False
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            date_str = current_date.strftime('%Y-%m-%d')
            min_staffing = self.get_min_staffing_for_date(current_date)
            for shift in shifts_to_check:
                min_req = min_staffing.get(shift)
                if min_req is not None:
                    count = daily_counts.get(date_str, {}).get(shift, 0)
                    if count < min_req:
                        understaffing_found = True
                        shift_name = self.app.shift_types_data.get(shift, {}).get('name', shift)
                        ttk.Label(self.understaffing_result_frame,
                                  text=f"Unterbesetzung am {current_date.strftime('%d.%m.%Y')}: Schicht '{shift_name}' ({shift}) - {count} von {min_req} Mitarbeitern anwesend.",
                                  foreground="red", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        if not understaffing_found:
            ttk.Label(self.understaffing_result_frame, text="Keine Unterbesetzungen gefunden.",
                      foreground="green", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.understaffing_result_frame.pack(fill="x", pady=5)