# gui/password_change_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import change_password

class PasswordChangeWindow(tk.Toplevel):
    def __init__(self, master, user_data, login_callback):
        super().__init__(master)
        self.master = master
        self.user_data = user_data
        self.login_callback = login_callback
        self.title("DHF-Planer - Passwort ändern")

        self.attributes('-fullscreen', True)
        self.configure(bg='#2c3e50')

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Segoe UI', 10, 'bold'),
                        borderwidth=0)
        style.map('TButton', background=[('active', '#2980b9')])

        self.protocol("WM_DELETE_WINDOW", self.master.master.destroy)
        self.create_widgets(style)

    def create_widgets(self, style):
        wrapper_frame = ttk.Frame(self, style='TFrame')
        wrapper_frame.pack(expand=True)

        main_frame = ttk.Frame(wrapper_frame, padding="40", style='TFrame')
        main_frame.pack()

        ttk.Label(main_frame, text="Bitte ändern Sie Ihr Passwort", font=("Segoe UI", 24, "bold")).pack(pady=(0, 20))
        ttk.Label(main_frame, text="Dies ist Ihr erster Login. Zu Ihrer Sicherheit müssen Sie Ihr Passwort jetzt ändern.", wraplength=400, justify=tk.CENTER).pack(pady=(0, 20))

        form_frame = ttk.Frame(main_frame, style='TFrame')
        form_frame.pack(fill="x", pady=5)
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Neues Passwort:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.new_password_entry = ttk.Entry(form_frame, show="*", font=('Segoe UI', 12), width=30)
        self.new_password_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.new_password_entry.focus_set()

        ttk.Label(form_frame, text="Passwort bestätigen:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.confirm_password_entry = ttk.Entry(form_frame, show="*", font=('Segoe UI', 12))
        self.confirm_password_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.confirm_password_entry.bind("<Return>", self.attempt_change_password)

        self.change_button = ttk.Button(main_frame, text="Passwort ändern und anmelden", command=self.attempt_change_password, style='TButton')
        self.change_button.pack(pady=20, fill="x", ipady=8)

    def attempt_change_password(self, event=None):
        new_password = self.new_password_entry.get()
        confirm_password = self.confirm_password_entry.get()

        if not new_password or not confirm_password:
            messagebox.showerror("Fehler", "Bitte füllen Sie beide Felder aus.", parent=self)
            return

        if new_password != confirm_password:
            messagebox.showerror("Fehler", "Die Passwörter stimmen nicht überein.", parent=self)
            return

        success, message = change_password(self.user_data['id'], new_password)

        if success:
            messagebox.showinfo("Erfolg", "Ihr Passwort wurde erfolgreich geändert.", parent=self)
            self.user_data['password_changed'] = 1
            self.destroy()
            self.master.login_callback(self.user_data)
        else:
            messagebox.showerror("Fehler", message, parent=self)