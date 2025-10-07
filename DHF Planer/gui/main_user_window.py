# gui/main_user_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
from datetime import date, datetime, timedelta
import calendar
import json
import os

from database.db_manager import (
    add_vacation_request, get_requests_by_user,
    get_shifts_for_month, get_ordered_users_for_schedule,
    get_daily_shift_counts_for_month, get_ordered_shift_abbrevs,
    get_all_shift_types, add_wunschfrei_request,
    get_wunschfrei_requests_by_user_for_month,
    get_wunschfrei_requests_for_month, get_unnotified_requests,
    mark_requests_as_notified, get_all_requests_by_user, withdraw_wunschfrei_request
)
from .holiday_manager import HolidayManager

STAFFING_RULES_FILE = 'min_staffing_rules.json'
DEFAULT_RULES = {
    "Colors": {"alert_bg": "#FF5555", "success_bg": "#90EE90", "overstaffed_bg": "#FFFF99"},
    "Mo-Do": {"T.": 1}, "Fr": {"T.": 1, "6": 1}, "Sa-So": {"T.": 2},
    "Holiday": {"T.": 2}, "Daily": {"N.": 2, "24": 2}
}


def load_staffing_rules():
    if os.path.exists(STAFFING_RULES_FILE):
        try:
            with open(STAFFING_RULES_FILE, 'r') as f:
                rules = json.load(f)
                if 'Colors' not in rules:
                    rules['Colors'] = DEFAULT_RULES['Colors']
                return rules
        except json.JSONDecodeError:
            return DEFAULT_RULES
    return DEFAULT_RULES


class MainUserWindow(tk.Toplevel):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.master = master
        self.user_data = user_data
        self.wunschfrei_data_store = {}

        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name}")
        self.geometry("1200x800")
        self.state("zoomed")

        self.current_display_date = date.today()
        self.shift_types_data = {}
        self.shift_schedule_data = {}
        self.staffing_rules = load_staffing_rules()
        self.current_year_holidays = {}
        self._load_holidays_for_year(self.current_display_date.year)
        self.load_shift_types()

        self.show_archived_var = tk.BooleanVar(value=False)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.create_vacation_tab()
        self.create_wunschfrei_tab()
        self.create_shift_plan_tab()

        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)

        self.after(100, self.check_for_notifications)

    def check_for_notifications(self):
        unnotified = get_unnotified_requests(self.user_data['id'])
        if not unnotified:
            return

        message_lines = ["Sie haben Neuigkeiten zu Ihren 'Wunschfrei'-Anträgen:"]
        notified_ids = []

        for req in unnotified:
            req_date = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            status = req['status']
            reason = req.get('rejection_reason')

            line = f"- Ihr Antrag für den {req_date} wurde {status}."
            if status == 'Abgelehnt' and reason:
                line += f" Grund: {reason}"

            message_lines.append(line)
            notified_ids.append(req['id'])

        messagebox.showinfo("Benachrichtigung", "\n".join(message_lines), parent=self)
        mark_requests_as_notified(notified_ids)

    def _load_holidays_for_year(self, year):
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def get_min_staffing_for_date(self, current_date):
        weekday = current_date.weekday()
        is_holiday_check = self.is_holiday(current_date)
        rules = self.staffing_rules
        min_staffing = {}
        min_staffing.update(rules.get('Daily', {}))
        if is_holiday_check:
            min_staffing.update(rules.get('Holiday', {}))
        elif weekday in [5, 6]:
            min_staffing.update(rules.get('Sa-So', {}))
        elif weekday == 4:
            min_staffing.update(rules.get('Fr', {}))
        elif weekday in [0, 1, 2, 3]:
            min_staffing.update(rules.get('Mo-Do', {}))
        return {k: int(v) for k, v in min_staffing.items() if v is not None and str(v).isdigit()}

    def load_shift_types(self):
        shift_types_list = get_all_shift_types()
        self.shift_types_data = {st['abbreviation']: st for st in shift_types_list}

    def get_contrast_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def create_vacation_tab(self):
        vacation_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(vacation_frame, text="Mein Urlaub")
        self.remaining_vacation_days = self.user_data.get('urlaub_rest', 0)
        info_frame = ttk.LabelFrame(vacation_frame, text="Meine Übersicht", padding="10")
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text=f"Verfügbare Urlaubstage: {self.remaining_vacation_days}",
                  font=("Arial", 12, "bold")).pack()
        request_frame = ttk.LabelFrame(vacation_frame, text="Neuen Urlaub beantragen", padding="10")
        request_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(request_frame, text="Erster Urlaubstag:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.start_date_entry = DateEntry(request_frame, date_pattern='dd.mm.yyyy', mindate=date.today(),
                                          foreground="black", headersforeground="black")
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(request_frame, text="Letzter Urlaubstag:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.end_date_entry = DateEntry(request_frame, date_pattern='dd.mm.yyyy', mindate=date.today(),
                                        foreground="black", headersforeground="black")
        self.end_date_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(request_frame, text="Antrag stellen", command=self.submit_request).grid(row=2, column=0,
                                                                                           columnspan=2, pady=10)
        status_frame = ttk.LabelFrame(vacation_frame, text="Meine Anträge", padding="10")
        status_frame.pack(fill="both", expand=True)
        columns = ("start_date", "end_date", "status")
        self.tree = ttk.Treeview(status_frame, columns=columns, show="headings")
        self.tree.heading("start_date", text="Von")
        self.tree.heading("end_date", text="Bis")
        self.tree.heading("status", text="Status")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("genehmigt", background="lightgreen")
        self.tree.tag_configure("ausstehend", background="khaki")
        self.tree.tag_configure("abgelehnt", background="lightcoral")
        self.load_requests()

    def load_requests(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        requests = get_requests_by_user(self.user_data['id'])
        for req in requests:
            start_date_obj = datetime.strptime(req['start_date'], '%Y-%m-%d')
            end_date_obj = datetime.strptime(req['end_date'], '%Y-%m-%d')
            display_values = (start_date_obj.strftime('%d.%m.%Y'), end_date_obj.strftime('%d.%m.%Y'), req['status'])
            status_tag = req['status'].lower()
            self.tree.insert("", tk.END, values=display_values, tags=(status_tag,))

    def submit_request(self):
        start_date = self.start_date_entry.get_date()
        end_date = self.end_date_entry.get_date()
        if start_date > end_date:
            messagebox.showwarning("Fehler", "Das Startdatum muss vor dem Enddatum liegen.", parent=self)
            return
        success = add_vacation_request(self.user_data['id'], start_date, end_date)
        if success:
            messagebox.showinfo("Erfolg", f"Ihr Antrag wurde erfolgreich eingereicht.", parent=self)
            self.load_requests()
        else:
            messagebox.showerror("Fehler", "Ihr Antrag konnte nicht gespeichert werden.", parent=self)

    def create_wunschfrei_tab(self):
        frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(frame, text="Meine Wunschfrei-Anträge")

        main_pane = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        main_pane.pack(fill="both", expand=True)

        status_frame = ttk.LabelFrame(main_pane, text="Übersicht", padding="10")
        main_pane.add(status_frame, weight=3)

        tree_frame = ttk.Frame(status_frame)
        tree_frame.pack(fill="both", expand=True)

        columns = ("date", "status")
        self.wunschfrei_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.wunschfrei_tree.heading("date", text="Datum")
        self.wunschfrei_tree.heading("status", text="Status")
        self.wunschfrei_tree.pack(fill="both", expand=True, side="left")

        self.wunschfrei_tree.tag_configure("Genehmigt", background="lightgreen")
        self.wunschfrei_tree.tag_configure("Ausstehend", background="orange")
        self.wunschfrei_tree.tag_configure("Abgelehnt", background="lightcoral")

        button_frame = ttk.Frame(tree_frame)
        button_frame.pack(side="left", fill="y", padx=10)
        ttk.Button(button_frame, text="Antrag zurückziehen", command=self.withdraw_selected_request).pack(pady=5)

        archive_check = ttk.Checkbutton(status_frame, text="Archivierte Anträge anzeigen",
                                        variable=self.show_archived_var, command=self.refresh_wunschfrei_tab)
        archive_check.pack(anchor="w", pady=(10, 0))

        detail_frame = ttk.LabelFrame(main_pane, text="Details", padding="10")
        main_pane.add(detail_frame, weight=1)

        self.rejection_reason_var = tk.StringVar()
        ttk.Label(detail_frame, text="Ablehnungsgrund:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        reason_label = ttk.Label(detail_frame, textvariable=self.rejection_reason_var, wraplength=400,
                                 font=("Segoe UI", 10, "italic"))
        reason_label.pack(anchor="w", pady=5, padx=5)

        self.wunschfrei_tree.bind("<<TreeviewSelect>>", self.on_wunschfrei_selected)
        self.refresh_wunschfrei_tab()

    def on_wunschfrei_selected(self, event=None):
        self.rejection_reason_var.set("")
        selection = self.wunschfrei_tree.selection()
        if not selection:
            return

        request_id = int(selection[0])
        request_data = self.wunschfrei_data_store.get(request_id)

        if request_data and request_data['status'] == 'Abgelehnt':
            reason = request_data.get('rejection_reason') or "Kein Grund angegeben."
            self.rejection_reason_var.set(reason)

    def refresh_wunschfrei_tab(self):
        for item in self.wunschfrei_tree.get_children():
            self.wunschfrei_tree.delete(item)

        self.rejection_reason_var.set("")
        self.wunschfrei_data_store.clear()

        show_all = self.show_archived_var.get()
        requests = get_all_requests_by_user(self.user_data['id'])

        for req in requests:
            self.wunschfrei_data_store[req['id']] = req
            if not show_all and req['status'] != 'Ausstehend':
                continue

            date_obj = datetime.strptime(req['request_date'], '%Y-%m-%d')
            display_values = (date_obj.strftime('%d.%m.%Y'), req['status'])
            self.wunschfrei_tree.insert("", tk.END, iid=req['id'], values=display_values, tags=(req['status'],))

    def withdraw_selected_request(self):
        selection = self.wunschfrei_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Antrag zum Zurückziehen aus.", parent=self)
            return

        request_id = int(selection[0])
        item = self.wunschfrei_tree.item(request_id)
        status = item['values'][1]

        if status not in ['Ausstehend', 'Genehmigt']:
            messagebox.showwarning("Aktion nicht möglich",
                                   "Nur ausstehende oder bereits genehmigte Anträge können zurückgezogen werden.",
                                   parent=self)
            return

        msg = "Möchten Sie diesen Antrag wirklich zurückziehen?"
        if status == 'Genehmigt':
            msg += "\n\nIhr Dienstplan wird für diesen Tag geleert und der Admin informiert."

        if messagebox.askyesno("Bestätigen", msg, parent=self):
            success, message = withdraw_wunschfrei_request(request_id, self.user_data['id'])
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.refresh_wunschfrei_tab()
                self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def create_shift_plan_tab(self):
        self.plan_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.plan_tab_frame, text="Schichtplan")
        main_view_container = ttk.Frame(self.plan_tab_frame)
        main_view_container.pack(fill="both", expand=True)
        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))
        prev_button = ttk.Button(nav_frame, text="< Voriger Monat", command=self.show_previous_month)
        prev_button.pack(side="left")
        self.month_label_var = tk.StringVar()
        month_label = ttk.Label(nav_frame, textvariable=self.month_label_var, font=("Segoe UI", 14, "bold"),
                                anchor="center")
        month_label.pack(side="left", expand=True, fill="x")
        next_button = ttk.Button(nav_frame, text="Nächster Monat >", command=self.show_next_month)
        next_button.pack(side="right")
        grid_container_frame = ttk.Frame(main_view_container)
        grid_container_frame.pack(fill="both", expand=True)
        self.vsb = ttk.Scrollbar(grid_container_frame, orient="vertical")
        self.vsb.pack(side="right", fill="y")
        self.hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal")
        self.hsb.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.config(command=self.canvas.yview)
        self.hsb.config(command=self.canvas.xview)
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")
        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def on_wunschfrei_cell_click(self, event, user_id_in_row, day, year, month):
        if user_id_in_row != self.user_data['id']:
            return

        request_date = date(year, month, day)
        if request_date < date.today():
            messagebox.showwarning("Aktion nicht erlaubt",
                                   "Sie können nur für zukünftige Tage 'Wunschfrei' beantragen.", parent=self)
            return

        month_name = date(year, month, 1).strftime('%B')
        request_count = get_wunschfrei_requests_by_user_for_month(self.user_data['id'], year, month)
        if request_count >= 3:
            messagebox.showwarning("Limit erreicht",
                                   f"Sie haben bereits das Maximum von 3 'Wunschfrei'-Anfragen für {month_name} {year} erreicht.",
                                   parent=self)
            return

        if messagebox.askyesno("Bestätigen",
                               f"Möchten Sie für den {request_date.strftime('%d.%m.%Y')} 'Wunschfrei' beantragen?\n\nSie haben noch {3 - request_count} Anfrage(n) für diesen Monat frei.",
                               parent=self):
            success, message = add_wunschfrei_request(self.user_data['id'], request_date.strftime('%Y-%m-%d'))
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.build_shift_plan_grid(year, month)
                self.refresh_wunschfrei_tab()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def build_shift_plan_grid(self, year, month):
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        users = get_ordered_users_for_schedule(include_hidden=False)
        self.shift_schedule_data = get_shifts_for_month(year, month)
        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
        daily_counts = get_daily_shift_counts_for_month(year, month)
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        color_map = {"URLAUB": "mediumseagreen", "KRANK": "lightcoral", "FREI": "white", "WF": "orange",
                     "X": "lightgreen"}
        for abbrev, data in self.shift_types_data.items():
            color_map[abbrev] = data.get('color', '#FFFFFF')
        month_name = date(year, month, 1).strftime('%B')
        self.month_label_var.set(f"{month_name.capitalize()} {year}")
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        days_in_month = calendar.monthrange(year, month)[1]
        header_bg, weekend_bg = "#E0E0E0", "#F0F0F0"
        summary_bg = "#D0D0FF"
        color_rules = self.staffing_rules.get('Colors', DEFAULT_RULES['Colors'])
        alert_bg, success_bg, overstaffed_bg = color_rules.get('alert_bg'), color_rules.get(
            'success_bg'), color_rules.get('overstaffed_bg')
        MIN_NAME_WIDTH, MIN_DOG_WIDTH = 150, 100
        ttk.Label(self.plan_grid_frame, text="Mitarbeiter", font=("Segoe UI", 10, "bold"), background=header_bg,
                  padding=5, borderwidth=1, relief="solid", foreground="black").grid(row=0, column=0, columnspan=2,
                                                                                     sticky="nsew")
        ttk.Label(self.plan_grid_frame, text="Name", font=("Segoe UI", 9, "bold"), background=header_bg, padding=5,
                  borderwidth=1, relief="solid", foreground="black").grid(row=1, column=0, sticky="nsew")
        ttk.Label(self.plan_grid_frame, text="Diensthund", font=("Segoe UI", 9, "bold"), background=header_bg,
                  padding=5, borderwidth=1, relief="solid", foreground="black").grid(row=1, column=1, sticky="nsew")
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_abbr = day_map[current_date.weekday()]
            is_weekend = current_date.weekday() >= 5
            is_holiday_check = self.is_holiday(current_date)
            bg = weekend_bg if is_weekend else header_bg
            if is_holiday_check: bg = "#FFD700"
            if is_weekend or is_holiday_check:
                frame_h1 = tk.Frame(self.plan_grid_frame, bg="blue")
                frame_h1.grid(row=0, column=day + 1, sticky="nsew")
                ttk.Label(frame_h1, text=day_abbr, font=("Segoe UI", 9, "bold"), background=bg, padding=5,
                          anchor="center", foreground="black").pack(fill="both", expand=True, padx=1, pady=1)
                frame_h2 = tk.Frame(self.plan_grid_frame, bg="blue")
                frame_h2.grid(row=1, column=day + 1, sticky="nsew")
                ttk.Label(frame_h2, text=str(day), font=("Segoe UI", 9), background=bg, padding=5, anchor="center",
                          foreground="black").pack(fill="both", expand=True, padx=1, pady=1)
            else:
                ttk.Label(self.plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), background=bg, padding=5,
                          borderwidth=1, relief="solid", anchor="center", foreground="black").grid(row=0,
                                                                                                   column=day + 1,
                                                                                                   sticky="nsew")
                ttk.Label(self.plan_grid_frame, text=str(day), font=("Segoe UI", 9), background=bg, padding=5,
                          borderwidth=1, relief="solid", anchor="center", foreground="black").grid(row=1,
                                                                                                   column=day + 1,
                                                                                                   sticky="nsew")
        current_row = 2
        for row_idx, user_data_row in enumerate(users):
            user_name = f"{user_data_row['vorname']} {user_data_row['name']}"
            user_dog = user_data_row.get('diensthund', '---')
            user_id_str = str(user_data_row['id'])
            # KORRIGIERTE ZEILE
            ttk.Label(self.plan_grid_frame, text=user_name, font=("Segoe UI", 10, "bold"), padding=5, borderwidth=1,
                      relief="solid", foreground="black", background="white").grid(row=current_row, column=0,
                                                                                   sticky="nsew")
            ttk.Label(self.plan_grid_frame, text=user_dog, font=("Segoe UI", 10), padding=5, borderwidth=1,
                      relief="solid", foreground="black", anchor="center", background="white").grid(row=current_row,
                                                                                                    column=1,
                                                                                                    sticky="nsew")
            for day in range(1, days_in_month + 1):
                col_idx = day + 1
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str, "")

                wunschfrei_status = wunschfrei_data.get(user_id_str, {}).get(date_str)
                if wunschfrei_status == 'Ausstehend':
                    shift = 'WF'
                elif wunschfrei_status == 'Genehmigt':
                    shift = 'X'

                bg_color, text_color = color_map.get(shift, "white"), self.get_contrast_color(
                    color_map.get(shift, "white"))
                is_weekend, is_holiday_check = current_date.weekday() >= 5, self.is_holiday(current_date)
                cursor_type = "hand2" if user_data_row['id'] == self.user_data['id'] else ""

                if is_weekend or is_holiday_check:
                    cell_frame = tk.Frame(self.plan_grid_frame, bg="blue")
                    cell_frame.grid(row=current_row, column=col_idx, sticky="nsew")
                    label = ttk.Label(cell_frame, text=shift, background=bg_color, padding=5, anchor="center",
                                      foreground=text_color, cursor=cursor_type)
                    label.pack(fill="both", expand=True, padx=1, pady=1)
                    label.bind("<Button-1>",
                               lambda e, uid=user_data_row['id'], d=day, y=year, m=month: self.on_wunschfrei_cell_click(
                                   e, uid, d, y, m))
                    cell_frame.bind("<Button-1>", lambda e, uid=user_data_row['id'], d=day, y=year,
                                                         m=month: self.on_wunschfrei_cell_click(e, uid, d, y, m))
                else:
                    label = ttk.Label(self.plan_grid_frame, text=shift, background=bg_color, padding=5, borderwidth=1,
                                      relief="solid", anchor="center", foreground=text_color, cursor=cursor_type)
                    label.grid(row=current_row, column=col_idx, sticky="nsew")
                    label.bind("<Button-1>",
                               lambda e, uid=user_data_row['id'], d=day, y=year, m=month: self.on_wunschfrei_cell_click(
                                   e, uid, d, y, m))
            current_row += 1
        ttk.Label(self.plan_grid_frame, text="", background=header_bg, padding=2, borderwidth=0).grid(row=current_row,
                                                                                                      column=0,
                                                                                                      columnspan=days_in_month + 2,
                                                                                                      sticky="nsew")
        current_row += 1
        ttk.Label(self.plan_grid_frame, text="Tageszählungen und Mindestbesetzung", font=("Segoe UI", 10, "bold"),
                  background=header_bg, padding=5, borderwidth=1, relief="solid", foreground="black").grid(
            row=current_row, column=0, columnspan=days_in_month + 2, sticky="nsew")
        current_row += 1
        for item in ordered_abbrevs_to_show:
            abbrev, name_text = item['abbreviation'], item.get('name', 'N/A')
            ttk.Label(self.plan_grid_frame, text=abbrev, font=("Segoe UI", 9, "bold"), padding=5, borderwidth=1,
                      relief="solid", anchor="center", background=summary_bg, foreground="black").grid(row=current_row,
                                                                                                       column=0,
                                                                                                       sticky="nsew")
            ttk.Label(self.plan_grid_frame, text=name_text, font=("Segoe UI", 9), padding=5, borderwidth=1,
                      relief="solid", anchor="w", background=summary_bg, foreground="black").grid(row=current_row,
                                                                                                  column=1,
                                                                                                  sticky="nsew")
            for day in range(1, days_in_month + 1):
                col_idx = day + 1
                current_date = date(year, month, day)
                count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                min_required = self.get_min_staffing_for_date(current_date).get(abbrev)
                bg, text_color = summary_bg, "black"
                if min_required is not None:
                    if count < min_required:
                        bg, text_color = alert_bg, "white"
                    elif count > min_required:
                        bg, text_color = overstaffed_bg, "black"
                    else:
                        bg, text_color = success_bg, "black"
                display_text = f"{count}/{min_required}" if min_required is not None else str(count)
                is_weekend, is_holiday_check = current_date.weekday() >= 5, self.is_holiday(current_date)
                if is_weekend or is_holiday_check:
                    summary_frame = tk.Frame(self.plan_grid_frame, bg="blue")
                    summary_frame.grid(row=current_row, column=col_idx, sticky="nsew")
                    ttk.Label(summary_frame, text=display_text, background=bg, padding=5, anchor="center",
                              foreground=text_color).pack(fill="both", expand=True, padx=1, pady=1)
                else:
                    ttk.Label(self.plan_grid_frame, text=display_text, background=bg, padding=5, borderwidth=1,
                              relief="solid", anchor="center", foreground=text_color).grid(row=current_row,
                                                                                           column=col_idx,
                                                                                           sticky="nsew")
            current_row += 1
        self.plan_grid_frame.grid_columnconfigure(0, weight=0, minsize=MIN_NAME_WIDTH)
        self.plan_grid_frame.grid_columnconfigure(1, weight=0, minsize=MIN_DOG_WIDTH)
        for day_col in range(2, days_in_month + 2): self.plan_grid_frame.grid_columnconfigure(day_col, weight=1)
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def show_previous_month(self):
        current_year, current_month = self.current_display_date.year, self.current_display_date.month
        prev_month, prev_year = (current_month - 1, current_year) if current_month > 1 else (12, current_year - 1)
        if prev_year != current_year: self._load_holidays_for_year(prev_year)
        self.current_display_date = date(prev_year, prev_month, 1)
        self.build_shift_plan_grid(prev_year, prev_month)
        self.refresh_wunschfrei_tab()

    def show_next_month(self):
        current_year, current_month = self.current_display_date.year, self.current_display_date.month
        next_month, next_year = (current_month + 1, current_year) if current_month < 12 else (1, current_year + 1)
        if next_year != current_year: self._load_holidays_for_year(next_year)
        self.current_display_date = date(next_year, next_month, 1)
        self.build_shift_plan_grid(next_year, next_month)
        self.refresh_wunschfrei_tab()