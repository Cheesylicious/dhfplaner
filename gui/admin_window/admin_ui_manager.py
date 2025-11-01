# gui/admin_window/admin_ui_manager.py
import tkinter as tk
from tkinter import ttk

# Dialoge importieren, die im Header-Menü benötigt werden
from ..dialogs.bug_report_dialog import BugReportDialog


class AdminUIManager:
    def __init__(self, admin_window, header_frame, footer_frame):
        """
        Manager für den Aufbau der Haupt-UI-Komponenten (Header, Footer, Styles).

        :param admin_window: Die Instanz von MainAdminWindow.
        :param header_frame: Der ttk.Frame für den Header.
        :param footer_frame: Der ttk.Frame für den Footer.
        """
        self.admin_window = admin_window
        self.header_frame = header_frame
        self.footer_frame = footer_frame
        self.user_data = admin_window.user_data

        # Style-Objekt im Hauptfenster speichern, da es global gilt
        self.admin_window.style = ttk.Style(self.admin_window)

    def setup_styles(self):
        """Definiert die globalen ttk-Styles für das Admin-Fenster."""
        style = self.admin_window.style
        try:
            style.theme_use('clam')
        except tk.TclError:
            print("Clam theme not available, using default.")

        style.configure('Bug.TButton', background='dodgerblue', foreground='white', font=('Segoe UI', 9, 'bold'))
        style.map('Bug.TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])

        style.configure('Logout.TButton', background='gold', foreground='black', font=('Segoe UI', 10, 'bold'),
                        padding=6)
        style.map('Logout.TButton', background=[('active', 'goldenrod')], foreground=[('active', 'black')])

        style.configure('Notification.TButton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))
        style.map('Notification.TButton', background=[('active', '#e0e0e0')], relief=[('pressed', 'sunken')])

        style.configure('Settings.TMenubutton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))

    def setup_header(self):
        """Erstellt den Header-Bereich (Benachrichtigungen und Einstellungsmenü)."""

        # Frame für Benachrichtigungen (links)
        self.admin_window.notification_frame = ttk.Frame(self.header_frame)
        self.admin_window.notification_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(self.admin_window.notification_frame, text="").pack()  # Platzhalter

        # Menü-Button für Einstellungen (rechts)
        settings_menubutton = ttk.Menubutton(self.header_frame, text="⚙️ Einstellungen", style='Settings.TMenubutton')
        settings_menubutton.pack(side="right", padx=5)
        settings_menu = tk.Menu(settings_menubutton, tearoff=0)
        settings_menubutton["menu"] = settings_menu

        action_handler = self.admin_window.action_handler
        tab_manager = self.admin_window.tab_manager

        # Menüeinträge hinzufügen
        settings_menu.add_command(label="Schichtarten", command=action_handler.open_shift_types_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Mitarbeiter-Sortierung", command=action_handler.open_user_order_window)
        settings_menu.add_command(label="Schicht-Sortierung", command=action_handler.open_shift_order_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Besetzungsregeln", command=action_handler.open_staffing_rules_window)
        settings_menu.add_command(label="Feiertage", command=action_handler.open_holiday_settings_window)
        settings_menu.add_command(label="Sondertermine", command=action_handler.open_event_settings_window)
        settings_menu.add_command(label="Farbeinstellungen", command=action_handler.open_color_settings_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Anfragen verwalten", command=action_handler.open_request_settings_window)
        settings_menu.add_command(label="Antragssperre", command=action_handler.open_request_lock_window)
        settings_menu.add_command(label="Benutzer-Reiter sperren", command=action_handler.open_user_tab_settings)
        settings_menu.add_command(label="Planungs-Helfer", command=action_handler.open_planning_assistant_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="Datenbank Wartung", command=lambda: tab_manager.switch_to_tab("Wartung"))

    def setup_footer(self):
        """Erstellt den Footer-Bereich (Logout, Bug-Report)."""
        ttk.Button(self.footer_frame, text="Abmelden", command=self.admin_window.logout, style='Logout.TButton').pack(
            side="left", padx=10, pady=5)
        ttk.Button(self.footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def open_bug_report_dialog(self):
        """ Öffnet den Dialog zum Melden eines Bugs. """

        # --- KORREKTUR: AttributeError ---
        # Ruft die neue, nicht-blockierende Funktion 'check_for_updates_threaded' auf.
        callback = self.admin_window.notification_manager.check_for_updates_threaded
        # --- ENDE KORREKTUR ---

        BugReportDialog(self.admin_window, self.user_data['id'], callback)