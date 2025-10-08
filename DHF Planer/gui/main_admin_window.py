# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
from datetime import date
import os

from .tabs.shift_plan_tab import ShiftPlanTab
from .tabs.user_management_tab import UserManagementTab
from .tabs.dog_management_tab import DogManagementTab
from .tabs.shift_types_tab import ShiftTypesTab
from .tabs.requests_tab import RequestsTab
from .tabs.log_tab import LogTab
from .tabs.bug_reports_tab import BugReportsTab
from .dialogs.user_order_window import UserOrderWindow
from .dialogs.shift_order_window import ShiftOrderWindow
from .dialogs.min_staffing_window import MinStaffingWindow
from .dialogs.holiday_settings_window import HolidaySettingsWindow
from .dialogs.request_settings_window import RequestSettingsWindow
from .dialogs.planning_assistant_settings_window import PlanningAssistantSettingsWindow
from .holiday_manager import HolidayManager
from database.db_manager import (
    get_all_shift_types, get_unread_admin_notifications,
    mark_admin_notifications_as_read, get_open_bug_reports_count,
    get_pending_wunschfrei_requests
)

# Dateipfade für Konfigurationen
STAFFING_RULES_FILE = 'min_staffing_rules.json'
SHIFT_FREQUENCY_FILE = 'shift_frequency.json'
TAB_ORDER_CONFIG_FILE = 'tab_order_config.json'


class MainAdminWindow(tk.Toplevel):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.master = master
        self.user_data = user_data

        self.title(f"DHF-Planer - Admin-Bereich (Angemeldet als: {self.user_data['vorname']} {self.user_data['name']})")
        self.geometry("1400x900")
        self.state('zoomed')

        # UI Styling
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass  # Fallback auf Standard-Theme

        # Daten-Initialisierung
        self.current_display_date = date.today()
        self.shift_types_data = {}
        self.staffing_rules = self.load_staffing_rules()
        self.shift_frequency = self.load_shift_frequency()
        self.current_year_holidays = {}

        self.load_shift_types()
        self._load_holidays_for_year(self.current_display_date.year)

        # Haupt-UI-Container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Dictionary, um die Tab-Frames zu halten
        self.tab_frames = {}

        # Laden und Anzeigen der Tabs
        self.setup_tabs()

        # Schließt die Anwendung, wenn das Fenster geschlossen wird
        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)

        # Nach dem Start auf Benachrichtigungen prüfen
        self.after(500, self.check_for_notifications)
        self.after(501, self.update_notification_indicators)  # Indikatoren initial laden

    def load_staffing_rules(self):
        if os.path.exists(STAFFING_RULES_FILE):
            try:
                with open(STAFFING_RULES_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}  # Fallback auf leeres Dictionary bei Fehler
        return {}

    def save_staffing_rules(self):
        try:
            with open(STAFFING_RULES_FILE, 'w') as f:
                json.dump(self.staffing_rules, f, indent=4)
            return True
        except IOError:
            return False

    def load_shift_frequency(self):
        if os.path.exists(SHIFT_FREQUENCY_FILE):
            with open(SHIFT_FREQUENCY_FILE, 'r') as f:
                return json.load(f)
        return {}

    def save_shift_frequency(self):
        with open(SHIFT_FREQUENCY_FILE, 'w') as f:
            json.dump(self.shift_frequency, f, indent=4)

    def setup_tabs(self):
        """Erstellt und konfiguriert alle Tabs im Admin-Fenster."""
        self.tab_classes = {
            "Schichtplan": ShiftPlanTab,
            "Mitarbeiter": UserManagementTab,
            "Diensthunde": DogManagementTab,
            "Schichtarten": ShiftTypesTab,
            "Offene Anfragen": RequestsTab,
            "Bug Reports": BugReportsTab,
            "Aktivitätsprotokoll": LogTab
        }

        # Erstelle alle Tab-Instanzen
        for name, TabClass in self.tab_classes.items():
            if name == "Bug Reports":
                frame = BugReportsTab(self.notebook)
            else:
                frame = TabClass(self.notebook, self)
            self.tab_frames[name] = frame

        # Lade und wende die gespeicherte Reihenfolge an
        self.apply_tab_order()

    def apply_tab_order(self):
        """Ordnet die Tabs gemäß der gespeicherten Konfiguration an."""
        try:
            with open(TAB_ORDER_CONFIG_FILE, 'r') as f:
                config = json.load(f)

            # **KORREKTUR**: Prüfen, ob die geladene config eine Liste ist (altes Format)
            if isinstance(config, list):
                # Konvertiere die Liste in das erwartete Dictionary-Format
                new_config = {}
                for i, tab_name in enumerate(config):
                    new_config[tab_name] = {'order': i, 'visible': True}
                config = new_config

        except (FileNotFoundError, json.JSONDecodeError):
            config = {name: {'order': i, 'visible': True} for i, name in enumerate(self.tab_classes.keys())}

        # Sortiere die Tabs basierend auf der 'order'-Eigenschaft
        sorted_tabs = sorted(self.tab_frames.items(), key=lambda item: config.get(item[0], {}).get('order', 99))

        # Entferne alle Tabs, um sie neu hinzuzufügen
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)

        # Füge die Tabs in der korrekten Reihenfolge hinzu, wenn sie sichtbar sind
        for name, frame in sorted_tabs:
            if config.get(name, {}).get('visible', True):
                self.notebook.add(frame, text=name)

    def update_notification_indicators(self):
        """Aktualisiert die Zähler in den Tab-Titeln."""
        # Zähler für Bug-Reports
        bug_report_count = get_open_bug_reports_count()
        bug_tab_text = "Bug Reports"
        if bug_report_count > 0:
            bug_tab_text += f" ({bug_report_count})"

        # Zähler für offene Anfragen
        request_count = len(get_pending_wunschfrei_requests())
        request_tab_text = "Offene Anfragen"
        if request_count > 0:
            request_tab_text += f" ({request_count})"

        # Finde die Tabs und aktualisiere ihre Texte
        for i, tab_id in enumerate(self.notebook.tabs()):
            current_text = self.notebook.tab(tab_id, "text")
            if current_text.startswith("Bug Reports"):
                self.notebook.tab(i, text=bug_tab_text)
            elif current_text.startswith("Offene Anfragen"):
                self.notebook.tab(i, text=request_tab_text)

    def open_user_order_window(self):
        UserOrderWindow(self, self.reload_shift_plan)

    def open_shift_order_window(self):
        ShiftOrderWindow(self, self.reload_shift_plan)

    def open_staffing_rules_window(self):
        MinStaffingWindow(self, self.staffing_rules, self.reload_shift_plan)

    def open_holiday_settings_window(self):
        HolidaySettingsWindow(self, self.reload_shift_plan)

    def open_request_settings_window(self):
        RequestSettingsWindow(self)

    def open_planning_assistant_settings(self):
        PlanningAssistantSettingsWindow(self)

    def reload_shift_plan(self):
        """Fordert den Schichtplan-Tab auf, sich neu zu laden."""
        if "Schichtplan" in self.tab_frames:
            self.tab_frames["Schichtplan"].build_shift_plan_grid(self.current_display_date.year,
                                                                 self.current_display_date.month)

    def load_shift_types(self):
        shift_types_list = get_all_shift_types()
        self.shift_types_data = {st['abbreviation']: st for st in shift_types_list}

    def get_contrast_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7:
            return 'black'
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def _load_holidays_for_year(self, year):
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def check_for_notifications(self):
        """Prüft auf neue Admin-Benachrichtigungen und zeigt diese an."""
        unread_notifications = get_unread_admin_notifications()

        if unread_notifications:
            message = "Neue Benachrichtigungen:\n\n"
            for notification in unread_notifications:
                message += f"- {notification['message']}\n"

            messagebox.showinfo("Admin-Benachrichtigungen", message, parent=self)

            # Markiere die angezeigten Benachrichtigungen als gelesen
            notification_ids = [n['id'] for n in unread_notifications]
            mark_admin_notifications_as_read(notification_ids)