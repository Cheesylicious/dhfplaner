import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
# --- KORREKTUR: Imports für Datumsberechnung ---
from datetime import date, datetime, timedelta
import calendar
# --- ENDE KORREKTUR ---

# Datenbank-Kern (Fassade)
from database import db_core

# Wichtige Manager
# KORREKTUR: Wir importieren die Klassen, rufen sie aber statisch auf
from gui.holiday_manager import HolidayManager
from gui.event_manager import EventManager
# --- ENDE KORREKTUR ---

from gui.shift_plan_data_manager import ShiftPlanDataManager
from database.db_shifts import get_all_shift_types

# --- NEUE IMPORTE FÜR GLOBALEN CACHE (JETZT KORRIGIERT) ---
from database.db_users import get_all_users  # Korrekter Funktionsname (statt get_all_active_users)
from database.db_dogs import get_all_dogs
# (Verwendet get_pending_vacation_requests_count gemäß Ihrer db_requests.py)
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count
# --- ENDE NEUE IMPORTE ---

# Fenster
from gui.login_window import LoginWindow
from gui.main_admin_window import MainAdminWindow
from gui.main_user_window import MainUserWindow
# --- NEU (Zuteilungs-Fenster): Import für das Zuteilungsfenster ---
from gui.main_zuteilung_window import MainZuteilungWindow
# --- ENDE NEU ---

# --- NEU: Import für Schiffsbewachungs-Fenster (Annahme des Klassennamens) ---
try:
    from gui.main_schiffsbewachung_window import MainSchiffsbewachungWindow
except ImportError:
    print("[WARNUNG] main_schiffsbewachung_window.py nicht gefunden. Bitte erstellen Sie die Datei.")
    MainSchiffsbewachungWindow = None  # Fallback
# --- ENDE NEU ---

# --- NEU (P1-P4): Import des neuen Preloading-Managers (Regel 4) ---
from gui.preloading_manager import PreloadingManager
# --- ENDE NEU ---


class Application(tk.Tk):
    """
    Die Hauptanwendungsklasse (Bootloader), die als Root-Tkinter-Instanz dient,
    den Start verwaltet und die Hauptfenster (Login, Admin, User) steuert.
    """

    def __init__(self):
        super().__init__()
        self.withdraw()

        self.current_user_data = None
        self.main_window = None
        self.login_window = None

        # --- NEU (Schritt 5): Fenster-Klassen-Mapping (Regel 2 & 4) ---
        # Definiert, welcher String aus der DB welche Fensterklasse öffnet
        self.window_class_map = {
            "main_admin_window": MainAdminWindow,
            "main_user_window": MainUserWindow,
            # --- NEU (Zuteilungs-Fenster): Zuteilungsfenster hinzugefügt ---
            "main_zuteilung_window": MainZuteilungWindow,
            # --- NEU: Schiffsbewachungs-Fenster hinzugefügt ---
            "main_schiffsbewachung_window": MainSchiffsbewachungWindow
        }
        # --- ENDE NEU ---

        # --- KORREKTUR: Berechne den ZIELMONAT (nächster Monat) ---
        # (Logik von MainAdminWindow hierher verschoben)
        today = date.today()
        first_day_current_month = today.replace(day=1)
        days_in_month = calendar.monthrange(first_day_current_month.year, first_day_current_month.month)[1]
        # Setzt das Zieldatum auf den 1. des nächsten Monats
        self.current_display_date = first_day_current_month + timedelta(days=days_in_month)
        print(f"[Boot Loader] Ziel-Anzeigedatum initialisiert auf: {self.current_display_date}")
        # --- ENDE KORREKTUR ---

        self.prewarm_thread = None
        self.preload_thread = None  # Dieser Thread lädt P1a und P3 (Originalfunktion)

        # --- NEU (P1-P4): Instanz für den Post-Login Preloading-Manager (P1b, P2) ---
        self.preloading_manager = None
        # --- ENDE NEU ---

        # --- Kern-Caches (bereits optimiert) ---
        self.shift_types_data = {}
        self.staffing_rules = {}
        self.data_manager = None
        self.global_events_data = {}  # Dieser Cache wird jetzt vom DM gefüllt

        # --- NEU: Globale Caches für andere Tabs (Regel 2: Performance) ---
        # (Diese werden jetzt wieder im preload_common_data (P3) geladen)
        self.global_user_cache = []
        self.global_dog_cache = []
        self.global_pending_wishes_cache = []  # Hält die volle Liste
        self.global_pending_vacations_count = 0  # Hält nur den ZÄHLER
        self.global_open_bugs_count = 0  # Zähler für Bug-Reports
        # --- ENDE NEU ---

        self.start_threads_and_show_login()

    def start_threads_and_show_login(self):
        print("[Boot Loader] Starte DB-Pre-Warming Thread...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        print("[Boot Loader] Starte Common-Data-Pre-Loading Thread (P1a + P3)...")
        self.preload_thread = threading.Thread(target=self.preload_common_data, daemon=True)
        self.preload_thread.start()

        self.show_login_window()

    def show_login_window(self):
        if self.login_window and self.login_window.winfo_exists():
            self.login_window.lift()
            self.login_window.focus_force()
        else:
            print("[DEBUG] Application.show_login_window: Erstelle LoginWindow...")
            self.login_window = LoginWindow(self, self, self.prewarm_thread, self.preload_thread)

    def load_shift_types(self, force_reload=False):
        if not self.shift_types_data or force_reload:
            shift_types_list = get_all_shift_types()
            self.shift_types_data = {
                st['abbreviation']: st for st in shift_types_list
            }
            print(f"[Boot Loader] {len(self.shift_types_data)} Schichtarten in Map-Cache geladen.")

    # --- KORREKTUR: Name und Logik der Funktion angepasst ---
    def load_staffing_rules(self, force_reload=False):
        """
        Lädt die Mindestbesetzungsregeln und validiert sie (inkl. Standardfarben),
        damit der Renderer sie beim Kaltstart verwenden kann.
        """
        if not self.staffing_rules or force_reload:
            rules = db_core.load_config_json(db_core.MIN_STAFFING_RULES_CONFIG_KEY)

            # Standard-Validierung (analog zu AdminDataManager)
            default_colors = {
                "alert_bg": "#FF5555",
                "overstaffed_bg": "#FFFF99",
                "success_bg": "#90EE90",
                "weekend_bg": "#EAF4FF",
                "holiday_bg": "#FFD700",
                "violation_bg": "#FF5555",
                "Ausstehend": "orange",
                "Admin_Ausstehend": "#E0B0FF",
                "quartals_ausbildung_bg": "#ADD8E6",  # Wichtig für Header
                "schiessen_bg": "#FFB6C1"  # Wichtig für Header
            }
            defaults = {
                "Mo-Do": {}, "Fr": {}, "Sa-So": {}, "Holiday": {}, "Daily": {},
                "Colors": default_colors
            }

            if not rules or not isinstance(rules, dict):
                print("[WARNUNG] Besetzungsregeln nicht gefunden oder ungültig, verwende Standard.")
                self.staffing_rules = defaults
            else:
                # Stelle sicher, dass alle Hauptkategorien und Farben existieren
                for key, default_val in defaults.items():
                    if key not in rules:
                        rules[key] = default_val
                    elif key == "Colors":
                        if isinstance(rules[key], dict):
                            for ckey, cval in default_colors.items():
                                if ckey not in rules["Colors"]:
                                    rules["Colors"][ckey] = cval
                        else:
                            rules["Colors"] = default_colors
                self.staffing_rules = rules
            print("[Boot Loader] Besetzungsregeln (staffing_rules) geladen und validiert.")

    # --- ENDE KORREKTUR ---

    # --- KORREKTUR: Aufruf auf STATISCHE Methode geändert ---
    def load_holidays_for_year(self, year):
        """Lädt Feiertage für ein Jahr (ruft statische Methode auf)."""
        HolidayManager.get_holidays_for_year(year)

    def is_holiday(self, date_obj):
        """Prüft, ob ein Datum ein Feiertag ist (ruft statische Methode auf)."""
        return HolidayManager.is_holiday(date_obj)

    def load_events_for_year(self, year):
        """Lädt Sondertermine für ein Jahr (ruft statische Methode auf)."""
        # (Gemäß der Verwendung in db_shifts.py)
        EventManager.get_events_for_year(year)

    def get_event_type(self, date_obj):
        """Gibt den Typ eines Sondertermins zurück (oder None)."""
        # (Gemäß der Verwendung in db_shifts.py)
        # Wir müssen sicherstellen, dass die globalen Daten (jetzt im DM) geladen sind
        # Aber der DM ruft DIESE Funktion auf...
        # KORREKTUR: Der EventManager wird statisch aufgerufen
        year_events = EventManager.get_events_for_year(date_obj.year)
        return year_events.get(date_obj.strftime('%Y-%m-%d'))

    # --- ENDE KORREKTUR ---

    # --- NEUE FUNKTION (LÖST DEN FEHLER) ---
    def get_contrast_color(self, hex_color):
        """
        Gibt 'white' or 'black' zurück, je nach Kontrast zu hex_color.
        (Kopiert von AdminUtils, um für den Renderer im Bootloader verfügbar zu sein)
        """
        try:
            if hex_color.startswith('#'):
                hex_color = hex_color[1:]

            # Konvertiere Hex zu RGB
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)

            # Berechne Helligkeit (YIQ-Formel)
            luminance = (r * 299 + g * 587 + b * 114) / 1000

            # Schwellenwert (128 ist die Mitte)
            return 'black' if luminance > 128 else 'white'
        except Exception:
            # Fallback bei ungültigem Farbcode
            return 'black'

    # --- ENDE NEUE FUNKTION ---

    def preload_common_data(self):
        """
        THREAD-FUNKTION: Lädt alle notwendigen Anwendungsdaten parallel
        zum DB-Pre-Warming. Lädt auch den Schichtplan für den nächsten Monat vor.
        (DIES IST DIE "ORIGINALFUNKTION", DIE BEIBEHALTEN WIRD - P1a + P3)
        """
        print("[Preload Thread] Starte Daten-Caching (P1a + P3)...")
        start_time = time.time()

        while not db_core.is_db_initialized():
            if self.prewarm_thread and not self.prewarm_thread.is_alive():
                print("[FEHLER im Preload] DB-Thread ist tot, aber DB nicht initialisiert. Breche Preload ab.")
                return
            time.sleep(0.1)

        try:
            print("[Preload Thread] Lade Schichtarten...")
            self.load_shift_types(force_reload=True)

            print("[Preload Thread] Lade Mindestbesetzung...")
            # --- KORREKTUR: Korrekter Funktionsaufruf ---
            self.load_staffing_rules(force_reload=True)
            # --- ENDE KORREKTUR ---

            current_year = date.today().year
            print(f"[Preload Thread] Lade Feiertage für {current_year}...")
            self.load_holidays_for_year(current_year)

            # --- KORREKTUR: Events für das ZIELJAHR laden, falls abweichend ---
            target_year = self.current_display_date.year
            if target_year != current_year:
                print(f"[Preload Thread] Lade Feiertage auch für {target_year}...")
                self.load_holidays_for_year(target_year)
                print(f"[Preload Thread] Lade Events für {target_year}...")
                self.load_events_for_year(target_year)
            else:
                print(f"[Preload Thread] Lade Events für {current_year}...")
                self.load_events_for_year(current_year)
            # --- ENDE KORREKTUR ---

            if self.data_manager is None:
                print("[Preload Thread] Instanziiere ShiftPlanDataManager (P5-Cache)...")
                self.data_manager = ShiftPlanDataManager(self)

            # --- KORREKTUR: Lade den ZIELMONAT (nächster Monat) (P1a) ---
            target_month = self.current_display_date.month
            print(f"[Preload Thread] Lade Schichtplan (P1a: Zielmonat: {target_year}-{target_month:02d})...")
            self.data_manager.load_and_process_data(target_year, target_month)
            print(f"[Preload Thread] Schichtplan für {target_year}-{target_month:02d} vorgeladen.")
            # --- ENDE KORREKTUR ---

            # --- NEU: Globale Daten für andere Tabs vorladen (P3) (JETZT KORRIGIERT) ---
            print("[Preload Thread] Lade globale Benutzerliste (P3)...")
            self.global_user_cache = get_all_users()  # KORRIGIERT (verwendet get_all_users)
            print(f"[Preload Thread] {len(self.global_user_cache)} Benutzer geladen.")

            print("[Preload Thread] Lade globale Diensthundeliste (P3)...")
            self.global_dog_cache = get_all_dogs()
            print(f"[Preload Thread] {len(self.global_dog_cache)} Hunde geladen.")

            print("[Preload Thread] Lade offene Wunschanfragen (P3)...")
            self.global_pending_wishes_cache = get_pending_wunschfrei_requests()
            print(f"[Preload Thread] {len(self.global_pending_wishes_cache)} offene Wünsche geladen.")

            print("[Preload Thread] Lade Zähler für offene Urlaubsanträge (P3)...")
            self.global_pending_vacations_count = get_pending_vacation_requests_count()  # KORRIGIERT (verwendet _count Funktion)
            print(f"[Preload Thread] {self.global_pending_vacations_count} offene Urlaube gezählt.")

            print("[Preload Thread] Lade Zähler für offene Bug-Reports (P3)...")
            self.global_open_bugs_count = get_open_bug_reports_count()
            print(f"[Preload Thread] {self.global_open_bugs_count} offene Bugs gezählt.")
            # --- ENDE NEU (P3) ---

        except Exception as e:
            # Fängt Fehler ab (z.B. den 'year_int'-Fehler, falls er erneut auftritt)
            print(f"[FEHLER] Preload des Schichtplans ODER der Stammdaten fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()

        end_time = time.time()
        print(f"[Preload Thread] Common-Data-Caching BEENDET. Dauer: {end_time - start_time:.2f}s")

    def on_login_success(self, login_window, user_data):
        print(
            f"[Boot Loader] Login erfolgreich für: {user_data['vorname']} {user_data['name']} (Rolle: {user_data['role']})"
        )
        # (user_data enthält jetzt 'main_window' dank login_window.py)
        self.current_user_data = user_data
        login_window.show_loading_ui()
        self.after(100, lambda: self._load_main_window(user_data))

    def _load_main_window(self, user_data):
        try:
            if self.main_window:
                self.main_window.destroy()

            # --- ANPASSUNG (Schritt 5): Dynamischer Fenster-Lader (Regel 2 & 4) ---

            # 1. Fensternamen aus user_data holen (von login_window.py (Schritt 4) gesetzt)
            window_name = user_data.get('main_window')

            # 2. Fallback (Regel 1), falls login_window.py 'main_window' nicht setzen konnte
            if not window_name:
                print(
                    f"[FEHLER] 'main_window' nicht in user_data gefunden! Führe alten Fallback (basierend auf Rolle) aus.")
                role = user_data.get('role')
                window_name = 'main_admin_window' if role in ["Admin", "SuperAdmin"] else 'main_user_window'
                user_data['main_window'] = window_name  # Sicherstellen, dass es für den Rest der App da ist

            # 3. Fensterklasse aus Mapping (in __init__ definiert) holen
            TargetWindow = self.window_class_map.get(window_name)

            # 4. Fenster instanziieren
            if TargetWindow:
                print(f"[Boot Loader] Lade Fenster: {window_name} ({TargetWindow.__name__})...")
                self.main_window = TargetWindow(self, user_data, self)
            else:
                # Fallback (Regel 1), falls DB einen Namen liefert, den wir (noch) nicht kennen
                # ODER wenn der Import (z.B. für MainSchiffsbewachungWindow) fehlschlug
                print(
                    f"[WARNUNG] Unbekanntes Hauptfenster '{window_name}' in DB oder Import fehlgeschlagen! Führe Fallback auf 'main_user_window' aus.")
                self.main_window = MainUserWindow(self, user_data, self)
            # --- ENDE ANPASSUNG ---

            self.main_window.wait_visibility()
            self.main_window.update_idletasks()

            print("[Boot Loader] Hauptfenster geladen. Wechsle Fenster...")
            self.login_window.destroy()
            self.login_window = None
            self.main_window.deiconify()

            # --- NEU (P1b + P2): Starte den Post-Login PreloadingManager ---
            print("[Boot Loader] Initialisiere Post-Login PreloadingManager (P1b, P2)...")
            self.preloading_manager = PreloadingManager(
                app=self,
                data_manager=self.data_manager,
                main_window=self.main_window
            )
            # Starte die Ladekaskade (P1b -> P2)
            self.preloading_manager.start_initial_preload()

            # Starte den Verarbeitungs-Loop für die UI-Queue (P2)
            self.main_window.after(500, self.preloading_manager.process_ui_queue)
            # --- ENDE NEU ---

        except Exception as e:
            print(f"[FEHLER] Kritisches Laden des Hauptfensters fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Kritischer Fehler",
                                 f"Das Hauptfenster konnte nicht geladen werden:\n{e}\n\n"
                                 "Die Anwendung wird beendet oder zum Login zurückgesetzt.",
                                 parent=self.login_window)

            if self.login_window and self.login_window.winfo_exists():
                self.login_window.show_login_ui()
            else:
                self.on_app_close()

    def on_logout(self):
        print("[Boot Loader] Logout eingeleitet.")

        # --- NEU (P1-P4): Preloader stoppen ---
        if self.preloading_manager:
            self.preloading_manager.stop()
            self.preloading_manager = None
        # --- ENDE NEU ---

        if self.main_window:
            self.main_window.destroy()
        self.main_window = None
        self.current_user_data = None

        # --- NEU (P5): Globalen Dienstplan-Cache leeren ---
        if self.data_manager:
            self.data_manager.clear_all_monthly_caches()
        # --- ENDE NEU ---

        # --- KORREKTUR: Zieldatum beim Logout zurücksetzen ---
        today = date.today()
        first_day_current_month = today.replace(day=1)
        days_in_month = calendar.monthrange(first_day_current_month.year, first_day_current_month.month)[1]
        self.current_display_date = first_day_current_month + timedelta(days=days_in_month)
        # --- ENDE KORREKTUR ---

        # --- NEU: Caches beim Logout leeren (wichtig für nächsten Login) ---
        self.global_user_cache = []
        self.global_dog_cache = []
        self.global_pending_wishes_cache = []
        self.global_pending_vacations_count = 0
        self.global_open_bugs_count = 0
        # --- ENDE NEU ---

        self.start_threads_and_show_login()

    def on_app_close(self):
        print("[Boot Loader] Anwendung wird beendet.")

        # --- NEU (P1-P4): Preloader stoppen ---
        if self.preloading_manager:
            self.preloading_manager.stop()
            self.preloading_manager = None
        # --- ENDE NEU ---

        try:
            if self.main_window:
                self.main_window.destroy()
            if self.login_window:
                self.login_window.destroy()
        except Exception as e:
            print(f"Fehler beim Schließen der Fenster: {e}")
        finally:
            self.quit()

    def run(self):
        print("[DEBUG] Application.run: Starte root.mainloop()...")
        self.mainloop()