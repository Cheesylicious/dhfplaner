# gui/login_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import authenticate_user, get_user_count, log_user_login
from .registration_window import RegistrationWindow
from .password_reset_window import PasswordResetWindow
import webbrowser  # Beibehalten, falls es für andere Links genutzt wird


# WICHTIG: Die Imports von update_manager und LOCAL_VERSION sind entfernt,
# da der neue Launcher diese Aufgaben übernimmt.

class LoginWindow(tk.Toplevel):
    def __init__(self, master, app):
        print("[DEBUG] LoginWindow.__init__: Wird initialisiert.")
        super().__init__(master)
        self.app = app

        # Update-Variablen sind nicht mehr nötig, da der Launcher diese Aufgabe übernimmt.
        self.local_version = "0.0.0"  # Setze eine Platzhalterversion, wenn nötig.

        self.withdraw()  # Zuerst unsichtbar machen, um Flackern zu vermeiden

        self.title("DHF-Planer - Login")
        self.configure(bg='#2c3e50')

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Segoe UI', 10, 'bold'),
                        borderwidth=0)
        style.map('TButton', background=[('active', '#2980b9')])

        # --- NEU: Style für Ladebalken ---
        style.configure('Loading.TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 12))
        style.configure('Loading.Horizontal.TProgressbar', background='#3498db')
        # ---------------------------------

        self.protocol("WM_DELETE_WINDOW", self.app.on_app_close)
        self.create_widgets(style)

        # Die Update-Prüfung nach 100ms ist entfernt.

        # --- Auf Vollbildmodus umgestellt ---
        self.attributes('-fullscreen', True)

        self.deiconify()
        self.lift()
        self.focus_force()
        print("[DEBUG] LoginWindow.__init__: Initialisierung abgeschlossen, Fenster sichtbar.")

    # Die Methoden _version_button_click, _check_update_and_config_button und _start_blinking
    # MÜSSEN im neuen Setup GELÖSCHT werden, da sie UpdateManager-Logik enthalten.
    # Da sie im Originalcode außerhalb der Klasse waren (wenn sie nicht als Methoden definiert wurden),
    # musste ich sie nur aus der Klasse entfernen.

    def create_widgets(self, style):
        # Der Inhalt wird nun in einem Frame zentriert, damit es im Vollbild gut aussieht
        container = ttk.Frame(self, style='TFrame')
        container.pack(fill="both", expand=True)

        wrapper_frame = ttk.Frame(container, style='TFrame')
        wrapper_frame.place(relx=0.5, rely=0.5, anchor="center")  # Zentriert den Login-Block

        self.main_frame = ttk.Frame(wrapper_frame, padding="40", style='TFrame')
        self.main_frame.pack()

        # Version im Titel anpassen: Verwende Platzhalter oder entferne den Versionshinweis.
        # Der Versionshinweis verwendet nun den Platzhalter-Wert "0.0.0" oder kann ganz entfernt werden.
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

        # Enter-Bindung auf das Passwort-Feld
        self.password_entry.bind("<Return>", self.attempt_login)
        # Enter-Bindung auf die anderen Felder, um den Fokus zu wechseln
        self.vorname_entry.bind("<Return>", lambda e: self.name_entry.focus())
        self.name_entry.bind("<Return>", lambda e: self.password_entry.focus())

        self.login_button = ttk.Button(self.main_frame, text="Anmelden", command=self.attempt_login, style='TButton')
        self.login_button.pack(pady=20, fill="x", ipady=8)

        # ... (Restliche Widgets wie Registrieren/Passwort-Reset-Buttons)
        # (Hier annehmen, dass sie existieren, auch wenn sie im Snippet fehlen)
        self.button_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.button_frame.pack(fill='x')

        self.register_button = ttk.Button(self.button_frame, text="Registrieren", command=self.open_registration)
        self.register_button.pack(side='left', expand=True, fill='x', padx=(0, 5), ipady=4)

        self.reset_button = ttk.Button(self.button_frame, text="Passwort vergessen", command=self.open_password_reset)
        self.reset_button.pack(side='right', expand=True, fill='x', padx=(5, 0), ipady=4)

        # --- NEUE LADE-WIDGETS ---
        # (Werden unter dem main_frame im wrapper_frame platziert)
        self.loading_label = ttk.Label(wrapper_frame, text="Lade Hauptfenster, bitte warten...",
                                       style='Loading.TLabel', anchor="center")
        self.progress_bar = ttk.Progressbar(wrapper_frame, mode='indeterminate',
                                            style='Loading.Horizontal.TProgressbar')
        # ---------------------------

    def attempt_login(self, event=None):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()

        if not vorname or not name or not password:
            messagebox.showerror("Eingabe fehlt", "Bitte Vorname, Nachname und Passwort eingeben.", parent=self)
            return

        user_data = authenticate_user(vorname, name, password)

        if user_data:
            # Protokolliere Login-Event (NEU)
            log_user_login(user_data['id'], user_data['vorname'], user_data['name'])

            # Blinken stoppen (Logik ist entfernt, dieser Teil ist jetzt unnötig, aber ungefährlich)
            # if self.update_check_job:
            #    self.after_cancel(self.update_check_job)

            # Ruft die (jetzt überarbeitete) Thread-Start-Funktion im Bootloader auf
            self.app.on_login_success(self, user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    # --- NEUE FUNKTION ---
    def show_loading_ui(self):
        """
        Versteckt das Login-Formular und zeigt die Lade-Animation.
        Wird von boot_loader.py aufgerufen.
        """
        print("[DEBUG] LoginWindow.show_loading_ui: Zeige Lade-Animation.")
        # Login-Formular verstecken
        self.main_frame.pack_forget()

        # Lade-Widgets anzeigen
        self.loading_label.pack(pady=(20, 10), fill='x', padx=40)
        self.progress_bar.pack(pady=10, fill='x', padx=40)
        self.progress_bar.start(15)  # Startet die Animation

    # ---------------------

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)