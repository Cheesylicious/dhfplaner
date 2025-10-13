# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
from datetime import date, timedelta
import calendar
from collections import defaultdict

# --- (Alle deine Imports bleiben unverändert) ---
from .tabs.shift_plan_tab import ShiftPlanTab
from .tabs.user_management_tab import UserManagementTab
from .tabs.dog_management_tab import DogManagementTab
from .tabs.shift_types_tab import ShiftTypesTab
from .tabs.requests_tab import RequestsTab
from .tabs.log_tab import LogTab
from .tabs.bug_reports_tab import BugReportsTab
from .tabs.vacation_requests_tab import VacationRequestsTab
from .tabs.request_lock_tab import RequestLockTab
from .tabs.user_tab_settings_tab import UserTabSettingsTab
from .tabs.participation_tab import ParticipationTab
from .dialogs.user_order_window import UserOrderWindow
from .dialogs.shift_order_window import ShiftOrderWindow
from .dialogs.min_staffing_window import MinStaffingWindow
from .dialogs.holiday_settings_window import HolidaySettingsWindow
from .dialogs.event_settings_window import EventSettingsWindow
from .dialogs.request_settings_window import RequestSettingsWindow
from .dialogs.planning_assistant_settings_window import PlanningAssistantSettingsWindow
from .dialogs.color_settings_window import ColorSettingsWindow
from .dialogs.bug_report_dialog import BugReportDialog
from .holiday_manager import HolidayManager
from .event_manager import EventManager
from database.db_shifts import get_all_shift_types
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count
from database.db_admin import get_pending_password_resets_count
from database.db_core import ROLE_HIERARCHY
from .tabs.password_reset_requests_window import PasswordResetRequestsWindow


class MainAdminWindow(tk.Toplevel):
    # --- HIER IST DIE KORREKTUR ---
    # Wir akzeptieren jetzt 'master', 'user_data' und die 'app'-Instanz
    def __init__(self, master, user_data, app):
        super().__init__(master)
        self.app = app  # Speichert die Referenz zur Haupt-App
        self.user_data = user_data

        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name} (Admin)")
        self.attributes('-fullscreen', True)

        # --- (Der Rest des Codes bleibt exakt gleich, bis auf die letzten beiden Methoden) ---
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
        self.style.map('Notification.TButton', background=[('active', '#e0e0e0')], relief=[('pressed', 'sunken')])
        self.style.configure('Settings.TMenubutton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))
        self.shift_types_data = {}
        self.staffing_rules = {}
        self.events = {}
        today = date.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        self.current_display_date = today.replace(day=1) + timedelta(days=days_in_month)
        self.current_year_holidays = {}
        self.shift_frequency = self.load_shift_frequency()
        self.load_all_data()
        self.header_frame = ttk.Frame(self, padding=(10, 5, 10, 0))
        self.header_frame.pack(fill='x')
        self.setup_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)
        self.tab_frames = {}
        self.setup_tabs()
        self.setup_footer()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(1000, self.check_for_updates)

    def on_close(self):
        """Wird aufgerufen, wenn das Fenster geschlossen wird."""
        self.app.on_app_close()

    def logout(self):
        """Zerstört das Hauptfenster, um zum Login zurückzukehren."""
        self.app.on_logout(self)

    # --- (Alle anderen Methoden in der Mitte bleiben unverändert) ---
    def setup_header(self):
        self.notification_frame = ttk.Frame(self.header_frame)
        self.notification_frame.pack(side="left", fill="x", expand=True)
        settings_menubutton = ttk.Menubutton(self.header_frame, text="⚙️ Einstellungen", style='Settings.TMenubutton')
        settings_menubutton.pack(side="right", padx=5)
        settings_menu = tk.Menu(settings_menubutton, tearoff=0)
        settings_menubutton["menu"] = settings_menu
        settings_menu.add_command(label="Schichtarten", command=self.open_shift_types_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Mitarbeiter-Sortierung", command=self.open_user_order_window)
        settings_menu.add_command(label="Schicht-Sortierung", command=self.open_shift_order_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Besetzungsregeln", command=self.open_staffing_rules_window)
        settings_menu.add_command(label="Feiertage", command=self.open_holiday_settings_window)
        settings_menu.add_command(label="Sondertermine", command=self.open_event_settings_window)
        settings_menu.add_command(label="Farbeinstellungen", command=self.open_color_settings_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Anfragen verwalten", command=self.open_request_settings_window)
        settings_menu.add_command(label="Antragssperre", command=self.open_request_lock_window)
        settings_menu.add_command(label="Benutzer-Reiter sperren", command=self.open_user_tab_settings)
        settings_menu.add_command(label="Planungs-Helfer", command=self.open_planning_assistant_settings)

    def setup_tabs(self):
        self.tab_frames = {"Schichtplan": ShiftPlanTab(self.notebook, self),
                           "Teilnahmen": ParticipationTab(self.notebook, self),
                           "Mitarbeiter": UserManagementTab(self.notebook, self),
                           "Diensthunde": DogManagementTab(self.notebook, self),
                           "Wunschanfragen": RequestsTab(self.notebook, self),
                           "Urlaubsanträge": VacationRequestsTab(self.notebook, self),
                           "Bug-Reports": BugReportsTab(self.notebook, self), "Logs": LogTab(self.notebook, self)}
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

    def open_shift_types_window(self):
        ShiftTypesTab(self, self.refresh_all_tabs)

    def open_bug_report_dialog(self):
        BugReportDialog(self, self.user_data['id'], self.check_for_updates)

    def open_password_resets_window(self):
        PasswordResetRequestsWindow(self, self.check_for_updates)

    def open_request_lock_window(self):
        if "Antragssperre" not in self.tab_frames:
            self.tab_frames["Antragssperre"] = RequestLockTab(self.notebook, self)
            self.notebook.add(self.tab_frames["Antragssperre"], text="Antragssperre")
        self.notebook.select(self.tab_frames["Antragssperre"])

    def refresh_antragssperre_views(self):
        if "Schichtplan" in self.tab_frames and self.tab_frames["Schichtplan"].winfo_exists(): self.tab_frames[
            "Schichtplan"].update_lock_status()
        if "Antragssperre" in self.tab_frames and self.tab_frames["Antragssperre"].winfo_exists(): self.tab_frames[
            "Antragssperre"].load_locks_for_year()

    def open_user_tab_settings(self):
        tab_name = "Benutzer-Reiter"
        all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports"]
        if tab_name not in self.tab_frames:
            self.tab_frames[tab_name] = UserTabSettingsTab(self.notebook, all_user_tab_names)
            self.notebook.add(self.tab_frames[tab_name], text=tab_name)
        self.notebook.select(self.tab_frames[tab_name])

    def check_for_updates(self):
        self.update_tab_titles()
        self.update_header_notifications()
        if hasattr(self.tab_frames["Mitarbeiter"], 'update_password_reset_button'): self.tab_frames[
            "Mitarbeiter"].update_password_reset_button()
        self.after(60000, self.check_for_updates)

    def update_tab_titles(self):
        pending_wunsch_count = len(get_pending_wunschfrei_requests())
        tab_text_wunsch = "Wunschanfragen"
        if pending_wunsch_count > 0: tab_text_wunsch += f" ({pending_wunsch_count})"
        if "Wunschanfragen" in self.tab_frames: self.notebook.tab(self.tab_frames["Wunschanfragen"],
                                                                  text=tab_text_wunsch)
        pending_urlaub_count = get_pending_vacation_requests_count()
        tab_text_urlaub = "Urlaubsanträge"
        if pending_urlaub_count > 0: tab_text_urlaub += f" ({pending_urlaub_count})"
        if "Urlaubsanträge" in self.tab_frames: self.notebook.tab(self.tab_frames["Urlaubsanträge"],
                                                                  text=tab_text_urlaub)
        open_bug_count = get_open_bug_reports_count()
        tab_text_bugs = "Bug-Reports"
        if open_bug_count > 0: tab_text_bugs += f" ({open_bug_count})"
        if "Bug-Reports" in self.tab_frames: self.notebook.tab(self.tab_frames["Bug-Reports"], text=tab_text_bugs)

    def update_header_notifications(self):
        for widget in self.notification_frame.winfo_children(): widget.destroy()
        notifications = []
        pending_password_resets = get_pending_password_resets_count()
        if pending_password_resets > 0: notifications.append(
            {"text": f"{pending_password_resets} Passwort-Reset(s)", "bg": "mediumpurple", "fg": "white",
             "action": self.open_password_resets_window})
        pending_wunsch_count = len(get_pending_wunschfrei_requests())
        if pending_wunsch_count > 0: notifications.append(
            {"text": f"{pending_wunsch_count} Offene Wunschanfrage(n)", "bg": "orange", "fg": "black",
             "tab": "Wunschanfragen"})
        pending_urlaub_count = get_pending_vacation_requests_count()
        if pending_urlaub_count > 0: notifications.append(
            {"text": f"{pending_urlaub_count} Offene Urlaubsanträge", "bg": "lightblue", "fg": "black",
             "tab": "Urlaubsanträge"})
        open_bug_count = get_open_bug_reports_count()
        if open_bug_count > 0: notifications.append(
            {"text": f"{open_bug_count} Offene Bug-Report(s)", "bg": "tomato", "fg": "white", "tab": "Bug-Reports"})
        if not notifications:
            ttk.Label(self.notification_frame, text="Keine neuen Benachrichtigungen",
                      font=('Segoe UI', 10, 'italic')).pack()
        else:
            for i, notif in enumerate(notifications):
                self.style.configure(f'Notif{i}.TButton', background=notif["bg"], foreground=notif["fg"])
                if "action" in notif:
                    command = notif["action"]
                else:
                    command = lambda tab=notif["tab"]: self.switch_to_tab(tab)
                btn = ttk.Button(self.notification_frame, text=notif["text"], style=f'Notif{i}.TButton',
                                 command=command)
                btn.pack(side="left", padx=5, fill="x", expand=True)

    def switch_to_tab(self, tab_name):
        if tab_name in self.tab_frames: self.notebook.select(self.tab_frames[tab_name])

    def load_all_data(self):
        self.load_shift_types()
        self.load_staffing_rules()
        self._load_holidays_for_year(self.current_display_date.year)
        self._load_events_for_year(self.current_display_date.year)

    def refresh_all_tabs(self):
        self.load_all_data()
        for tab_name, tab_frame in self.tab_frames.items():
            if hasattr(tab_frame, 'refresh_data'):
                tab_frame.refresh_data()
            elif hasattr(tab_frame, 'refresh_plan'):
                tab_frame.refresh_plan()
        self.check_for_updates()

    def load_shift_types(self):
        self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}

    def load_staffing_rules(self):
        try:
            with open('min_staffing_rules.json', 'r', encoding='utf-8') as f:
                self.staffing_rules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.staffing_rules = {"Daily": {}, "Sa-So": {}, "Fr": {}, "Mo-Do": {}, "Holiday": {}, "Colors": {}}

    def _load_holidays_for_year(self, year):
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def _load_events_for_year(self, year):
        self.events = EventManager.get_events_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def get_event_type(self, current_date):
        return EventManager.get_event_type(current_date, self.events)

    def get_contrast_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def load_shift_frequency(self):
        try:
            with open('shift_frequency.json', 'r', encoding='utf-8') as f:
                return defaultdict(int, json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return defaultdict(int)

    def save_shift_frequency(self):
        try:
            with open('shift_frequency.json', 'w', encoding='utf-8') as f:
                json.dump(self.shift_frequency, f, indent=4)
        except IOError:
            messagebox.showwarning("Speicherfehler", "Die Schichthäufigkeit konnte nicht gespeichert werden.",
                                   parent=self)

    def reset_shift_frequency(self):
        if messagebox.askyesno("Bestätigen", "Möchten Sie den Zähler für die Schichthäufigkeit wirklich zurücksetzen?",
                               parent=self):
            self.shift_frequency.clear()
            self.save_shift_frequency()
            messagebox.showinfo("Erfolg", "Der Zähler wurde zurückgesetzt.", parent=self)

    def get_allowed_roles(self):
        admin_level = ROLE_HIERARCHY.get(self.user_data['role'], 0)
        allowed_roles = [role for role, level in ROLE_HIERARCHY.items() if level < admin_level]
        if self.user_data['role'] == "SuperAdmin": allowed_roles.append("SuperAdmin")
        return allowed_roles

    def open_user_order_window(self):
        UserOrderWindow(self, callback=self.refresh_all_tabs)

    def open_shift_order_window(self):
        ShiftOrderWindow(self, callback=self.refresh_all_tabs)

    def open_staffing_rules_window(self):
        MinStaffingWindow(self, callback=self.refresh_all_tabs)

    def open_holiday_settings_window(self):
        HolidaySettingsWindow(self, year=self.current_display_date.year, callback=self.refresh_all_tabs)

    def open_event_settings_window(self):
        EventSettingsWindow(self, year=self.current_display_date.year, callback=self.refresh_all_tabs)

    def open_color_settings_window(self):
        ColorSettingsWindow(self, callback=self.refresh_all_tabs)

    def open_request_settings_window(self):
        RequestSettingsWindow(self)

    def open_planning_assistant_settings(self):
        PlanningAssistantSettingsWindow(self)