# gui/login_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import authenticate_user, get_user_count
from .registration_window import RegistrationWindow
from .password_reset_window import PasswordResetWindow


class LoginWindow(tk.Toplevel):
    def __init__(self, master, app):
        print("[DEBUG] LoginWindow.__init__: Wird initialisiert.")
        super().__init__(master)
        self.app = app

        # --- FINALE KORREKTUR ---
        # Wir entfernen alle Befehle, die einen Deadlock verursachen können
        # und machen das Fenster manuell sichtbar.
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

        # Fenster zentrieren und sichtbar machen
        self.update_idletasks()
        w = 500
        h = 350
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw / 2) - (w / 2)
        y = (sh / 2) - (h / 2)
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))
        self.deiconify()
        self.lift()
        self.focus_force()
        print("[DEBUG] LoginWindow.__init__: Initialisierung abgeschlossen, Fenster sichtbar.")

    def create_widgets(self, style):
        # Diese Methode bleibt unverändert
        wrapper_frame = ttk.Frame(self, style='TFrame')
        wrapper_frame.pack(expand=True)
        main_frame = ttk.Frame(wrapper_frame, padding="40", style='TFrame')
        main_frame.pack()
        ttk.Label(main_frame, text="DHF Planer v1.0.0", font=("Segoe UI", 28, "bold")).pack(pady=(0, 40))
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

    def attempt_login(self, event=None):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()
        user_data = authenticate_user(vorname, name, password)

        if user_data:
            self.app.on_login_success(self, user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)