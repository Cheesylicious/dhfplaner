# gui/boot_loader.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from datetime import date, datetime

# Datenbank-Kern (Fassade)
from database import db_core

# Wichtige Manager
# KORREKTUR: Wir importieren die Klassen, rufen sie aber statisch auf
from gui.holiday_manager import HolidayManager
from gui.event_manager import EventManager
# --- ENDE KORREKTUR ---

from gui.shift_plan_data_manager import ShiftPlanDataManager
from database.db_shifts import get_all_shift_types

# Fenster
from gui.login_window import LoginWindow
from gui.main_admin_window import MainAdminWindow
from gui.main_user_window import MainUserWindow


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
        self.current_display_date = date.today()

        self.prewarm_thread = None
        self.preload_thread = None

        self.shift_types_data = {}
        self.min_staffing_rules = {}

        # --- KORREKTUR: Instanziierung entfernt ---
        # Diese Manager werden jetzt (gemäß Ihrem Code-Design) statisch verwendet.
        # self.holiday_manager = HolidayManager() # ENTFERNT
        # self.event_manager = EventManager() # ENTFERNT
        # --- ENDE KORREKTUR ---

        self.data_manager = None
        self.global_events_data = {}  # Dieser Cache wird jetzt vom DM gefüllt

        self.start_threads_and_show_login()

    def start_threads_and_show_login(self):
        print("[Boot Loader] Starte DB-Pre-Warming Thread...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        print("[Boot Loader] Starte Common-Data-Pre-Loading Thread...")
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

    def load_min_staffing_rules(self, force_reload=False):
        if not self.min_staffing_rules or force_reload:
            self.min_staffing_rules = db_core.load_config_json("MIN_STAFFING_RULES")
            if not self.min_staffing_rules:
                print("[WARNUNG] Mindestbesetzung (MIN_STAFFING_RULES) nicht in DB gefunden. Verwende leere Regeln.")
                self.min_staffing_rules = {}

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

    def preload_common_data(self):
        """
        THREAD-FUNKTION: Lädt alle notwendigen Anwendungsdaten parallel
        zum DB-Pre-Warming. Lädt auch den Schichtplan für den aktuellen Monat vor.
        """
        print("[Preload Thread] Starte Daten-Caching...")
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
            self.load_min_staffing_rules(force_reload=True)

            current_year = date.today().year
            print(f"[Preload Thread] Lade Feiertage für {current_year}...")
            # KORREKTUR: Fange den Fehler hier ab, falls event_manager.py ihn auslöst
            self.load_holidays_for_year(current_year)

            if self.data_manager is None:
                print("[Preload Thread] Instanziiere ShiftPlanDataManager...")
                self.data_manager = ShiftPlanDataManager(self)

            print("[Preload Thread] Lade Schichtplan (aktueller Monat)...")
            today = date.today()
            self.data_manager.load_and_process_data(today.year, today.month)
            print(f"[Preload Thread] Schichtplan für {today.year}-{today.month} vorgeladen.")

        except Exception as e:
            # Fängt Fehler ab (z.B. den 'year_int'-Fehler, falls er erneut auftritt)
            print(f"[FEHLER] Preload des Schichtplans ODER der Stammdaten fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()

        end_time = time.time()
        print(f"[Preload Thread] Common-Data-Caching BEENDET. Dauer: {end_time - start_time:.2f}s")

    def on_login_success(self, login_window, user_data):
        print(
            f"[Boot Loader] Login erfolgreich für: {user_data['vorname']} {user_data['name']} (Rolle: {user_data['role']})")
        self.current_user_data = user_data
        login_window.show_loading_ui()
        self.after(100, lambda: self._load_main_window(user_data))

    def _load_main_window(self, user_data):
        try:
            if self.main_window:
                self.main_window.destroy()

            role = user_data.get('role')
            if role in ["Admin", "SuperAdmin"]:
                print("[Boot Loader] Lade Admin-Fenster...")
                self.main_window = MainAdminWindow(self, user_data, self)
            else:
                print("[Boot Loader] Lade Benutzer-Fenster...")
                self.main_window = MainUserWindow(self, user_data, self)

            self.main_window.wait_visibility()
            self.main_window.update_idletasks()

            print("[Boot Loader] Hauptfenster geladen. Wechsle Fenster...")
            self.login_window.destroy()
            self.login_window = None
            self.main_window.deiconify()

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
        if self.main_window:
            self.main_window.destroy()
        self.main_window = None
        self.current_user_data = None
        self.start_threads_and_show_login()

    def on_app_close(self):
        print("[Boot Loader] Anwendung wird beendet.")
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