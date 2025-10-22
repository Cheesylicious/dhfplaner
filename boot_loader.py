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


# ------------------------------------

class Application:
    def __init__(self):
        print("[DEBUG] Application.__init__: Initialisiere die Anwendung.")
        self.root = tk.Tk()
        self.root.withdraw()  # Das Haupt-Root-Fenster bleibt unsichtbar

        # Prüfe, ob die Datenbankverbindung funktioniert, BEVOR der Login startet
        if not self.check_db_connection():
            self.root.destroy()
            sys.exit(1)  # Beendet die Anwendung, wenn DB nicht geht

        print("[DEBUG] Application.__init__: Datenbank initialisiert.")
        self.login_window = None
        self.main_window = None

        # --- NEUE VARIABLEN für Threading ---
        self.user_data = None
        self.current_login_window = None
        self.loading_queue = None
        # ------------------------------------

    def check_db_connection(self):
        """Prüft, ob der DB-Pool erfolgreich erstellt wurde."""
        try:
            db_core.initialize_db()
            # Der Pool wird in db_core erstellt. Prüfen, ob er existiert.
            if db_core.db_pool is None:
                print("ERROOOOOR")
                messagebox.showerror("Kritischer DB Fehler",
                                     "Der Datenbank-Verbindungspool konnte nicht erstellt werden. "
                                     "Siehe Konsole für Details.\nAnwendung wird beendet.")
                return False

            # Test-Verbindung holen und wieder schließen
            conn = db_core.create_connection()
            if conn is None:
                messagebox.showerror("Kritischer DB Fehler",
                                     "Konnte keine Verbindung zur Datenbank herstellen. "
                                     "Ist der Server erreichbar?\nAnwendung wird beendet.")
                return False
            conn.close()
            return True
        except Exception as e:
            messagebox.showerror("Kritischer DB Fehler",
                                 f"Ein unerwarteter Fehler beim DB-Start ist aufgetreten: {e}\n"
                                 "Anwendung wird beendet.")
            return False

    def run(self):
        print("[DEBUG] Application.run: Zeige Login-Fenster.")
        self.show_login_window()
        self.root.mainloop()

    def show_login_window(self):
        print("[DEBUG] Application.show_login_window: Erstelle LoginWindow.")
        if self.main_window:
            self.main_window.destroy()
            self.main_window = None

        self.login_window = LoginWindow(self.root, self)
        # LoginWindow(Toplevel) wird von sich aus sichtbar.

    # --- KOMPLETT ÜBERARBEITET für Threading ---
    def on_login_success(self, login_window, user_data):
        """
        Wird vom LoginWindow aufgerufen. Startet den Lade-Thread.
        """
        print("[DEBUG] Application.on_login_success: Login erfolgreich. Starte Lade-Thread.")

        # 1. Login-Fenster und User-Daten für den Thread speichern
        self.current_login_window = login_window
        self.user_data = user_data

        # 2. Lade-UI im Login-Fenster anzeigen
        #    (Die Funktion show_loading_ui() fügen wir in login_window.py hinzu)
        self.current_login_window.show_loading_ui()

        # 3. Queue für das Thread-Ergebnis erstellen
        self.loading_queue = Queue()

        # 4. Den Lade-Thread starten
        threading.Thread(
            target=self._load_main_window_threaded,
            daemon=True
        ).start()

        # 5. Den "Checker" starten, der auf das Thread-Ergebnis wartet
        self.root.after(100, self._check_loading_thread)

    # --- NEUE FUNKTION (läuft im Hintergrund-Thread) ---
    def _load_main_window_threaded(self):
        """
        Läuft im Hintergrund. Erstellt das Hauptfenster (das ist der langsame Teil).
        """
        print("[DEBUG] Lade-Thread: Erstelle Hauptfenster...")
        try:
            role = self.user_data.get('role')
            if role in ["Admin", "SuperAdmin"]:
                main_window = MainAdminWindow(self.root, self.user_data, self)
            else:
                main_window = MainUserWindow(self.root, self.user_data, self)

            # Legt das fertige Fenster in die Queue
            self.loading_queue.put(main_window)
            print("[DEBUG] Lade-Thread: Hauptfenster fertig erstellt.")
        except Exception as e:
            print(f"[DEBUG] Lade-Thread: KRITISCHER FEHLER beim Laden: {e}")
            self.loading_queue.put(e)

    # --- NEUE FUNKTION (läuft im GUI-Thread) ---
    def _check_loading_thread(self):
        """
        Prüft alle 100ms, ob der Lade-Thread fertig ist.
        """
        try:
            result = self.loading_queue.get_nowait()

            # Thread ist fertig!
            if isinstance(result, Exception):
                # Es gab einen Fehler beim Laden
                print("[DEBUG] GUI-Thread: Fehler vom Lade-Thread empfangen.")
                messagebox.showerror("Kritischer Ladefehler",
                                     f"Das Hauptfenster konnte nicht geladen werden:\n{result}")
                self.on_app_close()  # Anwendung beenden
            else:
                # Erfolgreich geladen!
                print("[DEBUG] GUI-Thread: Hauptfenster empfangen.")
                self.main_window = result

                # Jetzt das Login-Fenster zerstören
                if self.current_login_window:
                    self.current_login_window.destroy()
                    self.current_login_window = None

                # Das Hauptfenster ist bereits sichtbar, da es ein Toplevel ist
                # und sich selbst in seiner __init__ konfiguriert
                # (z.B. mit attributes('-fullscreen', True))
                print("[DEBUG] GUI-Thread: Login zerstört, Hauptfenster ist aktiv.")

        except Empty:
            # Thread ist noch nicht fertig, in 100ms nochmal prüfen.
            self.root.after(100, self._check_loading_thread)

    # -------------------------------------------------

    def on_logout(self, main_window):
        print("[DEBUG] Application.on_logout: Zerstöre Hauptfenster, zeige Login.")
        main_window.destroy()
        self.main_window = None
        self.user_data = None
        self.show_login_window()

    def on_app_close(self):
        print("[DEBUG] Application.on_app_close: Anwendung wird beendet.")
        if self.main_window:
            try:
                # Versuche, die Frequenz zu speichern, falls das Fenster noch existiert
                if isinstance(self.main_window, MainAdminWindow):
                    self.main_window.save_shift_frequency()
            except Exception as e:
                print(f"[DEBUG] Fehler beim Speichern der Frequenz beim Beenden: {e}")

        self.root.quit()
        self.root.destroy()
        print("[DEBUG] Anwendung beendet.")