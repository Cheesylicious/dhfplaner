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

        main_frame = ttk.Frame(wrapper_frame, padding="40", style='TFrame')
        main_frame.pack()

        # Version im Titel anpassen: Verwende Platzhalter oder entferne den Versionshinweis.
        # Der Versionshinweis verwendet nun den Platzhalter-Wert "0.0.0" oder kann ganz entfernt werden.
        ttk.Label(main_frame, text=f"DHF Planer", font=("Segoe UI", 28, "bold")).pack(
            pady=(0, 40))

        form_frame = ttk.Frame(main_frame, style='TFrame')
        form_frame.pack(fill="x", pady=5)
        form_frame.columnconfigure(1, weight=1)
        ttk.Label(form_frame, text="Vorname:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.vorname_entry = ttk.Entry(form_frame, font=('Segoe UI', 12), width=30)
        self.vorname_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.vorname_entry.focus_set()
        ttk.Label(form_frame, text="Nachname:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.name_entry = ttk.Entry(form_frame, font=('Segoe UI', 12))
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(form_frame, text="Passwort:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.password_entry = ttk.Entry(form_frame, show="*", font=('Segoe UI', 12))
        self.password_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.password_entry.bind("<Return>", self.attempt_login)
        self.login_button = ttk.Button(main_frame, text="Anmelden", command=self.attempt_login, style='TButton')
        self.login_button.pack(pady=20, fill="x", ipady=8)
        # ... restliche Widgets ...

        # Der Version Button (Update Manager) MUSS hier entfernt werden, da der Launcher ihn steuert.
        # Wenn der Button im Original-Code außerhalb von create_widgets war,
        # wurde er jetzt korrekt entfernt (falls er dorthin verschoben wurde).
        # Er wird NICHT MEHR erstellt, daher ist die Ausführung sicher.

    def attempt_login(self, event=None):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()
        user_data = authenticate_user(vorname, name, password)

        if user_data:
            # Protokolliere Login-Event (NEU)
            log_user_login(user_data['id'], user_data['vorname'], user_data['name'])

            # Blinken stoppen (Logik ist entfernt, dieser Teil ist jetzt unnötig, aber ungefährlich)
            # if self.update_check_job:
            #    self.after_cancel(self.update_check_job)

            self.app.on_login_success(self, user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)
