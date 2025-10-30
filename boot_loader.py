# boot_loader.py
import tkinter as tk
from tkinter import messagebox
from database import db_core
import sys
import os

# --- NEUE IMPORTE für Threading ---
import threading
from queue import Queue, Empty
from gui.main_admin_window import MainAdminWindow
from gui.main_user_window import MainUserWindow
from gui.login_window import LoginWindow
# --- INNOVATION: Import der Prewarm-Funktion ---
from database.db_core import prewarm_connection_pool


# ------------------------------------

class Application:
    def __init__(self):
        print("[DEBUG] Application.__init__: Initialisiere die Anwendung.")
        self.root = tk.Tk()
        self.root.withdraw()  # Das Haupt-Root-Fenster bleibt unsichtbar

        # --- INNOVATION: Blockierender DB-Check entfernt ---
        # Der Start-Check wird entfernt, um das UI sofort anzuzeigen.
        # Die Verbindung wird "lazy" im prewarm-Thread oder spätestens beim Login aufgebaut.
        # if not self.check_db_connection():
        #    self.root.destroy()
        #    sys.exit(1)
        # --- ENDE INNOVATION ---

        self.login_window = None
        self.main_window = None

        # --- NEUE VARIABLEN für Threading ---
        self.user_data = None
        self.current_login_window = None
        self.loading_queue = None
        # ------------------------------------

    # --- INNOVATION: Veraltete Funktion entfernt ---
    # Die check_db_connection() ist jetzt obsolet, da
    # db_core.create_connection() die Initialisierung
    # beim ersten Aufruf (im prewarm_thread) selbst übernimmt.
    # --- ENDE INNOVATION ---

    def run(self):
        print("[DEBUG] Application.run: Zeige Login-Fenster und starte Pre-Warming.")

        # --- INNOVATION: Starte Pool-Initialisierung im Hintergrund ---
        # Wir starten den Thread, um den DB-Pool zu "wärmen",
        # WÄHREND der Benutzer seine Login-Daten eingibt.
        print("[Boot Loader] Starte Pre-Warming Thread für Datenbank-Pool...")
        prewarm_thread = threading.Thread(target=prewarm_connection_pool, daemon=True)
        prewarm_thread.start()
        # --- ENDE INNOVATION ---

        # Übergibt den Thread an das Login-Fenster, damit es ihn beobachten kann
        self.show_login_window(prewarm_thread)
        self.root.mainloop()

    def show_login_window(self, prewarm_thread):
        """
        Nimmt jetzt den prewarm_thread entgegen, um ihn an das
        LoginWindow weiterzugeben.
        """
        print("[DEBUG] Application.show_login_window: Erstelle LoginWindow.")
        if self.main_window:
            self.main_window.destroy()
            self.main_window = None

        # Übergibt den Thread an das Login-Fenster
        self.login_window = LoginWindow(self.root, self, prewarm_thread)
        # LoginWindow(Toplevel) wird von sich aus sichtbar.

    # --- (Die folgenden Threading-Funktionen sind bereits korrekt) ---
    def on_login_success(self, login_window, user_data):
        """
        Wird vom LoginWindow aufgerufen. Startet den Lade-Thread für das Hauptfenster.
        """
        print("[DEBUG] Application.on_login_success: Login erfolgreich. Starte Lade-Thread.")

        self.current_login_window = login_window
        self.user_data = user_data
        self.current_login_window.show_loading_ui()
        self.loading_queue = Queue()

        threading.Thread(
            target=self._load_main_window_threaded,
            daemon=True
        ).start()

        self.root.after(100, self._check_loading_thread)

    def _load_main_window_threaded(self):
        """
        Läuft im Hintergrund. Erstellt das Hauptfenster (das ist der langsame Teil).
        """
        print("[DEBUG] Lade-Thread: Erstelle Hauptfenster...")
        try:
            # HINWEIS: HIER PASSIERT DER EIGENTLICHE LOGIN-LOAD
            # Wenn der Benutzer schneller war als der Pre-Warming-Thread,
            # wird db_core.create_connection() *hier* blockieren (z.B. in authenticate_user).
            # Wenn der Pre-Warming-Thread schneller war, ist dieser Aufruf sofort fertig.
            role = self.user_data.get('role')
            if role in ["Admin", "SuperAdmin"]:
                main_window = MainAdminWindow(self.root, self.user_data, self)
            else:
                main_window = MainUserWindow(self.root, self.user_data, self)

            self.loading_queue.put(main_window)
            print("[DEBUG] Lade-Thread: Hauptfenster fertig erstellt.")
        except Exception as e:
            print(f"[DEBUG] Lade-Thread: KRITISCHER FEHLER beim Laden: {e}")
            import traceback
            traceback.print_exc()  # Mehr Details für die Konsole
            self.loading_queue.put(e)

    def _check_loading_thread(self):
        """
        Prüft alle 100ms, ob der Lade-Thread fertig ist.
        """
        try:
            result = self.loading_queue.get_nowait()

            if isinstance(result, Exception):
                print("[DEBUG] GUI-Thread: Fehler vom Lade-Thread empfangen.")

                # Bessere Fehlerbehandlung
                error_str = str(result)
                if "Fehler beim Erstellen des DB-Pools" in error_str or "Konnte keine Verbindung" in error_str:
                    messagebox.showerror("Kritischer DB Fehler",
                                         f"Die Datenbankverbindung konnte nicht hergestellt werden:\n{result}\n\n"
                                         "Bitte 'db_config.json' prüfen und Server-Verbindung sicherstellen.",
                                         parent=self.root)
                else:
                    messagebox.showerror("Kritischer Ladefehler",
                                         f"Das Hauptfenster konnte nicht geladen werden:\n{result}")

                # Zeigt das Login-Fenster wieder an
                if self.current_login_window:
                    if hasattr(self.current_login_window, 'show_login_ui'):
                        self.current_login_window.show_login_ui()
                    else:
                        self.show_login_window(None)  # Fallback
                else:
                    self.show_login_window(None)  # Fallback
            else:
                print("[DEBUG] GUI-Thread: Hauptfenster empfangen.")
                self.main_window = result

                if self.current_login_window:
                    self.current_login_window.destroy()
                    self.current_login_window = None

                print("[DEBUG] GUI-Thread: Login zerstört, Hauptfenster ist aktiv.")

        except Empty:
            self.root.after(100, self._check_loading_thread)

    # -------------------------------------------------

    def on_logout(self, main_window):
        print("[DEBUG] Application.on_logout: Zerstöre Hauptfenster, zeige Login.")
        main_window.destroy()
        self.main_window = None
        self.user_data = None
        # Startet den Pre-Warming-Prozess für den nächsten Login
        prewarm_thread = threading.Thread(target=prewarm_connection_pool, daemon=True)
        prewarm_thread.start()
        self.show_login_window(prewarm_thread)

    def on_app_close(self):
        print("[DEBUG] Application.on_app_close: Anwendung wird beendet.")
        if self.main_window:
            try:
                if isinstance(self.main_window, MainAdminWindow):
                    self.main_window.save_shift_frequency()
            except Exception as e:
                print(f"[DEBUG] Fehler beim Speichern der Frequenz beim Beenden: {e}")

        self.root.quit()
        self.root.destroy()
        print("[DEBUG] Anwendung beendet.")