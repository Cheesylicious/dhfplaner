# gui/login_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import check_login, get_user_count
from .registration_window import RegistrationWindow
from .password_change_window import PasswordChangeWindow
from .password_reset_window import PasswordResetWindow

__version__ = "1.0.0"


class LoginWindow(tk.Toplevel):
    def __init__(self, master, login_callback):
        super().__init__(master)
        self.master = master
        self.login_callback = login_callback
        self.title("DHF-Planer - Login")

        self.attributes('-fullscreen', True)
        self.configure(bg='#2c3e50')

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Segoe UI', 10, 'bold'),
                        borderwidth=0)
        style.map('TButton', background=[('active', '#2980b9')])
        style.configure('Small.TButton', font=('Segoe UI', 8))
        style.configure('Link.TLabel', foreground='#3498db', font=('Segoe UI', 9, 'underline'))

        self.protocol("WM_DELETE_WINDOW", self.master.destroy)
        self.create_widgets(style)

    def create_widgets(self, style):
        wrapper_frame = ttk.Frame(self, style='TFrame')
        wrapper_frame.pack(expand=True)

        main_frame = ttk.Frame(wrapper_frame, padding="40", style='TFrame')
        main_frame.pack()

        ttk.Label(main_frame, text=f"DHF Planer v{__version__}", font=("Segoe UI", 28, "bold")).pack(pady=(0, 40))

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

        reset_link = ttk.Label(main_frame, text="Passwort vergessen?", style='Link.TLabel', cursor="hand2")
        reset_link.pack()
        reset_link.bind("<Button-1>", self.open_password_reset)

        user_count = get_user_count()
        if user_count == 0:
            reg_frame = ttk.Frame(main_frame, style='TFrame')
            reg_frame.pack(pady=10)
            ttk.Label(reg_frame, text="Keine Benutzer gefunden.", foreground="#bdc3c7").pack()
            reg_button = ttk.Button(reg_frame, text="Ersten Admin registrieren", command=self.open_registration)
            reg_button.pack(pady=5)

        footer_frame = ttk.Frame(self, style='TFrame', padding=10)
        footer_frame.pack(side="bottom", fill="x")
        update_button = ttk.Button(footer_frame, text="Update", command=self.check_for_updates, style='Small.TButton')
        update_button.pack(side="right")

    def attempt_login(self, event=None):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()
        user_data = check_login(vorname, name, password)
        if user_data:
            if user_data['password_changed'] == 0:
                self.withdraw()
                PasswordChangeWindow(self, user_data, self.login_callback)
            else:
                self.login_callback(user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)

    def check_for_updates(self):
        messagebox.showinfo("Update", "Diese Funktion ist noch nicht implementiert.", parent=self)

    def clear_input_fields(self):
        self.vorname_entry.delete(0, tk.END)
        self.name_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.vorname_entry.focus_set()