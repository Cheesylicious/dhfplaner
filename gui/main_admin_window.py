# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta, datetime
import calendar
from collections import defaultdict

# --- NEUE IMPORTE DER MANAGER ---
from .admin_window.admin_data_manager import AdminDataManager
from .admin_window.admin_tab_manager import AdminTabManager
from .admin_window.admin_ui_manager import AdminUIManager
from .admin_window.admin_action_handler import AdminActionHandler
from .admin_window.admin_notification_manager import AdminNotificationManager
from .admin_window.admin_utils import AdminUtils
# -------------------------------

# --- NEUER IMPORT FÜR THREADING ---
from utils.threading_utils import ThreadManager
# ----------------------------------

# --- DB-IMPORTE FÜR LOGOUT ---
from database.db_users import log_user_logout
# -------------------------------

# Dialoge und Manager, die evtl. noch direkt referenziert werden
# (Die meisten sind jetzt in den Managern)
from .holiday_manager import HolidayManager
from .event_manager import EventManager


class MainAdminWindow(tk.Toplevel):
    def __init__(self, master, user_data, app):
        print("[DEBUG] MainAdminWindow.__init__: Start")
        super().__init__(master)
        self.app = app  # Die Haupt-Applikationsinstanz (enthält PreloadingManager)
        self.user_data = user_data  # HIER WIRD ES GESPEICHERT
        self.user_id = user_data.get('id')
        self.current_user_id = user_data.get('id')

        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name} (Admin)")
        self.attributes('-fullscreen', True)

        # --- DATENATTRIBUTE (Werden von Managern gefüllt) ---
        self.shift_types_data = {}
        self.staffing_rules = {}
        self.events = {}
        today = date.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]

        # HINWEIS: Dieses Datum wird vom Bootloader (P1a) gesetzt und
        # anschließend vom shift_plan_tab (der es lädt) verwaltet.
        self.current_display_date = self.app.current_display_date

        self.current_year_holidays = {}
        self.shift_frequency = defaultdict(int)  # Wird von DataManager geladen

        # --- UI-Elemente (Referenzen für Manager) ---
        self.style = None  # Wird von UIManager gesetzt
        self.notification_frame = None  # Wird von UIManager erstellt
        self.header_frame = ttk.Frame(self, padding=(10, 5, 10, 0))
        self.header_frame.pack(fill='x')

        self.chat_notification_frame = tk.Frame(self, bg='tomato', cursor="hand2")
        # (wird von NotificationManager gepackt/entpackt)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        self.footer_frame = ttk.Frame(self, padding=5)
        self.footer_frame.pack(fill="x", side="bottom")

        # --- MANAGER INSTANZIIEREN ---
        # (Reihenfolge ist wichtig, da sie voneinander abhängen könnten)

        # Utils zuerst, da andere Manager es nutzen könnten
        self.utils = AdminUtils(self)

        # --- NEU: ThreadManager hier initialisieren ---
        # Er muss nach 'self' (dem root-Fenster) und vor den Managern,
        # die ihn verwenden (z.B. NotificationManager), initialisiert werden.
        self.thread_manager = ThreadManager(self)
        # -----------------------------------------------

        # DataManager (lädt shift_frequency beim Init)
        self.data_manager = AdminDataManager(self)

        # TabManager (braucht Notebook)
        self.tab_manager = AdminTabManager(self, self.notebook)

        # ActionHandler (braucht TabManager)
        self.action_handler = AdminActionHandler(self)

        # UIManager (braucht Header/Footer-Frames und ActionHandler/TabManager für Menü)
        self.ui_manager = AdminUIManager(self, self.header_frame, self.footer_frame)

        # NotificationManager (braucht UI-Referenzen, TabManager, ActionHandler)
        self.notification_manager = AdminNotificationManager(self)

        print("[DEBUG] MainAdminWindow.__init__: Alle Manager instanziiert.")

        # --- SETUP-AUFRUFE (Delegiert an Manager) ---

        # --- KORREKTUR: HIER MUSS load_all_data() aufgerufen werden ---
        # 1. Kerndaten (Schichtarten, Regeln, Farben, Events) laden.
        #    Dies MUSS erfolgen, BEVOR der erste Tab (Schichtplan) geladen wird,
        #    damit die Farben und Stundenberechnungen verfügbar sind.
        print("[DEBUG] MainAdminWindow.__init__: Lade Kerndaten (Schichten, Regeln)...")
        # (Diese Daten kommen jetzt aus dem app-Cache, der im Bootloader gefüllt wurde)
        self.data_manager.load_all_data()
        print("[DEBUG] MainAdminWindow.__init__: Kerndaten geladen.")
        # --- ENDE KORREKTUR ---

        # 2. UI-Elemente aufbauen
        self.ui_manager.setup_styles()
        self.ui_manager.setup_header()  # Header (inkl. Menü)
        self.ui_manager.setup_footer()  # Footer (Logout, Bug)

        # 3. Tabs (Platzhalter) erstellen
        self.tab_manager.setup_lazy_tabs()
        print("[DEBUG] MainAdminWindow.__init__: Lazy Tabs (Platzhalter) erstellt.")

        # --- FINALES SETUP ---
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 4. Periodische Checks starten (über NotificationManager)
        #    Diese werden nun intern den ThreadManager verwenden.
        self.notification_manager.start_checkers()

        # 5. Tab-Wechsel-Event binden (an TabManager)
        self.notebook.bind("<<NotebookTabChanged>>", self.tab_manager.on_tab_changed)

        # 6. Ersten Tab auswählen und Laden auslösen
        if self.notebook.tabs():
            self.notebook.select(0)
            # Manueller Aufruf für den ersten Tab (jetzt mit geladenen Daten)
            self.tab_manager.on_tab_changed(None)

        print("[DEBUG] MainAdminWindow.__init__: Initialisierung abgeschlossen.")

    def on_close(self):
        """Wird aufgerufen, wenn das Fenster geschlossen wird."""
        print("[DEBUG] MainAdminWindow.on_close aufgerufen.")
        # Daten speichern (delegiert an DataManager)
        self.data_manager.save_shift_frequency()
        try:
            log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        except Exception as e:
            print(f"[FEHLER] Konnte Logout nicht loggen: {e}")
        # Haupt-App informieren
        self.app.on_app_close()

    def logout(self):
        """Meldet den Benutzer ab und kehrt zum Login-Fenster zurück."""
        print("[DEBUG] MainAdminWindow.logout aufgerufen.")
        # Daten speichern (delegiert an DataManager)
        self.data_manager.save_shift_frequency()
        try:
            log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        except Exception as e:
            print(f"[FEHLER] Konnte Logout nicht loggen: {e}")
        # Haupt-App informieren (schließt dieses Fenster)
        # KORREKTUR: on_logout erwartet keine Argumente
        self.app.on_logout()

    # --- KORREKTUR: PROXY-/DELEGATIONS-METHODEN ---
    # Diese Methoden fangen Aufrufe von älteren Modulen (z.B. Renderer)
    # ab und leiten sie an die neuen Manager weiter.

    def get_event_type(self, current_date):
        """
        Proxy-Methode: Leitet den Aufruf an den AdminDataManager weiter.
        (Behebt den AttributeError aus dem shift_plan_renderer)
        """
        return self.data_manager.get_event_type(current_date)

    def is_holiday(self, check_date):
        """Proxy-Methode: Leitet den Aufruf an den AdminDataManager weiter."""
        return self.data_manager.is_holiday(check_date)

    def get_contrast_color(self, hex_color):
        """Proxy-Methode: Leitet den Aufruf an den AdminUtils weiter."""
        return self.utils.get_contrast_color(hex_color)

    def get_allowed_roles(self):
        """Proxy-Methode: Leitet den Aufruf an den AdminUtils weiter."""
        return self.utils.get_allowed_roles()

    def refresh_all_tabs(self):
        """Proxy-Methode: Leitet den Aufruf an den AdminTabManager weiter."""
        return self.tab_manager.refresh_all_tabs()

    def refresh_shift_plan(self):
        """Proxy-Methode: Leitet den Aufruf an den AdminTabManager weiter."""
        return self.tab_manager.refresh_shift_plan()

    def refresh_specific_tab(self, tab_name):
        """Proxy-Methode: Leitet den Aufruf an den AdminTabManager weiter."""
        return self.tab_manager.refresh_specific_tab(tab_name)

    def refresh_antragssperre_views(self):
        """Proxy-Methode: Leitet den Aufruf an den AdminTabManager weiter."""
        return self.tab_manager.refresh_antragssperre_views()

    def reset_shift_frequency(self):
        """Proxy-Methode: Leitet den Aufruf an den AdminDataManager weiter."""
        return self.data_manager.reset_shift_frequency()

    # (Weitere Proxy-Methoden können bei Bedarf hier hinzugefügt werden)

    # --- NEU (P4): Proxy-Methode zum Auslösen des Preloaders ---
    def trigger_shift_plan_preload(self, new_year, new_month):
        """
        Proxy-Methode (P4): Leitet den Blättern-Trigger an den PreloadingManager (auf self.app) weiter.
        """
        # Greift auf den Manager zu, der auf der Bootloader-Instanz (self.app) lebt
        if hasattr(self.app, 'preloading_manager') and self.app.preloading_manager:
            self.app.preloading_manager.trigger_shift_plan_preload(new_year, new_month)
        else:
            print("[WARNUNG MAW] PreloadingManager nicht auf app gefunden. P4-Trigger ignoriert.")
    # -------------------------------------------------------------------