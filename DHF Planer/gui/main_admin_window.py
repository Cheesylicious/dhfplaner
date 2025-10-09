# gui/main_admin_window.py (KORRIGIERT: Konfigurations-Logik auf DB umgestellt)
import tkinter as tk
from tkinter import ttk, messagebox
import json
from datetime import date
from collections import defaultdict

from .tabs.shift_plan_tab import ShiftPlanTab
from .tabs.user_management_tab import UserManagementTab
from .tabs.dog_management_tab import DogManagementTab
from .tabs.shift_types_tab import ShiftTypesTab
from .tabs.requests_tab import RequestsTab
from .tabs.log_tab import LogTab
from .tabs.bug_reports_tab import BugReportsTab
from .tabs.vacation_requests_tab import VacationRequestsTab
from .dialogs.user_order_window import UserOrderWindow
from .dialogs.shift_order_window import ShiftOrderWindow
from .dialogs.min_staffing_window import MinStaffingWindow
from .dialogs.holiday_settings_window import HolidaySettingsWindow
from .dialogs.request_settings_window import RequestSettingsWindow
from .dialogs.planning_assistant_settings_window import PlanningAssistantSettingsWindow
from .dialogs.bug_report_dialog import BugReportDialog
from .holiday_manager import HolidayManager
from database.db_manager import (
    get_all_shift_types, get_pending_wunschfrei_requests, get_open_bug_reports_count,
    get_pending_vacation_requests_count, ROLE_HIERARCHY,

    # NEUE DB-KONFIGURATIONSFUNKTIONEN
    load_staffing_rules, load_shift_frequency, load_holiday_config, save_shift_frequency
)


class MainAdminWindow(tk.Toplevel):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.master = master
        self.user_data = user_data
        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name} (Admin)")
        self.attributes('-fullscreen', True)

        self.style = ttk.Style(self)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass

        self.style.configure('Bug.TButton', background='dodgerblue', foreground='white', font=('Segoe UI', 9, 'bold'))
        self.style.map('Bug.TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])
        self.style.configure('Logout.TButton', background='gold', foreground='black', font=('Segoe UI', 10, 'bold'),
                             padding=6)
        self.style.map('Logout.TButton', background=[('active', 'goldenrod')], foreground=[('active', 'black')])

        self.style.configure('Notification.TButton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))
        self.style.map('Notification.TButton',
                       background=[('active', '#e0e0e0')],
                       relief=[('pressed', 'sunken')])

        self.shift_types_data = {}
        self.staffing_rules = {}
        self.holiday_config = {}
        self.current_display_date = date.today()
        self.current_year_holidays = {}
        self.shift_frequency = self.load_shift_frequency()

        self.load_all_data()

        self.header_frame = ttk.Frame(self, padding=(10, 5, 10, 0))
        self.header_frame.pack(fill='x')

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        self.tab_frames = {}
        self.setup_tabs()
        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)
        self.after(1000, self.check_for_updates)

    def setup_tabs(self):
        self.tab_frames = {
            "Schichtplan": ShiftPlanTab(self.notebook, self),
            "Mitarbeiter": UserManagementTab(self.notebook, self),
            "Diensthunde": DogManagementTab(self.notebook, self),
            "Schichtarten": ShiftTypesTab(self.notebook, self),
            "Wunschanfragen": RequestsTab(self.notebook, self),
            "Urlaubsanträge": VacationRequestsTab(self.notebook, self),
            "Bug-Reports": BugReportsTab(self.notebook, self),
            "Logs": LogTab(self.notebook, self)
        }
        for name, frame in self.tab_frames.items():
            self.notebook.add(frame, text=name)
        self.update_tab_titles()

    def setup_footer(self):
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def open_bug_report_dialog(self):
        BugReportDialog(self, self.user_data['id'])

    def logout(self):
        self.withdraw()
        self.master.login_window.clear_input_fields()
        self.master.login_window.deiconify()

    def check_for_updates(self):
        self.update_tab_titles()
        self.update_header_notifications()
        self.after(60000, self.check_for_updates)

    def update_tab_titles(self):
        pending_wunsch_count = len(get_pending_wunschfrei_requests())
        tab_text_wunsch = "Wunschanfragen"
        if pending_wunsch_count > 0:
            tab_text_wunsch += f" ({pending_wunsch_count})"
        if "Wunschanfragen" in self.tab_frames:
            self.notebook.tab(self.tab_frames["Wunschanfragen"], text=tab_text_wunsch)

        pending_urlaub_count = get_pending_vacation_requests_count()
        tab_text_urlaub = "Urlaubsanträge"
        if pending_urlaub_count > 0:
            tab_text_urlaub += f" ({pending_urlaub_count})"
        if "Urlaubsanträge" in self.tab_frames:
            self.notebook.tab(self.tab_frames["Urlaubsanträge"], text=tab_text_urlaub)

        open_bug_count = get_open_bug_reports_count()
        tab_text_bugs = "Bug-Reports"
        if open_bug_count > 0:
            tab_text_bugs += f" ({open_bug_count})"
        if "Bug-Reports" in self.tab_frames:
            self.notebook.tab(self.tab_frames["Bug-Reports"], text=tab_text_bugs)

    def update_header_notifications(self):
        for widget in self.header_frame.winfo_children():
            widget.destroy()

        notifications = []

        pending_wunsch_count = len(get_pending_wunschfrei_requests())
        if pending_wunsch_count > 0:
            notifications.append({
                "text": f"{pending_wunsch_count} Offene Wunschanfrage(n)",
                "bg": "orange",
                "fg": "black",
                "tab": "Wunschanfragen"
            })

        pending_urlaub_count = get_pending_vacation_requests_count()
        if pending_urlaub_count > 0:
            notifications.append({
                "text": f"{pending_urlaub_count} Offene Urlaubsanträge",
                "bg": "lightblue",
                "fg": "black",
                "tab": "Urlaubsanträge"
            })

        open_bug_count = get_open_bug_reports_count()
        if open_bug_count > 0:
            notifications.append({
                "text": f"{open_bug_count} Offene Bug-Report(s)",
                "bg": "tomato",
                "fg": "white",
                "tab": "Bug-Reports"
            })

        if not notifications:
            ttk.Label(self.header_frame, text="Keine neuen Benachrichtigungen", font=('Segoe UI', 10, 'italic')).pack()
        else:
            for i, notif in enumerate(notifications):
                self.style.configure(f'Notif{i}.TButton', background=notif["bg"], foreground=notif["fg"])
                btn = ttk.Button(
                    self.header_frame,
                    text=notif["text"],
                    style=f'Notif{i}.TButton',
                    command=lambda tab=notif["tab"]: self.switch_to_tab(tab)
                )
                btn.pack(side="left", padx=5, fill="x", expand=True)

    def switch_to_tab(self, tab_name):
        if tab_name in self.tab_frames:
            self.notebook.select(self.tab_frames[tab_name])

    def load_all_data(self):
        self.load_shift_types()
        self.load_staffing_rules()
        self.load_holiday_config()
        self._load_holidays_for_year(self.current_display_date.year)

    def refresh_all_tabs(self):
        self.load_all_data()
        for tab in self.tab_frames.values():
            if hasattr(tab, 'refresh_plan'):
                tab.refresh_plan()
            elif hasattr(tab, 'refresh_data'):
                tab.refresh_data()

    def load_shift_types(self):
        self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}

    def load_staffing_rules(self):
        """Lädt Personalregeln aus der Datenbank (ersetzt min_staffing_rules.json)."""
        self.staffing_rules = load_staffing_rules()

    def load_holiday_config(self):
        """Lädt die Feiertags-Konfiguration (Bundesland etc.) aus der Datenbank (ersetzt holidays_config.json)."""
        self.holiday_config = load_holiday_config()

    def _load_holidays_for_year(self, year):
        """Lädt Feiertage basierend auf der geladenen Konfiguration."""
        # Übergibt die Konfiguration an den HolidayManager
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year, self.holiday_config)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def get_contrast_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7:
            return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def load_shift_frequency(self):
        """Lädt Schichthäufigkeitszähler aus der Datenbank (ersetzt shift_frequency.json)."""
        frequency = load_shift_frequency()
        return defaultdict(int, frequency)

    def save_shift_frequency(self):
        """Speichert Schichthäufigkeitszähler in der Datenbank."""
        if not save_shift_frequency(dict(self.shift_frequency)):
            messagebox.showwarning("Speicherfehler", "Die Schichthäufigkeit konnte nicht gespeichert werden.",
                                   parent=self)

    def get_allowed_roles(self):
        return ROLE_HIERARCHY

    def open_user_order_window(self):
        UserOrderWindow(self, self.refresh_all_tabs)

    def open_shift_order_window(self):
        ShiftOrderWindow(self, self.refresh_all_tabs)

    def open_staffing_rules_window(self):
        MinStaffingWindow(self, self.refresh_all_tabs)

    def open_holiday_settings_window(self):
        HolidaySettingsWindow(self, self.current_display_date.year, self.refresh_all_tabs)

    def open_request_settings_window(self):
        RequestSettingsWindow(self, self.refresh_all_tabs)

    def open_planning_assistant_settings(self):
        PlanningAssistantSettingsWindow(self, self.refresh_all_tabs)