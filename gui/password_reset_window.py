# gui/password_reset_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_admin import request_password_reset

class PasswordResetWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Passwort zurücksetzen")
        self.geometry("400x250")
        self.configure(bg='#2c3e50')
        self.transient(master)
        self.grab_set()

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Segoe UI', 10, 'bold'),
                        borderwidth=0)
        style.map('TButton', background=[('active', '#2980b9')])

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(expand=True, fill="both")

        ttk.Label(main_frame, text="Passwort zurücksetzen anfordern", font=("Segoe UI", 16, "bold")).pack(pady=(0, 10))
        ttk.Label(main_frame, text="Geben Sie Ihren Namen ein, um eine Anfrage an den Admin zu senden.", wraplength=350, justify=tk.CENTER).pack(pady=(0, 20))

        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill="x")
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Vorname:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.vorname_entry = ttk.Entry(form_frame, font=('Segoe UI', 12))
        self.vorname_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.vorname_entry.focus_set()

        ttk.Label(form_frame, text="Nachname:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.name_entry = ttk.Entry(form_frame, font=('Segoe UI', 12))
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.name_entry.bind("<Return>", self.submit_request)

        submit_button = ttk.Button(main_frame, text="Anfrage senden", command=self.submit_request)
        submit_button.pack(pady=20, fill="x", ipady=5)

    def submit_request(self, event=None):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()

        if not vorname or not name:
            messagebox.showerror("Fehler", "Bitte geben Sie Vor- und Nachnamen ein.", parent=self)
            return

        success, message = request_password_reset(vorname, name)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)