import tkinter as tk
from tkinter import ttk, messagebox
# HIER WIRD 'add_user' durch 'register_user' ersetzt
from database.db_users import register_user, get_user_count

class RegistrationWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Registrierung")
        self.geometry("400x300")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        # Style-Konfiguration
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('TButton', font=('Helvetica', 10), padding=5)
        style.configure('TEntry', font=('Helvetica', 10), padding=5)

        self.create_widgets(style)

    def create_widgets(self, style):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(expand=True, fill='both')

        ttk.Label(main_frame, text="Vorname:", style='TLabel').grid(row=0, column=0, sticky='w', pady=5, padx=5)
        self.vorname_entry = ttk.Entry(main_frame, style='TEntry')
        self.vorname_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(main_frame, text="Name:", style='TLabel').grid(row=1, column=0, sticky='w', pady=5, padx=5)
        self.name_entry = ttk.Entry(main_frame, style='TEntry')
        self.name_entry.grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(main_frame, text="Passwort:", style='TLabel').grid(row=2, column=0, sticky='w', pady=5, padx=5)
        self.password_entry = ttk.Entry(main_frame, show="*", style='TEntry')
        self.password_entry.grid(row=2, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(main_frame, text="Passwort bestätigen:", style='TLabel').grid(row=3, column=0, sticky='w', pady=5, padx=5)
        self.confirm_password_entry = ttk.Entry(main_frame, show="*", style='TEntry')
        self.confirm_password_entry.grid(row=3, column=1, sticky='ew', pady=5, padx=5)

        reg_button = ttk.Button(main_frame, text="Registrieren", command=self.register, style='TButton')
        reg_button.grid(row=4, column=0, columnspan=2, pady=20)

        main_frame.columnconfigure(1, weight=1)

    def register(self):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()
        confirm_password = self.confirm_password_entry.get()

        if not all([vorname, name, password, confirm_password]):
            messagebox.showerror("Fehler", "Alle Felder müssen ausgefüllt sein.", parent=self)
            return

        if password != confirm_password:
            messagebox.showerror("Fehler", "Die Passwörter stimmen nicht überein.", parent=self)
            return

        # Wenn noch kein Benutzer existiert, wird der erste als SuperAdmin registriert
        role = "SuperAdmin" if get_user_count() == 0 else "Benutzer"

        # HIER WIRD der Funktionsaufruf angepasst
        success, message = register_user(vorname, name, password, role)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.destroy()
        else:
            messagebox.showerror("Fehler bei der Registrierung", message, parent=self)