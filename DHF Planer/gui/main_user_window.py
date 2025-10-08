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
    get_all_shift_types, submit_user_request,
    get_wunschfrei_requests_by_user_for_month,
    get_wunschfrei_requests_for_month, get_unnotified_requests,
    mark_requests_as_notified, get_all_requests_by_user, withdraw_wunschfrei_request,
    get_unnotified_bug_reports_for_user, mark_bug_reports_as_notified
)
from .holiday_manager import HolidayManager
from .request_config_manager import RequestConfigManager
from .dialogs.bug_report_dialog import BugReportDialog

STAFFING_RULES_FILE = 'min_staffing_rules.json'
USER_TAB_ORDER_FILE = 'user_tab_order_config.json'

DEFAULT_RULES = {
    "Colors": {"alert_bg": "#FF5555", "success_bg": "#90EE90", "overstaffed_bg": "#FFFF99"},
    "Mo-Do": {"T.": 1}, "Fr": {"T.": 1, "6": 1}, "Sa-So": {"T.": 2},
    "Holiday": {"T.": 2}, "Daily": {"N.": 2, "24": 2}
}


class TabOrderManager:
    """Verwaltet die Reihenfolge der Reiter im Benutzer-Fenster."""
    DEFAULT_ORDER = ["Schichtplan", "Meine Anfragen", "Mein Urlaub"]

    @staticmethod
    def load_order():
        if not os.path.exists(USER_TAB_ORDER_FILE):
            TabOrderManager.save_order(TabOrderManager.DEFAULT_ORDER)
            return TabOrderManager.DEFAULT_ORDER
        try:
            with open(USER_TAB_ORDER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return TabOrderManager.DEFAULT_ORDER

    @staticmethod
    def save_order(order_list):
        try:
            with open(USER_TAB_ORDER_FILE, 'w', encoding='utf-8') as f:
                json.dump(order_list, f, indent=4)
            return True
        except IOError:
            return False


class TabOrderWindow(tk.Toplevel):
    """Fenster zum Anpassen der Reiter-Reihenfolge."""

    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Reiter-Reihenfolge anpassen")
        self.geometry("400x500")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Ändern Sie die Reihenfolge der Reiter im Hauptfenster.").pack(anchor="w",
                                                                                                  pady=(0, 10))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.tab_listbox = tk.Listbox(list_frame, selectmode="single")
        self.tab_listbox.grid(row=0, column=0, sticky="nsew")

        button_subframe = ttk.Frame(list_frame)
        button_subframe.grid(row=0, column=1, sticky="ns", padx=(10, 0))

        ttk.Button(button_subframe, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(pady=2, fill="x")
        ttk.Button(button_subframe, text="↓ Runter", command=lambda: self.move_item(1)).pack(pady=2, fill="x")

        current_order = TabOrderManager.load_order()
        for tab_name in current_order:
            self.tab_listbox.insert(tk.END, tab_name)

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(15, 0))
        button_bar.columnconfigure((0, 1), weight=1)

        ttk.Button(button_bar, text="Speichern & Schließen", command=self.save_and_close).grid(row=0, column=0,
                                                                                               sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def move_item(self, direction):
        selection = self.tab_listbox.curselection()
        if not selection: return
        idx = selection[0]
        new_idx = idx + direction
        if not (0 <= new_idx < self.tab_listbox.size()): return

        item_text = self.tab_listbox.get(idx)
        self.tab_listbox.delete(idx)
        self.tab_listbox.insert(new_idx, item_text)
        self.tab_listbox.selection_set(new_idx)
        self.tab_listbox.activate(new_idx)

    def save_and_close(self):
        new_order = list(self.tab_listbox.get(0, tk.END))
        if TabOrderManager.save_order(new_order):
            messagebox.showinfo("Gespeichert", "Die Reiter-Reihenfolge wurde aktualisiert.", parent=self)
            self.callback(new_order)
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Die Reihenfolge konnte nicht gespeichert werden.", parent=self)


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

        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        style.configure("Blue.TButton",
                        foreground="black",
                        background="#007bff",
                        font=("Segoe UI", 9, "bold"),
                        bordercolor="#007bff",
                        lightcolor="#007bff",
                        darkcolor="#007bff",
                        padding=5)
        style.map("Blue.TButton",
                  background=[('active', '#0056b3'), ('pressed', '#004085')],
                  foreground=[('active', 'black'), ('pressed', 'black')])

        self.current_display_date = date.today()
        self.shift_types_data = {}
        self.shift_schedule_data = {}
        self.staffing_rules = load_staffing_rules()
        self.current_year_holidays = {}
        self._load_holidays_for_year(self.current_display_date.year)
        self.load_shift_types()

        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Button(header_frame, text="Reiter anpassen", command=self.open_tab_order_window).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.setup_tabs()
        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)

        self.after(100, self.check_for_wunschfrei_notifications)
        self.after(200, self.check_for_bug_report_notifications)

    def setup_footer(self):
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style="Blue.TButton").pack(side="right", padx=10)

    def open_bug_report_dialog(self):
        BugReportDialog(self, self.user_data['id'])

    def open_tab_order_window(self):
        TabOrderWindow(self, self.reorder_tabs)

    def reorder_tabs(self, new_order):
        try:
            selected_tab_name = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            selected_tab_name = None

        all_tabs = {}
        for tab_id in self.notebook.tabs():
            tab_name = self.notebook.tab(tab_id, "text")
            all_tabs[tab_name] = self.notebook.nametowidget(tab_id)

        for tab_id in list(self.notebook.tabs()):
            self.notebook.forget(tab_id)

        for tab_name in new_order:
            if tab_name in all_tabs:
                self.notebook.add(all_tabs[tab_name], text=tab_name)

        if selected_tab_name:
            for i, tab_name in enumerate(new_order):
                if tab_name == selected_tab_name:
                    self.notebook.select(i)
                    break

    def setup_tabs(self):
        self.tab_frames = {
            "Mein Urlaub": self.create_vacation_tab(),
            "Meine Anfragen": self.create_wunschfrei_tab(),
            "Schichtplan": self.create_shift_plan_tab()
        }

        saved_order = TabOrderManager.load_order()
        final_order = []
        existing_tabs = list(self.tab_frames.keys())
        for tab_name in saved_order:
            if tab_name in existing_tabs:
                final_order.append(tab_name)
                existing_tabs.remove(tab_name)
        final_order.extend(existing_tabs)

        for tab_name in final_order:
            frame = self.tab_frames.get(tab_name)
            if frame:
                self.notebook.add(frame, text=tab_name)

    def check_for_bug_report_notifications(self):
        """Prüft auf neue Statusänderungen bei Bug-Reports und benachrichtigt den User."""
        unnotified_reports = get_unnotified_bug_reports_for_user(self.user_data['id'])
        if not unnotified_reports:
            return

        message_lines = ["Es gibt Neuigkeiten zu Ihren Fehlerberichten:"]
        notified_ids = []

        for report in unnotified_reports:
            title = report['title']
            status = report['status']
            line = f"- Ihr Bericht '{title[:30]}...' hat jetzt den Status: {status}."
            message_lines.append(line)
            notified_ids.append(report['id'])

        messagebox.showinfo("Status-Update für Fehlerberichte", "\n".join(message_lines), parent=self)
        mark_bug_reports_as_notified(notified_ids)

    def check_for_wunschfrei_notifications(self):
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
        return vacation_frame

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
        columns = ("date", "request_type", "status")

        # --- Top Section: Pending Requests ---
        pending_frame = ttk.LabelFrame(frame, text="Offene Anträge", padding=10)
        pending_frame.pack(fill="x", expand=False)

        pending_tree_frame = ttk.Frame(pending_frame)
        pending_tree_frame.pack(fill="x", expand=True)

        self.pending_requests_tree = ttk.Treeview(pending_tree_frame, columns=columns, show="headings", height=5)
        self.pending_requests_tree.heading("date", text="Datum")
        self.pending_requests_tree.heading("request_type", text="Anfrage")
        self.pending_requests_tree.heading("status", text="Status")
        self.pending_requests_tree.column("request_type", width=100, anchor="center")
        self.pending_requests_tree.pack(fill="x", expand=True, side="left")
        self.pending_requests_tree.tag_configure("Ausstehend", background="orange")

        pending_button_frame = ttk.Frame(pending_tree_frame)
        pending_button_frame.pack(side="left", fill="y", padx=10)
        self.withdraw_button = ttk.Button(pending_button_frame, text="Zurückziehen",
                                          command=self.withdraw_selected_request)
        self.withdraw_button.pack(pady=5)

        # --- Toggle Button for Archive ---
        self.archive_visible = tk.BooleanVar(value=True)
        self.toggle_archive_button = ttk.Button(frame, text="Archiv ausblenden", command=self.toggle_archive_visibility)
        self.toggle_archive_button.pack(fill="x", pady=10)

        # --- Bottom Section: Processed Requests (Archive) ---
        self.archive_frame = ttk.Frame(frame)
        self.archive_frame.pack(fill="both", expand=True)

        processed_frame = ttk.LabelFrame(self.archive_frame, text="Bearbeitete Anträge (Archiv)", padding=10)
        processed_frame.pack(fill="both", expand=True)

        self.processed_requests_tree = ttk.Treeview(processed_frame, columns=columns, show="headings")
        self.processed_requests_tree.heading("date", text="Datum")
        self.processed_requests_tree.heading("request_type", text="Anfrage")
        self.processed_requests_tree.heading("status", text="Status")
        self.processed_requests_tree.column("request_type", width=100, anchor="center")
        self.processed_requests_tree.pack(fill="both", expand=True)

        self.processed_requests_tree.tag_configure("Genehmigt", background="lightgreen")
        self.processed_requests_tree.tag_configure("Abgelehnt", background="lightcoral")

        # --- Detail View for Rejection Reason ---
        detail_frame = ttk.LabelFrame(frame, text="Details zum abgelehnten Antrag", padding=10)
        detail_frame.pack(fill="x", pady=(10, 0))
        self.rejection_reason_var = tk.StringVar()
        reason_label = ttk.Label(detail_frame, textvariable=self.rejection_reason_var, wraplength=400,
                                 font=("Segoe UI", 10, "italic"))
        reason_label.pack(anchor="w", pady=5, padx=5)

        self.pending_requests_tree.bind("<<TreeviewSelect>>", self.on_wunschfrei_selected)
        self.processed_requests_tree.bind("<<TreeviewSelect>>", self.on_wunschfrei_selected)

        self.refresh_wunschfrei_tab()
        return frame

    def toggle_archive_visibility(self):
        if self.archive_visible.get():
            self.archive_frame.pack_forget()
            self.toggle_archive_button.config(text="Archiv einblenden")
            self.archive_visible.set(False)
        else:
            self.archive_frame.pack(fill="both", expand=True)
            self.toggle_archive_button.config(text="Archiv ausblenden")
            self.archive_visible.set(True)

    def on_wunschfrei_selected(self, event):
        self.rejection_reason_var.set("")

        tree = event.widget
        other_tree = self.processed_requests_tree if tree is self.pending_requests_tree else self.pending_requests_tree
        if other_tree.selection():
            other_tree.selection_remove(other_tree.selection())

        selection = tree.selection()
        if not selection:
            return

        request_id = int(selection[0])
        request_data = self.wunschfrei_data_store.get(request_id)

        if request_data and request_data['status'] == 'Abgelehnt':
            reason = request_data.get('rejection_reason') or "Kein Grund angegeben."
            self.rejection_reason_var.set(reason)

    def refresh_wunschfrei_tab(self):
        for item in self.pending_requests_tree.get_children():
            self.pending_requests_tree.delete(item)
        for item in self.processed_requests_tree.get_children():
            self.processed_requests_tree.delete(item)

        self.rejection_reason_var.set("")
        self.wunschfrei_data_store.clear()

        requests = get_all_requests_by_user(self.user_data['id'])

        for req in requests:
            self.wunschfrei_data_store[req['id']] = req

            date_obj = datetime.strptime(req['request_date'], '%Y-%m-%d')
            request_type_text = req.get('requested_shift', 'Unbekannt')
            if request_type_text == 'WF':
                request_type_text = "Frei"
            display_values = (date_obj.strftime('%d.%m.%Y'), request_type_text, req['status'])

            if req['status'] == 'Ausstehend':
                self.pending_requests_tree.insert("", tk.END, iid=req['id'], values=display_values,
                                                  tags=(req['status'],))
            else:  # Genehmigt oder Abgelehnt
                self.processed_requests_tree.insert("", tk.END, iid=req['id'], values=display_values,
                                                    tags=(req['status'],))

    def _withdraw_request_by_id(self, request_id):
        request_data = self.wunschfrei_data_store.get(request_id)
        if not request_data:
            messagebox.showerror("Fehler", "Antrag nicht gefunden.", parent=self)
            return

        status = request_data['status']
        if status not in ['Ausstehend', 'Genehmigt', 'Abgelehnt']:
            messagebox.showwarning("Aktion nicht möglich", "Dieser Antrag kann nicht zurückgezogen werden.",
                                   parent=self)
            return

        success, message = withdraw_wunschfrei_request(request_id, self.user_data['id'])
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_wunschfrei_tab()
            self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def withdraw_selected_request(self):
        selection = self.pending_requests_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen offenen Antrag zum Zurückziehen aus.",
                                   parent=self)
            return
        request_id = int(selection[0])
        self._withdraw_request_by_id(request_id)

    def create_shift_plan_tab(self):
        self.plan_tab_frame = ttk.Frame(self.notebook, padding="10")
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

        def _configure_inner_frame(event):
            self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame)
        self.inner_frame.bind('<Configure>', _configure_scrollregion)

        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
        return self.plan_tab_frame

    def _handle_user_request(self, year, month, day, request_type=None):
        request_date = date(year, month, day)
        date_str = request_date.strftime('%Y-%m-%d')
        new_requested_shift = "WF" if request_type is None else request_type

        existing_request = None
        for req in self.wunschfrei_data_store.values():
            if req['request_date'] == date_str:
                existing_request = req
                break

        if existing_request:
            if existing_request['status'] == 'Abgelehnt':
                if new_requested_shift == 'WF' and existing_request.get('requested_shift') == 'WF':
                    messagebox.showinfo("Aktion nicht möglich",
                                        "Ein Wunschfrei-Antrag für diesen Tag wurde bereits abgelehnt. Bitte wählen Sie eine andere Art von Wunsch (z.B. Schichtwunsch) oder kontaktieren Sie einen Admin.",
                                        parent=self)
                    return

                success_withdraw, msg_withdraw = withdraw_wunschfrei_request(existing_request['id'],
                                                                             self.user_data['id'])
                if not success_withdraw:
                    messagebox.showerror("Fehler",
                                         f"Der alte, abgelehnte Antrag konnte nicht überschrieben werden: {msg_withdraw}",
                                         parent=self)
                    return
            else:
                messagebox.showerror("Fehler",
                                     "Für diesen Tag existiert bereits ein ausstehender oder genehmigter Antrag.",
                                     parent=self)
                return

        if request_type is None:
            month_name = date(year, month, 1).strftime('%B')
            request_count = get_wunschfrei_requests_by_user_for_month(self.user_data['id'], year, month)
            if request_count >= 3:
                messagebox.showwarning("Limit erreicht",
                                       f"Sie haben bereits das Maximum von 3 'Wunschfrei'-Anfragen für {month_name} {year} erreicht.",
                                       parent=self)
                return

            msg = f"Möchten Sie für den {request_date.strftime('%d.%m.%Y')} 'Wunschfrei' beantragen?\n\nSie haben noch {3 - request_count} Anfrage(n) für diesen Monat frei."
            if not messagebox.askyesno("Bestätigen", msg, parent=self):
                return

        success, message = submit_user_request(self.user_data['id'], date_str, requested_shift=new_requested_shift)
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_wunschfrei_tab()
            self.build_shift_plan_grid(year, month)
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def on_user_cell_click(self, event, user_id_in_row, day, year, month):
        if user_id_in_row != self.user_data['id']:
            return

        request_date = date(year, month, day)
        if request_date < date.today():
            messagebox.showwarning("Aktion nicht erlaubt",
                                   "Anfragen für vergangene Tage können nicht gestellt oder geändert werden.",
                                   parent=self)
            return

        date_str = request_date.strftime('%Y-%m-%d')
        existing_request = None
        for req in self.wunschfrei_data_store.values():
            if req['request_date'] == date_str:
                existing_request = req
                break

        if existing_request and existing_request['status'] in ['Ausstehend', 'Genehmigt']:
            context_menu = tk.Menu(self, tearoff=0)
            context_menu.add_command(label="Wunsch entfernen",
                                     command=lambda: self._withdraw_request_by_id(existing_request['id']))
            context_menu.post(event.x_root, event.y_root)
            return

        request_config = RequestConfigManager.load_config()
        context_menu = tk.Menu(self, tearoff=0)

        if request_config.get("WF", False):
            context_menu.add_command(label="Wunschfrei beantragen",
                                     command=lambda: self._handle_user_request(year, month, day, request_type=None))
            context_menu.add_separator()

        preferred_shifts = ["T.", "N.", "6", "24"]
        for shift in preferred_shifts:
            if request_config.get(shift, False):
                if shift == "6":
                    is_friday = request_date.weekday() == 4
                    is_a_holiday = self.is_holiday(request_date)
                    if not is_friday or is_a_holiday:
                        continue

                context_menu.add_command(label=f"Wunsch: '{shift}' eintragen",
                                         command=lambda s=shift: self._handle_user_request(year, month, day,
                                                                                           request_type=s))

        if context_menu.index("end") is not None:
            context_menu.post(event.x_root, event.y_root)
        else:
            messagebox.showinfo("Keine Aktionen", "Aktuell sind keine Anfragetypen für diesen Tag verfügbar.",
                                parent=self)

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

        header_bg, weekend_bg_color = "#E0E0E0", "#EAF4FF"
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

            bg = header_bg
            if is_weekend and not is_holiday_check:
                bg = weekend_bg_color
            if is_holiday_check:
                bg = "#FFD700"

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
            user_id = user_data_row['id']
            user_name = f"{user_data_row['vorname']} {user_data_row['name']}"
            user_dog = user_data_row.get('diensthund', '---')
            user_id_str = str(user_id)

            row_bg_color = "#D4EDDA" if user_id == self.user_data['id'] else "white"

            ttk.Label(self.plan_grid_frame, text=user_name, font=("Segoe UI", 10, "bold"), padding=5, borderwidth=1,
                      relief="solid", foreground="black", background=row_bg_color).grid(row=current_row, column=0,
                                                                                        sticky="nsew")
            ttk.Label(self.plan_grid_frame, text=user_dog, font=("Segoe UI", 10), padding=5, borderwidth=1,
                      relief="solid", foreground="black", anchor="center", background=row_bg_color).grid(
                row=current_row,
                column=1,
                sticky="nsew")
            for day in range(1, days_in_month + 1):
                col_idx = day + 1
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')

                base_shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str, "")
                display_shift = base_shift
                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)

                is_clickable = False
                if user_id == self.user_data['id']:
                    if request_info or not base_shift:
                        is_clickable = True

                if request_info:
                    status, requested_shift = request_info
                    if status == 'Ausstehend':
                        display_shift = 'WF' if requested_shift == 'WF' else f"{requested_shift}?"
                    elif status == 'Genehmigt' and requested_shift == 'WF':
                        display_shift = 'X'

                is_weekend, is_holiday_check = current_date.weekday() >= 5, self.is_holiday(current_date)
                bg_color = color_map.get(display_shift, "white")
                if display_shift.endswith("?"):
                    bg_color = color_map.get("WF", "orange")

                if is_weekend and not is_holiday_check:
                    bg_color = weekend_bg_color
                if is_holiday_check:
                    bg_color = "#FFD700"

                if user_id == self.user_data['id'] and bg_color == "white":
                    bg_color = "#E8F5E9"

                text_color = self.get_contrast_color(bg_color)
                cursor_type = "hand2" if is_clickable else ""

                if is_weekend or is_holiday_check:
                    cell_frame = tk.Frame(self.plan_grid_frame, bg="blue")
                    cell_frame.grid(row=current_row, column=col_idx, sticky="nsew")
                    label = ttk.Label(cell_frame, text=display_shift, background=bg_color, padding=5, anchor="center",
                                      foreground=text_color, cursor=cursor_type)
                    label.pack(fill="both", expand=True, padx=1, pady=1)
                    if is_clickable:
                        label.bind("<Button-1>",
                                   lambda e, uid=user_id, d=day, y=year, m=month: self.on_user_cell_click(
                                       e, uid, d, y, m))
                        cell_frame.bind("<Button-1>", lambda e, uid=user_id, d=day, y=year,
                                                             m=month: self.on_user_cell_click(e, uid, d, y, m))
                else:
                    label = ttk.Label(self.plan_grid_frame, text=display_shift, background=bg_color, padding=5,
                                      borderwidth=1,
                                      relief="solid", anchor="center", foreground=text_color, cursor=cursor_type)
                    label.grid(row=current_row, column=col_idx, sticky="nsew")
                    if is_clickable:
                        label.bind("<Button-1>",
                                   lambda e, uid=user_id, d=day, y=year, m=month: self.on_user_cell_click(
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

                bg = summary_bg
                if min_required is not None:
                    if count < min_required:
                        bg = alert_bg
                    elif count > min_required:
                        bg = overstaffed_bg
                    else:
                        bg = success_bg

                text_color = self.get_contrast_color(bg)
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
        for day_col in range(2, days_in_month + 3):
            self.plan_grid_frame.grid_columnconfigure(day_col, weight=1)
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def show_previous_month(self):
        current_year, current_month = self.current_display_date.year, self.current_display_date.month
        prev_month, prev_year = (current_month - 1, current_year) if current_month > 1 else (12, current_year - 1)
        if prev_year != current_year: self._load_holidays_for_year(prev_year)
        self.current_display_date = date(prev_year, prev_month, 1)
        self.refresh_wunschfrei_tab()
        self.build_shift_plan_grid(prev_year, prev_month)

    def show_next_month(self):
        current_year, current_month = self.current_display_date.year, self.current_display_date.month
        next_month, next_year = (current_month + 1, current_year) if current_month < 12 else (1, current_year + 1)
        if next_year != current_year: self._load_holidays_for_year(next_year)
        self.current_display_date = date(next_year, next_month, 1)
        self.refresh_wunschfrei_tab()
        self.build_shift_plan_grid(next_year, next_month)