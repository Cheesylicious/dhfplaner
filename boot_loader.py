# boot_loader.py
import tkinter as tk
from tkinter import messagebox
import threading
import time
from datetime import date

# Import der DB-Funktionen (inkl. Pre-Warming)
from database import db_core

# --- NEUE IMPORTE FÜR PRE-LOADING ---
from database.db_shifts import get_all_shift_types
from gui.holiday_manager import HolidayManager
from gui.event_manager import EventManager


# ------------------------------------


class Application:
    def __init__(self):
        print("[DEBUG] Application.__init__: Erstelle Root-Fenster...")
        self.root = tk.Tk()
        self.root.withdraw()
        self.current_user_data = None
        self.main_window = None
        self.login_window = None

        # --- Threads für Pre-Loading ---
        self.prewarm_thread = None
        self.preload_thread = None  # NEU
        # -------------------------------

    def run(self):
        print("[DEBUG] Application.run: Start")
        # 1. Starte das Pre-Warming des DB-Pools im Hintergrund
        print("[Boot Loader] Starte DB-Pre-Warming Thread...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        # --- NEU: 2. Starte das Pre-Loading der Common-Daten ---
        print("[Boot Loader] Starte Common-Data-Pre-Loading Thread...")
        self.preload_thread = threading.Thread(target=self.preload_common_data, daemon=True)
        self.preload_thread.start()
        # ------------------------------------------------------

        # 2. Zeige das Login-Fenster
        self.show_login_window()

        # 3. Starte die mainloop
        # Die mainloop wird erst beendet, wenn das root-Fenster (das unsichtbar ist)
        # zerstört wird (z.B. durch on_app_close).
        print("[DEBUG] Application.run: Starte root.mainloop()...")
        try:
            self.root.mainloop()
        except Exception as e:
            print(f"[FEHLER] Mainloop gecrasht: {e}")
        print("[DEBUG] Application.run: Mainloop beendet.")

    # --- NEUE FUNKTION ---
    def preload_common_data(self):
        """
        Lädt die wichtigsten (und langsamsten) Daten, die JEDER Benutzer
        braucht, in den jeweiligen Cache.
        """
        print("[Preload Thread] Starte Daten-Caching...")
        start_time = time.time()
        try:
            # 1. Schichtarten (sind bereits gecacht in db_shifts)
            print("[Preload Thread] Lade Schichtarten...")
            get_all_shift_types()

            # 2. Mindestbesetzung (wird jetzt in db_core gecacht)
            print("[Preload Thread] Lade Mindestbesetzung...")
            db_core.load_config_json('MIN_STAFFING_RULES')

            # 3. Feiertage (wird jetzt in holiday_manager gecacht)
            current_year = date.today().year
            print(f"[Preload Thread] Lade Feiertage für {current_year}...")
            HolidayManager.get_holidays_for_year(current_year)

            # 4. Events (wird jetzt in event_manager gecacht)
            print(f"[Preload Thread] Lade Events für {current_year}...")
            EventManager.get_events_for_year(current_year)

            end_time = time.time()
            print(f"[Preload Thread] Common-Data-Caching BEENDET. Dauer: {end_time - start_time:.2f}s")
        except Exception as e:
            print(f"[Preload Thread] FEHLER beim Caching: {e}")
            # Der Thread endet, das Login-Fenster wird den Fehler bemerken
            # (da der Thread nicht mehr .is_alive() ist)
            # und den Login-Button trotzdem freigeben. Die App lädt dann
            # die Daten normal (langsam) beim Start des Hauptfensters.

    # ---------------------

    def show_login_window(self):
        # Import hier, um Zirkel-Importe zu vermeiden
        from gui.login_window import LoginWindow

        if self.login_window and self.login_window.winfo_exists():
            self.login_window.lift()
            self.login_window.focus_force()
        else:
            print("[DEBUG] Application.show_login_window: Erstelle LoginWindow...")
            # --- AUFRUF GEÄNDERT ---
            # Übergibt jetzt BEIDE Threads an das Login-Fenster
            self.login_window = LoginWindow(self.root, self, self.prewarm_thread, self.preload_thread)
            # ---------------------

    def on_login_success(self, login_window, user_data):
        print(f"[DEBUG] on_login_success: User {user_data['vorname']} (Role: {user_data.get('role')})")
        self.current_user_data = user_data

        # Zeige die "Lade..."-UI im Login-Fenster
        login_window.show_loading_ui()

        # Lade das Hauptfenster asynchron, damit die Lade-UI angezeigt wird
        # Wir übergeben das Login-Fenster, damit es bei Erfolg geschlossen werden kann
        threading.Thread(target=self._load_main_window_async, args=(login_window, user_data), daemon=True).start()

    def _load_main_window_async(self, login_window, user_data):
        """Läuft im Hintergrund-Thread nach dem Login."""
        try:
            print("[Async Load] Lade Hauptfenster...")
            start_time = time.time()

            # --- KORREKTUR: Prüfe auf 'role' statt 'is_admin' ---
            user_role = user_data.get('role')
            if user_role == 'Admin' or user_role == 'SuperAdmin':
                # --- ENDE KORREKTUR ---
                from gui.main_admin_window import MainAdminWindow
                main_window_instance = MainAdminWindow(self.root, user_data, self)
            else:
                from gui.main_user_window import MainUserWindow
                main_window_instance = MainUserWindow(self.root, user_data, self)

            end_time = time.time()
            print(f"[Async Load] Hauptfenster-Instanz erstellt. Dauer: {end_time - start_time:.2f}s")

            # Zurück zum Hauptthread, um die UI zu aktualisieren
            self.root.after(0, self.on_main_window_loaded, main_window_instance, login_window)

        except Exception as e:
            print(f"KRITISCHER FEHLER beim Laden des Hauptfensters: {e}")
            import traceback
            traceback.print_exc()
            # Zurück zum Hauptthread, um Fehler anzuzeigen
            self.root.after(0, self.on_main_window_load_failed, login_window, e)

    def on_main_window_loaded(self, main_window_instance, login_window):
        """Wird im Hauptthread aufgerufen, wenn das Hauptfenster fertig geladen ist."""
        print("[DEBUG] on_main_window_loaded: Zeige Hauptfenster, zerstöre Login-Fenster.")
        self.main_window = main_window_instance
        # Zerstöre das Login-Fenster (oder verstecke es)
        if login_window and login_window.winfo_exists():
            login_window.destroy()
        self.login_window = None
        # Das Hauptfenster wurde bereits beim Erstellen angezeigt (via Toplevel)
        self.main_window.lift()
        self.main_window.focus_force()

    def on_main_window_load_failed(self, login_window, error):
        """Wird im Hauptthread aufgerufen, wenn das Laden des Hauptfensters fehlschlägt."""
        print(f"[FEHLER] on_main_window_load_failed: {error}")
        # Zeige das Login-Fenster wieder an (falls es noch existiert)
        if login_window and login_window.winfo_exists():
            login_window.show_login_ui()  # Zeigt das Login-Formular wieder an
        messagebox.showerror("Fehler beim Laden",
                             f"Das Hauptfenster konnte nicht geladen werden:\n{error}\n\n"
                             "Bitte versuchen Sie den Login erneut.",
                             parent=login_window if login_window and login_window.winfo_exists() else self.root)

    def on_logout(self, main_window):
        """Wird aufgerufen, wenn sich ein Benutzer abmeldet."""
        print("[DEBUG] Application.on_logout")
        if main_window and main_window.winfo_exists():
            main_window.destroy()
        self.main_window = None
        self.current_user_data = None

        # --- Threads neu starten für den nächsten Login ---
        print("[Boot Loader] Starte DB-Pre-Warming Thread (nach Logout)...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        print("[Boot Loader] Starte Common-Data-Pre-Loading Thread (nach Logout)...")
        self.preload_thread = threading.Thread(target=self.preload_common_data, daemon=True)
        self.preload_thread.start()
        # --------------------------------------------------

        self.show_login_window()

    def on_app_close(self):
        """Wird aufgerufen, wenn das Fenster geschlossen wird."""
        print("[DEBUG] Application.on_app_close: Schließe Anwendung.")
        # Zerstöre alle Fenster und beende die mainloop
        if self.main_window and self.main_window.winfo_exists():
            self.main_window.destroy()
        if self.login_window and self.login_window.winfo_exists():
            self.login_window.destroy()
        if self.root and self.root.winfo_exists():
            self.root.destroy()
        print("[DEBUG] Anwendung heruntergefahren.")