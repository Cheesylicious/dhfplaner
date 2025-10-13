import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
import calendar
import webbrowser
import os
import tempfile

from database.db_shifts import get_shifts_for_month, get_daily_shift_counts_for_month, get_ordered_shift_abbrevs, save_shift_entry
from database.db_requests import get_wunschfrei_requests_for_month, get_wunschfrei_request_by_user_and_date, get_all_vacation_requests_for_month, admin_submit_request
from database.db_users import get_ordered_users_for_schedule
from gui.admin_menu_config_manager import AdminMenuConfigManager
from ..request_lock_manager import RequestLockManager


class ShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_widgets = {}
        self.violation_cells = set()
        self.current_user_order = []
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.setup_ui()
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

        ttk.Button(nav_frame, text="📄 Drucken", command=self.print_shift_plan).pack(side="left", padx=20)

        self.month_label_var = tk.StringVar()
        month_label_frame = ttk.Frame(nav_frame)
        month_label_frame.pack(side="left", expand=True, fill="x")

        ttk.Label(month_label_frame, textvariable=self.month_label_var, font=("Segoe UI", 14, "bold"),
                  anchor="center").pack()
        self.lock_status_label = ttk.Label(month_label_frame, text="", font=("Segoe UI", 10, "italic"), anchor="center")
        self.lock_status_label.pack()

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

        def _configure_inner_frame(event):
            self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame)
        self.inner_frame.bind('<Configure>', _configure_scrollregion)
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)

        footer_frame = ttk.Frame(main_view_container)
        footer_frame.pack(fill="x", pady=10)

        check_frame = ttk.Frame(footer_frame)
        check_frame.pack(side="left")

        ttk.Button(check_frame, text="Schichtplan Prüfen", command=self.check_understaffing).pack(side="left", padx=5)
        ttk.Button(check_frame, text="Leeren", command=self.clear_understaffing_results).pack(side="left", padx=5)

        self.lock_button = ttk.Button(footer_frame, text="", command=self.toggle_month_lock)
        self.lock_button.pack(side="right", padx=5)

        self.understaffing_result_frame = ttk.Frame(main_view_container, padding="10")

    def print_shift_plan(self):
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        # --- KORREKTUR: Der Parameter 'include_hidden' wird hier entfernt ---
        users = get_ordered_users_for_schedule()
        shifts_data = get_shifts_for_month(year, month)
        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
        processed_vacations = self._process_vacations(year, month)
        month_name = self.month_label_var.get()
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")

        html = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>Dienstplan {month_name}</title>
            <style>
                body {{ font-family: Segoe UI, Arial, sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
                th, td {{ border: 1px solid #ccc; padding: 6px; text-align: center; }}
                th {{ background-color: #E0E0E0; }}
                .weekend {{ background-color: {weekend_bg}; }}
                .holiday {{ background-color: {holiday_bg}; }}
                .name-col {{ text-align: left; font-weight: bold; width: 140px; }}
                .dog-col {{ text-align: left; width: 90px; }}
                .hours-col {{ font-weight: bold; width: 40px; }}
            </style>
        </head>
        <body>
            <h1>Dienstplan für {month_name}</h1>
            <table>
                <thead>
                    <tr>
                        <th class="name-col">Name</th>
                        <th class="dog-col">Diensthund</th>
        """

        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_class = ""
            if self.app.is_holiday(current_date):
                day_class = "holiday"
            elif current_date.weekday() >= 5:
                day_class = "weekend"
            html += f'<th class="{day_class}">{day}<br>{day_map[current_date.weekday()]}</th>'

        html += '<th class="hours-col">Std.</th>'
        html += """
                </tr>
            </thead>
            <tbody>
        """

        for user in users:
            user_id_str = str(user['id'])
            total_hours = self._calculate_total_hours_for_user(user_id_str, year, month)
            html += f"""
                <tr>
                    <td class="name-col">{user['vorname']} {user['name']}</td>
                    <td class="dog-col">{user.get('diensthund', '---')}</td>
            """
            for day in range(1, days_in_month + 1):
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')

                display_text = shifts_data.get(user_id_str, {}).get(date_str, "&nbsp;")
                vacation_status = processed_vacations.get(user_id_str, {}).get(current_date)
                if vacation_status == 'Genehmigt': display_text = 'U'

                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)
                if request_info and ("Akzeptiert" in request_info[0] or "Genehmigt" in request_info[0]) and \
                        request_info[1] == 'WF':
                    display_text = 'X'

                bg_color = ""
                is_weekend = current_date.weekday() >= 5
                is_holiday = self.app.is_holiday(current_date)

                if is_holiday:
                    bg_color = holiday_bg
                elif is_weekend:
                    bg_color = weekend_bg

                shift_data = self.app.shift_types_data.get(display_text)

                if shift_data and shift_data.get('color'):
                    if display_text in ["U", "X", "EU"]:
                        bg_color = shift_data['color']
                    elif not is_holiday and not is_weekend:
                        bg_color = shift_data['color']

                text_color = self.app.get_contrast_color(bg_color) if bg_color else "black"
                html += f'<td style="background-color: {bg_color or "white"}; color: {text_color};">{display_text}</td>'

            html += f'<td class="hours-col">{total_hours}</td></tr>'

        html += """
            </tbody>
        </table>
        </body>
        </html>
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
                f.write(html)
                filepath = f.name

            webbrowser.open(f"file://{os.path.realpath(filepath)}")
            messagebox.showinfo("Drucken",
                                "Der Dienstplan wurde in deinem Webbrowser geöffnet.\n\nBitte nutze dort die Druckfunktion (normalerweise Strg+P oder Cmd+P).",
                                parent=self)
        except Exception as e:
            messagebox.showerror("Fehler", f"Der Plan konnte nicht zum Drucken geöffnet werden:\n{e}", parent=self)

    def build_shift_plan_grid(self, year, month):
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
        self.update_lock_status()
        self.processed_vacations = self._process_vacations(year, month)
        # --- KORREKTUR: Der Parameter 'include_hidden' wird hier entfernt ---
        self.current_user_order = get_ordered_users_for_schedule()
        self.shift_schedule_data = get_shifts_for_month(year, month)
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
            is_weekend = current_date.weekday() >= 5
            is_holiday = self.app.is_holiday(current_date)
            event_type = self.app.get_event_type(current_date)

            bg = header_bg
            if is_holiday:
                bg = holiday_bg
            elif event_type == "Quartals Ausbildung":
                bg = ausbildung_bg
            elif event_type == "Schießen":
                bg = schiessen_bg
            elif is_weekend:
                bg = weekend_bg

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
            total_hours = self._calculate_total_hours_for_user(user_id_str, year, month)
            for day in range(1, days_in_month + 1):
                current_date_obj = date(year, month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')
                vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date_obj)
                shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str, "")
                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)
                display_text = shift
                if vacation_status == 'Genehmigt':
                    display_text = 'U'
                elif vacation_status == 'Ausstehend':
                    display_text = "U?"
                elif request_info:
                    status, requested_shift, requested_by = request_info
                    if status == 'Ausstehend':
                        if requested_by == 'admin':
                            display_text = f"{requested_shift} (A)?"
                        else:
                            display_text = 'WF' if requested_shift == 'WF' else f"{requested_shift}?"
                    elif "Akzeptiert" in status or "Genehmigt" in status:
                        if requested_shift == 'WF':
                            display_text = 'X'
                frame = tk.Frame(self.plan_grid_frame, bd=1, relief="solid")
                frame.grid(row=current_row, column=day + 1, sticky="nsew")
                label = tk.Label(frame, text=display_text, font=("Segoe UI", 10))
                label.pack(expand=True, fill="both")
                is_admin_request = request_info and request_info[2] == 'admin' and request_info[0] == 'Ausstehend'
                label.bind("<Button-1>",
                           lambda e, uid=user_id, d=day, y=year, m=month: self.on_grid_cell_click(e, uid, d, y, m))
                if '?' in display_text or display_text == 'WF' or is_admin_request:
                    label.bind("<Button-3>",
                               lambda e, uid=user_id, dt=date_str: self.show_wunschfrei_context_menu(e, uid, dt))
                self.grid_widgets['cells'][user_id_str][day] = {'frame': frame, 'label': label}
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
                current_date = date(year, month, day)
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)
                display_text = ""
                if not (abbrev == "6" and (not is_friday or is_holiday)):
                    count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                    min_required = self.get_min_staffing_for_date(current_date).get(abbrev)
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
        self.update_violation_set()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        pending_color = rules.get('Ausstehend', 'orange')
        admin_pending_color = rules.get('Admin_Ausstehend', '#E0B0FF')
        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
        for user in self.current_user_order:
            user_id, user_id_str = user['id'], str(user['id'])
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
                request_info = wunschfrei_data.get(user_id_str, {}).get(current_date.strftime('%Y-%m-%d'))

                bg_color = "white"
                if is_holiday:
                    bg_color = holiday_bg
                elif is_weekend:
                    bg_color = weekend_bg

                if shift_data and shift_data.get('color'):
                    if shift_abbrev in ["U", "X", "EU"]:
                        bg_color = shift_data['color']
                    elif not is_holiday and not is_weekend:
                        bg_color = shift_data['color']

                if vacation_status == 'Ausstehend':
                    bg_color = pending_color
                elif request_info and request_info[0] == 'Ausstehend':
                    if request_info[2] == 'admin':
                        bg_color = admin_pending_color
                    else:
                        bg_color = pending_color

                fg_color = self.app.get_contrast_color(bg_color)
                if (user_id, day) in self.violation_cells:
                    bg_color = "#FF5555"
                    fg_color = "white"
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

    def show_previous_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        self.app.current_display_date = last_day_of_previous_month.replace(day=1)
        if current_date.year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(self.app.current_display_date.year)
            self.app._load_events_for_year(self.app.current_display_date.year)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def show_next_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        first_day_of_next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        self.app.current_display_date = first_day_of_next_month
        if current_date.year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(self.app.current_display_date.year)
            self.app._load_events_for_year(self.app.current_display_date.year)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def on_grid_cell_click(self, event, user_id, day, year, month):
        shift_date_str = date(year, month, day).strftime('%Y-%m-%d')
        request = get_wunschfrei_request_by_user_and_date(user_id, shift_date_str)
        if request and request['status'] == 'Ausstehend' and request['requested_by'] == 'user':
            return
        current_shift = event.widget.cget("text")
        context_menu = tk.Menu(self, tearoff=0)
        context_menu.add_command(label="FREI (Dienst entfernen)",
                                 command=lambda: self._save_shift_and_update_ui(user_id, shift_date_str, current_shift,
                                                                                ""))
        context_menu.add_separator()
        anfragen_menu = tk.Menu(context_menu, tearoff=0)
        context_menu.add_cascade(label="Anfragen", menu=anfragen_menu)
        all_abbrevs = list(self.app.shift_types_data.keys())
        menu_config = AdminMenuConfigManager.load_config(all_abbrevs)
        sorted_abbrevs = sorted(all_abbrevs, key=lambda s: self.app.shift_frequency.get(s, 0), reverse=True)
        for abbrev in sorted_abbrevs:
            if menu_config.get(abbrev, True):
                name = self.app.shift_types_data[abbrev].get('name', abbrev)
                count = self.app.shift_frequency.get(abbrev, 0)
                label_text = f"{abbrev} ({name})" + (f"  (Bisher {count}x)" if count > 0 else "")
                context_menu.add_command(label=label_text,
                                         command=lambda s=abbrev: self._save_shift_and_update_ui(user_id,
                                                                                                 shift_date_str,
                                                                                                 current_shift, s))
                anfragen_menu.add_command(label=label_text,
                                          command=lambda s=abbrev: self._admin_request_shift(user_id, shift_date_str,
                                                                                             s))
        context_menu.post(event.x_root, event.y_root)

    def _admin_request_shift(self, user_id, shift_date_str, shift_abbrev):
        success, message = admin_submit_request(user_id, shift_date_str, shift_abbrev)
        if success:
            messagebox.showinfo("Anfrage gesendet", message, parent=self.app)
            self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)
        else:
            messagebox.showerror("Fehler", message, parent=self.app)

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

            if "Teilnahmen" in self.app.tab_frames:
                self.app.tab_frames["Teilnahmen"].refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self.app)

    def _update_ui_after_change(self, user_id, date_str, old_shift, new_shift):
        year, month, day = map(int, date_str.split('-'))
        user_id_str = str(user_id)
        cell_widgets = self.grid_widgets['cells'][user_id_str][day]
        cell_widgets['label'].config(text=new_shift)
        self._update_user_total_hours(user_id_str)
        self._update_daily_counts_for_day(day, old_shift, new_shift)
        self.apply_grid_colors()

    def _calculate_total_hours_for_user(self, user_id_str, year, month):
        total_hours = 0
        days_in_month = calendar.monthrange(year, month)[1]
        prev_month_date = date(year, month, 1) - timedelta(days=1)
        prev_month_shifts = get_shifts_for_month(prev_month_date.year, prev_month_date.month)
        prev_month_last_day_str = prev_month_date.strftime('%Y-%m-%d')
        if prev_month_shifts.get(user_id_str, {}).get(prev_month_last_day_str) == 'N.':
            total_hours += 6
        user_shifts = self.shift_schedule_data.get(user_id_str, {})
        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            shift = user_shifts.get(date_str, "")
            if shift in self.app.shift_types_data:
                hours = self.app.shift_types_data[shift].get('hours', 0)
                if shift == 'N.' and day == days_in_month:
                    hours = 6
                total_hours += hours
        return total_hours

    def _update_user_total_hours(self, user_id_str):
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        total_hours = self._calculate_total_hours_for_user(user_id_str, year, month)
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
        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            dog_schedule = {}
            for user in self.current_user_order:
                dog = user.get('diensthund')
                if dog and dog != '---':
                    shift = self.shift_schedule_data.get(str(user['id']), {}).get(date_str)
                    if shift:
                        if dog not in dog_schedule: dog_schedule[dog] = []
                        dog_schedule[dog].append((user['id'], shift))
            for dog, assignments in dog_schedule.items():
                if len(assignments) > 1:
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            if self._check_time_overlap(assignments[i][1], assignments[j][1]):
                                self.violation_cells.add((assignments[i][0], day))
                                self.violation_cells.add((assignments[j][0], day))

    def _check_time_overlap(self, shift1_abbrev, shift2_abbrev):
        s1_data = self.app.shift_types_data.get(shift1_abbrev)
        s2_data = self.app.shift_types_data.get(shift2_abbrev)
        if not all([s1_data, s2_data, s1_data.get('start_time'), s1_data.get('end_time'), s2_data.get('start_time'),
                    s2_data.get('end_time')]):
            return False
        try:
            s1 = datetime.strptime(s1_data['start_time'], '%H:%M').time()
            e1 = datetime.strptime(s1_data['end_time'], '%H:%M').time()
            s2 = datetime.strptime(s2_data['start_time'], '%H:%M').time()
            e2 = datetime.strptime(s2_data['end_time'], '%H:%M').time()
            s1_min = s1.hour * 60 + s1.minute
            e1_min = e1.hour * 60 + e1.minute
            s2_min = s2.hour * 60 + s2.minute
            e2_min = e2.hour * 60 + e2.minute
            if e1_min <= s1_min: e1_min += 24 * 60
            if e2_min <= s2_min: e2_min += 24 * 60
            return max(s1_min, s2_min) < min(e1_min, e2_min)
        except (ValueError, TypeError):
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

    def update_lock_status(self):
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)

        s = ttk.Style()
        s.configure("Lock.TButton", background="red", foreground="white", font=('Segoe UI', 9, 'bold'))
        s.map("Lock.TButton", background=[('active', '#CC0000')])
        s.configure("Unlock.TButton", background="green", foreground="white", font=('Segoe UI', 9, 'bold'))
        s.map("Unlock.TButton", background=[('active', '#006400')])

        if is_locked:
            self.lock_status_label.config(text="(Für Anträge gesperrt)", foreground="red")
            self.lock_button.config(text="Monat entsperren", style="Unlock.TButton")
        else:
            self.lock_status_label.config(text="")
            self.lock_button.config(text="Monat für Anträge sperren", style="Lock.TButton")

    def toggle_month_lock(self):
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)

        locks = RequestLockManager.load_locks()
        lock_key = f"{year}-{month:02d}"

        if is_locked:
            if lock_key in locks:
                del locks[lock_key]
        else:
            locks[lock_key] = True

        if RequestLockManager.save_locks(locks):
            self.app.refresh_antragssperre_views()
        else:
            messagebox.showerror("Fehler", "Der Status konnte nicht gespeichert werden.", parent=self)