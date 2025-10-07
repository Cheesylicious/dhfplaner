# gui/login_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_manager import check_login, get_user_count
from gui.registration_window import RegistrationWindow


class LoginWindow(tk.Toplevel):
    BG_COLOR = "#212529"
    FRAME_COLOR = "#343a40"
    TEXT_COLOR = "#dee2e6"
    ACCENT_COLOR = "#0d6efd"
    ACCENT_HOVER = "#0b5ed7"

    def __init__(self, master, login_callback):
        super().__init__(master)
        self.login_callback = login_callback
        self.master = master
        self.title("Anmeldung")
        self.attributes('-fullscreen', True)
        self.configure(bg=self.BG_COLOR)
        self.bind("<Escape>", lambda event: self.attributes("-fullscreen", False))

        style = ttk.Style(self)
        style.configure("TLabel", background=self.FRAME_COLOR, foreground=self.TEXT_COLOR, font=("Segoe UI", 12))
        style.configure("TFrame", background=self.FRAME_COLOR)
        style.configure("TEntry", fieldbackground="white", foreground="black", borderwidth=0, font=("Segoe UI", 12))
        style.configure("Login.TButton", font=("Segoe UI", 14, "bold"), foreground="white",
                        background=self.ACCENT_COLOR, padding=10, borderwidth=0)
        style.map("Login.TButton", background=[('active', self.ACCENT_HOVER)])

        outer_frame = tk.Frame(self, bg=self.FRAME_COLOR, bd=0)
        outer_frame.place(relx=0.5, rely=0.5, anchor='center')
        center_frame = tk.Frame(outer_frame, bg=self.FRAME_COLOR, padx=50, pady=40)
        center_frame.pack()

        ttk.Label(center_frame, text="Willkommen zurück", font=("Segoe UI", 24, "bold")).pack(pady=(0, 10))
        ttk.Label(center_frame, text="Bitte melden Sie sich an", font=("Segoe UI", 12)).pack(pady=(0, 30))

        # GEÄNDERT: Zwei Felder für Vorname und Nachname
        self.vorname_var = tk.StringVar()
        ttk.Label(center_frame, text="Vorname").pack(anchor="w")
        self.vorname_entry = ttk.Entry(center_frame, textvariable=self.vorname_var, width=30, font=("Segoe UI", 14))
        self.vorname_entry.pack(pady=(5, 10), ipady=5)

        self.nachname_var = tk.StringVar()
        ttk.Label(center_frame, text="Nachname").pack(anchor="w")
        self.nachname_entry = ttk.Entry(center_frame, textvariable=self.nachname_var, width=30, font=("Segoe UI", 14))
        self.nachname_entry.pack(pady=(5, 15), ipady=5)

        self.pass_var = tk.StringVar()
        ttk.Label(center_frame, text="Passwort").pack(anchor="w")
        self.pass_entry = ttk.Entry(center_frame, textvariable=self.pass_var, show="*", width=30, font=("Segoe UI", 14))
        self.pass_entry.pack(pady=(5, 25), ipady=5)
        self.pass_entry.bind("<Return>", self.attempt_login)

        login_button = ttk.Button(center_frame, text="Anmelden", command=self.attempt_login, style="Login.TButton",
                                  width=25)
        login_button.pack(pady=10)

        if get_user_count() == 0:
            reg_button = ttk.Button(center_frame, text="Ersten Admin registrieren", command=self.open_registration)
            reg_button.pack(pady=5)

        quit_button = ttk.Button(center_frame, text="Beenden", command=self.master.on_app_close)
        quit_button.pack(pady=15)

        self.vorname_entry.focus()

    def open_registration(self):
        RegistrationWindow(self)

    def attempt_login(self, event=None):
        # GEÄNDERT: Liest Vorname und Nachname aus
        vorname = self.vorname_var.get().strip()
        nachname = self.nachname_var.get().strip()
        password = self.pass_var.get().strip()

        if not vorname or not nachname or not password:
            messagebox.showwarning("Eingabe fehlt", "Bitte füllen Sie alle Felder aus.", parent=self)
            return

        # GEÄNDERT: Übergibt Vorname und Nachname an die Datenbankfunktion
        user_data = check_login(vorname, nachname, password)

        if user_data:
            self.login_callback(user_data)
        else:
            messagebox.showerror("Fehler", "Falscher Vor- oder Nachname bzw. Passwort.", parent=self)