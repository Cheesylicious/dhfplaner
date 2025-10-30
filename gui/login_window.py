# gui/login_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import authenticate_user, get_user_count, log_user_login
from .registration_window import RegistrationWindow
from .password_reset_window import PasswordResetWindow
import webbrowser  # Beibehalten

# --- NEUE IMPORTE ---
import threading
from database import db_core  # Um den Pool-Status zu prüfen


class LoginWindow(tk.Toplevel):
    def __init__(self, master, app, prewarm_thread):
        """
        Nimmt jetzt den 'prewarm_thread' entgegen, um den
        Verbindungsaufbau zu überwachen.
        """
        print("[DEBUG] LoginWindow.__init__: Wird initialisiert.")
        super().__init__(master)
        self.app = app

        # --- INNOVATION: Pre-Warming-Thread speichern ---
        self.prewarm_thread = prewarm_thread
        # ------------------------------------------------

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
        # --------------------------------------------

        self.protocol("WM_DELETE_WINDOW", self.app.on_app_close)
        self.create_widgets(style)

        self.attributes('-fullscreen', True)
        self.deiconify()
        self.lift()
        self.focus_force()

        # --- INNOVATION: Starte den Checker für den Pre-Warming-Thread ---
        if self.prewarm_thread:
            self.after(100, self._check_prewarm_thread)
        else:
            # Fallback
            print("[WARNUNG] Kein Pre-Warming-Thread an LoginWindow übergeben.")
            self.db_status_label.config(text="Fehler: Pre-Warming nicht gestartet.")
            self.db_progressbar.stop()  # Stoppt indeterminate mode
            self.login_button.config(state="normal")
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

        # --- INNOVATION: Pre-Login Lade-Widgets (angepasst) ---
        self.pre_login_loading_frame = ttk.Frame(self.wrapper_frame, style='TFrame')
        self.pre_login_loading_frame.pack(fill='x', padx=40, pady=(10, 0))

        self.db_status_label = ttk.Label(self.pre_login_loading_frame, text="Verbinde mit Datenbank...",
                                         style='PreLoading.TLabel', anchor="center")
        self.db_status_label.pack(fill='x')

        # Umgestellt auf 'determinate'
        self.db_progressbar = ttk.Progressbar(self.pre_login_loading_frame, mode='determinate',
                                              style='PreLoading.Horizontal.TProgressbar',
                                              maximum=100, value=0)  # Startet bei 0
        self.db_progressbar.pack(fill='x', pady=(5, 0))
        # .start() wird entfernt, da wir den Wert manuell setzen
        # -------------------------------------------------------------

        # --- Post-Login Lade-Widgets (im wrapper_frame) ---
        self.loading_label = ttk.Label(self.wrapper_frame, text="Lade Hauptfenster, bitte warten...",
                                       style='Loading.TLabel', anchor="center")
        self.progress_bar = ttk.Progressbar(self.wrapper_frame, mode='indeterminate',
                                            style='Loading.Horizontal.TProgressbar')
        # -------------------------------------------------

    # --- FUNKTION ÜBERARBEITET ---
    def _check_prewarm_thread(self):
        """
        Prüft, ob der Pre-Warming-Thread fertig ist UND
        simuliert den Ladefortschritt.
        """
        # Prüfen ob das Fenster noch existiert
        if not self.winfo_exists():
            return

        if self.prewarm_thread.is_alive():
            # Thread läuft noch, Ladebalken simulieren

            # --- NEU: Simulierter Fortschritt ---
            current_val = self.db_progressbar['value']
            if current_val < 95:
                # Erhöht den Balken langsam.
                # (100 Schritte * 100ms = 10 Sekunden für 100%)
                self.db_progressbar.step(1)
                # --- ENDE NEU ---

            self.after(100, self._check_prewarm_thread)
        else:
            # Thread ist beendet
            print("[DEBUG] LoginWindow: Pre-Warming-Thread ist beendet.")

            if db_core.db_pool is not None and db_core._db_initialized:
                # Erfolg!
                print("[DEBUG] LoginWindow: DB-Pool ist bereit.")

                # --- NEU: Auf 100% setzen und ausblenden ---
                self.db_progressbar['value'] = 100
                self.db_status_label.config(text="Verbindung bereit.", foreground="#2ecc71")  # Grüner Text
                self.login_button.config(state="normal")
                # Nach 500ms den Lade-Frame ausblenden
                self.after(500, self.pre_login_loading_frame.pack_forget)
                # --- ENDE NEU ---
            else:
                # Fehler!
                print("[FEHLER] LoginWindow: Pre-Warming ist fehlgeschlagen (Pool ist None).")
                self.db_status_label.config(text="Datenbank-Verbindung fehlgeschlagen.", foreground="red")
                self.db_progressbar.pack_forget()  # Nur den Balken verstecken

    def attempt_login(self, event=None):
        if self.login_button.cget("state") == "disabled":
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
            log_user_login(user_data['id'], user_data['vorname'], user_data['name'])
            self.app.on_login_success(self, user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    def show_loading_ui(self):
        """
        Versteckt das Login-Formular und zeigt die Lade-Animation (POST-Login).
        """
        print("[DEBUG] LoginWindow.show_loading_ui: Zeige Lade-Animation (Post-Login).")
        self.main_frame.pack_forget()

        self.pre_login_loading_frame.pack_forget()

        self.loading_label.pack(pady=(20, 10), fill='x', padx=40)
        self.progress_bar.pack(pady=10, fill='x', padx=40)
        self.progress_bar.start(15)

    # --- FUNKTION ÜBERARBEITET ---
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

        print("[Boot Loader] Starte Pre-Warming Thread (erneut)...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        self.pre_login_loading_frame.pack(fill='x', padx=40, pady=(10, 0))
        self.db_status_label.config(text="Verbindung wird erneut geprüft...", foreground="#bdc3c7")

        # --- NEU: Determinate-Balken zurücksetzen ---
        self.db_progressbar.pack(fill='x', pady=(5, 0))
        self.db_progressbar.config(value=0)  # Zurück auf 0
        # --- ENDE NEU ---

        self.login_button.config(state="disabled")

        self.after(100, self._check_prewarm_thread)

    # ---------------------

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)