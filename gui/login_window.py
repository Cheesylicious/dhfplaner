# gui/login_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import authenticate_user, get_user_count, log_user_login
# --- NEU (Schritt 4): Import der Rollen-DB-Funktion ---
from database.db_roles import get_main_window_for_role
# --- ENDE NEU ---
from .registration_window import RegistrationWindow
from .password_reset_window import PasswordResetWindow
import webbrowser  # Beibehalten

# --- NEUE IMPORTE ---
import threading
from database import db_core  # Um den Pool-Status zu prüfen


class LoginWindow(tk.Toplevel):
    def __init__(self, master, app, prewarm_thread, preload_thread):
        """
        Nimmt jetzt den 'prewarm_thread' UND den 'preload_thread' entgegen,
        um den Verbindungsaufbau UND das Daten-Caching zu überwachen.
        """
        print("[DEBUG] LoginWindow.__init__: Wird initialisiert.")
        super().__init__(master)
        self.app = app

        # --- INNOVATION: Pre-Loading-Threads speichern ---
        self.prewarm_thread = prewarm_thread
        self.preload_thread = preload_thread
        # ------------------------------------------------

        # --- NEU: Status-Flags ---
        self.db_ready = False
        self.data_ready = False  # NEUES FLAG für Daten-Thread
        self.login_button_enabled = False
        # -------------------------

        self.local_version = "0.0.0"

        self.withdraw()
        self.title("DHF-Planer - Login")
        self.configure(bg='#2c3e50')

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Segoe UI', 10, 'bold'),
                        borderwidth=0)
        style.map('TButton', background=[('active', '#2980b9')])

        # Style für Ladebalken (Post-Login)
        style.configure('Loading.TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 12))
        style.configure('Loading.Horizontal.TProgressbar', background='#3498db')

        # --- NEU: Style für Pre-Login-Ladebalken ---
        style.configure('PreLoading.TLabel', background='#2c3e50', foreground='#bdc3c7', font=('Segoe UI', 9, 'italic'))
        # Stil für den Balken selbst
        style.configure('PreLoading.Horizontal.TProgressbar',
                        troughcolor='#34495e',  # Farbe der Leiste
                        background='#3498db')  # Farbe des Balkens

        # Style für erfolgreiche Labels
        style.configure('Success.PreLoading.TLabel', background='#2c3e50', foreground='#2ecc71',
                        font=('Segoe UI', 9, 'italic'))
        # Style für fehlerhafte Labels
        style.configure('Error.PreLoading.TLabel', background='#2c3e50', foreground='red',
                        font=('Segoe UI', 9, 'italic'))
        # --------------------------------------------

        self.protocol("WM_DELETE_WINDOW", self.app.on_app_close)
        self.create_widgets(style)

        self.attributes('-fullscreen', True)
        self.deiconify()
        self.lift()
        self.focus_force()

        # --- INNOVATION: Starte den Checker für die Pre-Loading-Threads ---
        if self.prewarm_thread and self.preload_thread:
            # Startet den neuen Checker
            self.after(100, self._check_startup_threads)
        else:
            # Fallback
            print("[WARNUNG] Nicht alle Pre-Loading-Threads an LoginWindow übergeben.")
            self.db_status_label.config(text="Fehler: Pre-Loading nicht gestartet.", style='Error.PreLoading.TLabel')
            self.login_button.config(state="normal")
            self.login_button_enabled = True
        # -------------------------------------------------------------

        print("[DEBUG] LoginWindow.__init__: Initialisierung abgeschlossen, Fenster sichtbar.")

    def create_widgets(self, style):
        container = ttk.Frame(self, style='TFrame')
        container.pack(fill="both", expand=True)

        self.wrapper_frame = ttk.Frame(container, style='TFrame')
        self.wrapper_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.main_frame = ttk.Frame(self.wrapper_frame, padding="40", style='TFrame')
        self.main_frame.pack()

        ttk.Label(self.main_frame, text=f"DHF Planer", font=("Segoe UI", 28, "bold")).pack(
            pady=(0, 40))

        self.form_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.form_frame.pack(fill="x", pady=5)
        self.form_frame.columnconfigure(1, weight=1)
        ttk.Label(self.form_frame, text="Vorname:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.vorname_entry = ttk.Entry(self.form_frame, font=('Segoe UI', 12), width=30)
        self.vorname_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.vorname_entry.focus_set()
        ttk.Label(self.form_frame, text="Nachname:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.name_entry = ttk.Entry(self.form_frame, font=('Segoe UI', 12))
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(self.form_frame, text="Passwort:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.password_entry = ttk.Entry(self.form_frame, show="*", font=('Segoe UI', 12))
        self.password_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        self.password_entry.bind("<Return>", self.attempt_login)
        self.vorname_entry.bind("<Return>", lambda e: self.name_entry.focus())
        self.name_entry.bind("<Return>", lambda e: self.password_entry.focus())

        self.login_button = ttk.Button(self.main_frame, text="Anmelden", command=self.attempt_login, style='TButton',
                                       state="disabled")
        self.login_button.pack(pady=20, fill="x", ipady=8)

        self.button_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.button_frame.pack(fill='x')

        self.register_button = ttk.Button(self.button_frame, text="Registrieren", command=self.open_registration)
        self.register_button.pack(side='left', expand=True, fill='x', padx=(0, 5), ipady=4)

        self.reset_button = ttk.Button(self.button_frame, text="Passwort vergessen", command=self.open_password_reset)
        self.reset_button.pack(side='right', expand=True, fill='x', padx=(5, 0), ipady=4)

        # --- INNOVATION: Pre-Login Lade-Widgets (AUFGETEILT) ---
        self.pre_login_loading_frame = ttk.Frame(self.wrapper_frame, style='TFrame')
        self.pre_login_loading_frame.pack(fill='x', padx=40, pady=(10, 0))

        # --- Balken 1: Datenbank-Verbindung ---
        self.db_status_label = ttk.Label(self.pre_login_loading_frame, text="Verbinde mit Datenbank...",
                                         style='PreLoading.TLabel', anchor="center")
        self.db_status_label.pack(fill='x')
        self.db_progressbar = ttk.Progressbar(self.pre_login_loading_frame, mode='determinate',
                                              style='PreLoading.Horizontal.TProgressbar',
                                              maximum=100, value=0)
        self.db_progressbar.pack(fill='x', pady=(5, 10))  # Mehr Abstand nach unten

        # --- Balken 2: Anwendungsdaten ---
        self.data_status_label = ttk.Label(self.pre_login_loading_frame, text="Lade Anwendungsdaten...",
                                           style='PreLoading.TLabel', anchor="center")
        self.data_status_label.pack(fill='x')
        self.data_progressbar = ttk.Progressbar(self.pre_login_loading_frame, mode='determinate',
                                                style='PreLoading.Horizontal.TProgressbar',
                                                maximum=100, value=0)
        self.data_progressbar.pack(fill='x', pady=(5, 0))
        # -------------------------------------------------------------

        # --- Post-Login Lade-Widgets (im wrapper_frame) ---
        self.loading_label = ttk.Label(self.wrapper_frame, text="Lade Hauptfenster, bitte warten...",
                                       style='Loading.TLabel', anchor="center")
        self.progress_bar = ttk.Progressbar(self.wrapper_frame, mode='indeterminate',
                                            style='Loading.Horizontal.TProgressbar')
        # -------------------------------------------------

    def _check_startup_threads(self):
        """
        Prüft, ob die Pre-Loading-Threads (DB-Pool UND Daten-Cache) fertig sind
        und aktualisiert die Ladebalken SIMULTAN.
        """
        if not self.winfo_exists():
            return

        db_alive = self.prewarm_thread.is_alive()
        data_alive = self.preload_thread.is_alive()

        # --- 1. DB-Thread (Balken 1) ---
        if self.db_ready:
            # Ist bereits fertig, nichts zu tun
            pass
        elif db_alive:
            # Läuft noch, simuliere Fortschritt
            if self.db_progressbar['value'] < 95:
                self.db_progressbar.step(1.5)  # Etwas schneller simulieren
        else:
            # DB-Thread ist gerade fertig geworden
            pool_obj = db_core.get_db_pool()
            init_flag = db_core.is_db_initialized()

            if pool_obj is not None and init_flag:
                # ERFOLG
                print("[DEBUG] LoginWindow: DB-Pool ist bereit (dynamisch geprüft).")
                self.db_ready = True
                self.db_progressbar['value'] = 100
                self.db_status_label.config(text="Datenbank-Verbindung bereit", style='Success.PreLoading.TLabel')

                # WICHTIG: Login-Button freigeben
                if not self.login_button_enabled:
                    self.login_button.config(state="normal")
                    self.login_button_enabled = True
            else:
                # FEHLSCHLAG
                print("[FEHLER] LoginWindow: DB-Pre-Warming ist fehlgeschlagen (dynamisch geprüft).")
                self.db_ready = True  # Zählt als "fertig", wenn auch fehlgeschlagen
                self.db_progressbar['value'] = 0  # Fehler wird durch Text angezeigt
                self.db_status_label.config(text="Datenbank-Verbindung fehlgeschlagen!",
                                            style='Error.PreLoading.TLabel')

                # Button trotzdem freigeben (Loginversuch wird dann fehlschlagen)
                if not self.login_button_enabled:
                    self.login_button.config(state="normal")
                    self.login_button_enabled = True

        # --- 2. Daten-Thread (Balken 2) ---
        if self.data_ready:
            # Ist bereits fertig, nichts zu tun
            pass
        elif data_alive:
            # Läuft noch, simuliere Fortschritt
            if self.data_progressbar['value'] < 95:
                self.data_progressbar.step(0.7)  # Langsamer simulieren, da Caching länger dauert
        else:
            # Daten-Thread ist gerade fertig geworden
            print("[DEBUG] LoginWindow: Common-Data-Preload ist beendet.")
            self.data_ready = True
            self.data_progressbar['value'] = 100
            self.data_status_label.config(text="Anwendungsdaten bereit", style='Success.PreLoading.TLabel')

        # --- 3. Schleife fortsetzen oder beenden ---
        if not self.db_ready or not self.data_ready:
            # Mindestens ein Thread (oder beide) läuft noch ODER wurde noch nicht geprüft
            self.after(100, self._check_startup_threads)
        else:
            # BEIDE Threads sind beendet (oder fehlgeschlagen)
            print("[DEBUG] LoginWindow: Beide Start-Threads sind abgeschlossen.")
            # Warte kurz, damit der Benutzer den Erfolg sieht, dann blende aus
            self.after(500, self.pre_login_loading_frame.pack_forget)

    def attempt_login(self, event=None):
        if not self.login_button_enabled:
            print("[DEBUG] Login-Versuch abgeblockt (DB noch nicht bereit).")
            return

        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()

        if not vorname or not name or not password:
            messagebox.showerror("Eingabe fehlt", "Bitte Vorname, Nachname und Passwort eingeben.", parent=self)
            return

        user_data = authenticate_user(vorname, name, password)

        if user_data:

            # --- NEU (Schritt 4): Dynamisches Hauptfenster ermitteln (Regel 2 & 4) ---
            try:
                # Die Rolle des Benutzers holen (z.B. "Admin")
                user_role = user_data.get('role')

                # Die DB fragen, welches Fenster (z.B. "main_admin_window")
                # (Regel 1) get_main_window_for_role hat einen eingebauten Fallback,
                # falls die Rolle (z.B. "SuperAdmin") noch nicht in der 'roles'-Tabelle
                # eingetragen ist, aber im ENUM existiert.
                main_window_name = get_main_window_for_role(user_role)

                # Den Fensternamen zum user_data-Dict hinzufügen
                user_data['main_window'] = main_window_name
                print(f"[DEBUG] LoginWindow: Rolle '{user_role}' -> Fenster '{main_window_name}' zugewiesen.")

            except Exception as e:
                print(f"[FEHLER] LoginWindow: Konnte Hauptfenster für Rolle '{user_role}' nicht ermitteln: {e}")
                # (Regel 1) Fallback, falls get_main_window_for_role selbst fehlschlägt
                user_data['main_window'] = 'main_admin_window' if user_role in ["Admin",
                                                                                "SuperAdmin"] else 'main_user_window'
            # --- ENDE NEU ---

            log_user_login(user_data['id'], user_data['vorname'], user_data['name'])

            # boot_loader.py (self.app) erhält jetzt user_data inkl. 'main_window'
            self.app.on_login_success(self, user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    def show_loading_ui(self):
        """
        Versteckt das Login-Formular und zeigt die Lade-Animation (POST-Login).
        """
        print("[DEBUG] LoginWindow.show_loading_ui: Zeige Lade-Animation (Post-Login).")
        self.main_frame.pack_forget()

        # Stelle sicher, dass der Pre-Login-Lader auch weg ist
        self.pre_login_loading_frame.pack_forget()

        self.loading_label.pack(pady=(20, 10), fill='x', padx=40)
        self.progress_bar.pack(pady=10, fill='x', padx=40)
        self.progress_bar.start(15)

    def show_login_ui(self):
        """
        Versteckt die Lade-Animation (POST-Login) und zeigt das Login-Formular wieder an.
        (Wird vom boot_loader bei einem Fehler beim Laden des Hauptfensters aufgerufen)
        """
        print("[DEBUG] LoginWindow.show_login_ui: Zeige Login-Formular (nach Ladefehler).")
        self.loading_label.pack_forget()
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

        self.main_frame.pack()

        # --- Status-Flags zurücksetzen ---
        self.db_ready = False
        self.data_ready = False  # NEU
        self.login_button_enabled = False
        # ---------------------------------

        # --- Threads neu starten (wichtig!) ---
        print("[Boot Loader] Starte Pre-Warming Thread (erneut)...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        print("[Boot Loader] Starte Common-Data-Pre-Loading Thread (erneut)...")
        self.preload_thread = threading.Thread(target=self.app.preload_common_data, daemon=True)
        self.preload_thread.start()

        # Aktualisiere die Thread-Referenzen in der App
        self.app.prewarm_thread = self.prewarm_thread
        self.app.preload_thread = self.preload_thread
        # --- Ende ---

        # --- UI der Ladebalken zurücksetzen ---
        self.pre_login_loading_frame.pack(fill='x', padx=40, pady=(10, 0))

        self.db_status_label.config(text="Verbindung wird erneut geprüft...", style='PreLoading.TLabel')
        self.db_progressbar.config(value=0)

        self.data_status_label.config(text="Lade Anwendungsdaten...", style='PreLoading.TLabel')
        self.data_progressbar.config(value=0)

        self.login_button.config(state="disabled")

        # Den neuen Checker starten
        self.after(100, self._check_startup_threads)

    # ---------------------

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)