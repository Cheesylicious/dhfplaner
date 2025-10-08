# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
import os
import json

from database.db_manager import (
    get_pending_requests, ROLE_HIERARCHY, get_all_shift_types,
    get_unread_admin_notifications, mark_admin_notifications_as_read,
    get_pending_wunschfrei_requests, get_open_bug_reports_count
)
from gui.holiday_manager import HolidayManager

# === IMPORTE für Dialoge ===
from .dialogs.tab_order_window import TabOrderWindow, TabOrderManager
from .dialogs.planning_assistant_settings_window import PlanningAssistantSettingsWindow
from .dialogs.request_settings_window import RequestSettingsWindow
from .dialogs.holiday_settings_window import HolidaySettingsWindow
from .dialogs.min_staffing_window import MinStaffingWindow, load_staffing_rules
from .dialogs.user_order_window import UserOrderWindow
from .dialogs.shift_order_window import ShiftOrderWindow
from .dialogs.bug_report_dialog import BugReportDialog

# === IMPORTE für Tabs ===
from .tabs.shift_plan_tab import ShiftPlanTab
from .tabs.user_management_tab import UserManagementTab
from .tabs.dog_management_tab import DogManagementTab
from .tabs.shift_types_tab import ShiftTypesTab
from .tabs.log_tab import LogTab
from .tabs.requests_tab import RequestsTab
from .tabs.wunschfrei_tab import WunschfreiTab
from .tabs.bug_reports_tab import BugReportsTab

SHIFT_FREQUENCY_FILE = 'shift_frequency.json'


class MainAdminWindow(tk.Toplevel):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.master = master
        self.logged_in_user = user_data
        full_name = f"{self.logged_in_user.get('vorname')} {self.logged_in_user.get('name')}".strip()
        self.title(f"Admin-Dashboard - Angemeldet als {full_name}")
        self.geometry("1200x800")
        self.state("zoomed")

        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Alert.TLabel", font=("Segoe UI", 10, "bold"), foreground="red")

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
        self.user_data_store = {}
        self.dog_data_store = []
        self.shift_types_data = {}
        self.staffing_rules = load_staffing_rules()
        self.current_year_holidays = {}
        self.shift_frequency = self.load_shift_frequency()
        self.tab_frames = {}

        self._load_holidays_for_year(self.current_display_date.year)
        self.load_shift_types()

        self.setup_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.setup_tabs()
        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)
        self.after(100, self.check_for_admin_notifications)
        self.update_notification_indicators()

    def setup_header(self):
        header_frame = ttk.Frame(self, padding=5)
        header_frame.pack(fill="x", side="top")
        notification_frame = ttk.Frame(header_frame)
        notification_frame.pack(side="right", padx=10)

        self.pending_urlaub_var = tk.StringVar()
        self.urlaub_label = ttk.Label(notification_frame, textvariable=self.pending_urlaub_var, style="Header.TLabel",
                                      cursor="hand2")
        self.urlaub_label.pack(side="right", padx=10)
        self.urlaub_label.bind("<Button-1>", lambda e: self.switch_to_tab("Urlaubsanträge"))

        self.pending_wunschfrei_var = tk.StringVar()
        self.wunschfrei_label = ttk.Label(notification_frame, textvariable=self.pending_wunschfrei_var,
                                          style="Header.TLabel", cursor="hand2")
        self.wunschfrei_label.pack(side="right", padx=10)
        self.wunschfrei_label.bind("<Button-1>", lambda e: self.switch_to_tab("Offene Anfragen"))

        self.pending_bugs_var = tk.StringVar()
        self.bugs_label = ttk.Label(notification_frame, textvariable=self.pending_bugs_var,
                                    style="Header.TLabel", cursor="hand2")
        self.bugs_label.pack(side="right", padx=10)
        self.bugs_label.bind("<Button-1>", lambda e: self.switch_to_tab("Bug Reports"))

        ttk.Button(header_frame, text="Reiter anpassen", command=self.open_tab_order_window).pack(side="right", padx=10)

    def setup_tabs(self):
        self.tab_frames = {
            "Schichtplan": ShiftPlanTab(self.notebook, self),
            "Urlaubsanträge": RequestsTab(self.notebook, self),
            "Offene Anfragen": WunschfreiTab(self.notebook, self),
            "Benutzerverwaltung": UserManagementTab(self.notebook, self),
            "Diensthunde": DogManagementTab(self.notebook, self),
            "Schichtarten": ShiftTypesTab(self.notebook, self),
            "Protokoll": LogTab(self.notebook, self),
            "Bug Reports": BugReportsTab(self.notebook, self)
        }
        self.reorder_tabs(TabOrderManager.load_order(), set_active_tab=False)

    def setup_footer(self):
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style="Blue.TButton").pack(side="right", padx=10)

    def refresh_bug_reports(self):
        """Callback-Funktion zur Aktualisierung nach Bug-Meldung."""
        if "Bug Reports" in self.tab_frames:
            self.tab_frames["Bug Reports"].refresh_bug_trees()
        self.update_notification_indicators()

    def open_bug_report_dialog(self):
        # Übergibt die refresh_bug_reports Methode als Callback
        BugReportDialog(self, self.logged_in_user['id'], callback=self.refresh_bug_reports)

    def load_shift_frequency(self):
        if os.path.exists(SHIFT_FREQUENCY_FILE):
            try:
                with open(SHIFT_FREQUENCY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save_shift_frequency(self):
        try:
            with open(SHIFT_FREQUENCY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.shift_frequency, f, indent=4)
        except IOError:
            print(f"Fehler beim Speichern der Datei: {SHIFT_FREQUENCY_FILE}")

    def reorder_tabs(self, new_order, set_active_tab=True):
        selected_tab_name = None
        if set_active_tab:
            try:
                selected_tab_name = self.notebook.tab(self.notebook.select(), "text")
            except tk.TclError:
                pass

        for tab_id in list(self.notebook.tabs()):
            self.notebook.forget(tab_id)

        final_order = []
        existing_tabs = list(self.tab_frames.keys())
        for tab_name in new_order:
            if tab_name in existing_tabs:
                final_order.append(tab_name)
                existing_tabs.remove(tab_name)
        final_order.extend(existing_tabs)

        for tab_name in final_order:
            frame = self.tab_frames.get(tab_name)
            if frame:
                self.notebook.add(frame, text=tab_name)

        if selected_tab_name:
            for i, tab_name in enumerate(final_order):
                if tab_name == selected_tab_name:
                    self.notebook.select(i)
                    break

    def switch_to_tab(self, tab_text):
        for i, tab in enumerate(self.notebook.tabs()):
            if self.notebook.tab(i, "text") == tab_text:
                self.notebook.select(i)
                break

    def update_notification_indicators(self):
        num_wunschfrei = len(get_pending_wunschfrei_requests())
        num_urlaub = len(get_pending_requests())
        num_bugs = get_open_bug_reports_count()
        self.pending_wunschfrei_var.set(f"🔔 Offene Anfragen: {num_wunschfrei}" if num_wunschfrei > 0 else "")
        self.wunschfrei_label.config(style="Alert.TLabel" if num_wunschfrei > 0 else "Header.TLabel")
        self.pending_urlaub_var.set(f"🔔 Offene Urlaubsanträge: {num_urlaub}" if num_urlaub > 0 else "")
        self.urlaub_label.config(style="Alert.TLabel" if num_urlaub > 0 else "Header.TLabel")
        self.pending_bugs_var.set(f"🐞 Offene Bug Reports: {num_bugs}" if num_bugs > 0 else "")
        self.bugs_label.config(style="Alert.TLabel" if num_bugs > 0 else "Header.TLabel")

    def check_for_admin_notifications(self):
        unread_notifications = get_unread_admin_notifications()
        if not unread_notifications: return
        message_lines = ["Seit Ihrem letzten Login gab es folgende Aktivitäten:"] + [f"- {n['message']}" for n in
                                                                                     unread_notifications]
        notified_ids = [n['id'] for n in unread_notifications]
        messagebox.showinfo("Benachrichtigung", "\n".join(message_lines), parent=self)
        mark_admin_notifications_as_read(notified_ids)
        if "Protokoll" in self.tab_frames: self.tab_frames["Protokoll"].refresh_log_tab()
        if "Bug Reports" in self.tab_frames: self.tab_frames["Bug Reports"].refresh_bug_trees()

    def open_tab_order_window(self):
        TabOrderWindow(self, self.reorder_tabs)

    def open_planning_assistant_settings(self):
        PlanningAssistantSettingsWindow(self)

    def open_user_order_window(self):
        UserOrderWindow(self, self.refresh_all_tabs)

    def open_shift_order_window(self):
        ShiftOrderWindow(self, self.refresh_all_tabs)

    def open_staffing_rules_window(self):
        MinStaffingWindow(self, self.refresh_staffing_rules)

    def open_request_settings_window(self):
        RequestSettingsWindow(self)

    def open_holiday_settings_window(self):
        HolidaySettingsWindow(self, self.current_display_date.year, self.refresh_holidays_and_plan)

    def refresh_all_tabs(self):
        if "Benutzerverwaltung" in self.tab_frames: self.tab_frames["Benutzerverwaltung"].refresh_user_tree()
        if "Diensthunde" in self.tab_frames: self.tab_frames["Diensthunde"].refresh_dogs_list()
        if "Schichtplan" in self.tab_frames: self.tab_frames["Schichtplan"].build_shift_plan_grid(
            self.current_display_date.year, self.current_display_date.month)
        if "Bug Reports" in self.tab_frames: self.tab_frames["Bug Reports"].refresh_bug_trees()

    def refresh_holidays_and_plan(self):
        self._load_holidays_for_year(self.current_display_date.year)
        if "Schichtplan" in self.tab_frames: self.tab_frames["Schichtplan"].build_shift_plan_grid(
            self.current_display_date.year, self.current_display_date.month)

    def refresh_staffing_rules(self):
        self.staffing_rules = load_staffing_rules()
        if "Schichtplan" in self.tab_frames: self.tab_frames["Schichtplan"].build_shift_plan_grid(
            self.current_display_date.year, self.current_display_date.month)

    def load_shift_types(self):
        self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}
        if "Schichtarten" in self.tab_frames: self.tab_frames["Schichtarten"].refresh_shift_type_tree()
        if "Schichtplan" in self.tab_frames: self.tab_frames["Schichtplan"].build_shift_plan_grid(
            self.current_display_date.year, self.current_display_date.month)

    def _load_holidays_for_year(self, year):
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def get_contrast_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            return 'black' if (r * 299 + g * 587 + b * 114) / 1000 >= 128 else 'white'
        except ValueError:
            return 'black'

    def reset_shift_frequency(self):
        if messagebox.askyesno("Bestätigen", "Möchten Sie die Zählung der Schicht-Häufigkeit wirklich zurücksetzen?",
                               parent=self):
            self.shift_frequency = {}
            self.save_shift_frequency()
            messagebox.showinfo("Erfolg", "Der Zähler für die Schicht-Häufigkeit wurde zurückgesetzt.", parent=self)

    def get_allowed_roles(self):
        admin_level = ROLE_HIERARCHY.get(self.logged_in_user['role'], 0)
        is_super = self.logged_in_user['role'] == "SuperAdmin"
        return sorted([r for r, l in ROLE_HIERARCHY.items() if (l < admin_level or (is_super and l <= admin_level))],
                      key=lambda r: ROLE_HIERARCHY.get(r, 0))