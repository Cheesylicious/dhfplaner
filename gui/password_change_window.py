# gui/password_change_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import update_user_password


class PasswordChangeWindow(tk.Toplevel):
    def __init__(self, master, user_data, app):
        super().__init__(master)
        self.app = app
        self.user_data = user_data

        self.withdraw()
        self.title("Initiales Passwort ändern")

        # --- KORREKTUR: Feste Größe durch Vollbildmodus ersetzt ---
        self.attributes('-fullscreen', True)
        # self.geometry("400x250") # Alte Zeile entfernt

        self.resizable(False, False)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('TButton', font=('Helvetica', 10), padding=5)
        style.configure('TEntry', font=('Helvetica', 10), padding=5)
        style.configure('Header.TLabel', font=('Helvetica', 12, 'bold'))
        self.protocol("WM_DELETE_WINDOW", self.app.on_app_close)
        self.create_widgets(style)

        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.focus_force()

    def create_widgets(self, style):
        # Container-Frame, um den Inhalt im Vollbild zu zentrieren
        container_frame = ttk.Frame(self)
        container_frame.pack(expand=True, fill='both')

        main_frame = ttk.Frame(container_frame, padding="20")
        # Platziert den eigentlichen Inhalt in der Mitte des Fensters
        main_frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(main_frame, text="Bitte ändern Sie Ihr initiales Passwort.", style='Header.TLabel').pack(pady=(0, 15))
        ttk.Label(main_frame, text="Neues Passwort:").pack(fill='x', padx=5)
        self.new_password_entry = ttk.Entry(main_frame, show="*", style='TEntry')
        self.new_password_entry.pack(fill='x', padx=5, pady=(0, 10))
        self.new_password_entry.focus_set()
        ttk.Label(main_frame, text="Passwort bestätigen:").pack(fill='x', padx=5)
        self.confirm_password_entry = ttk.Entry(main_frame, show="*", style='TEntry')
        self.confirm_password_entry.pack(fill='x', padx=5, pady=(0, 20))
        self.confirm_password_entry.bind("<Return>", self.change_password)
        change_button = ttk.Button(main_frame, text="Passwort ändern und Anmelden", command=self.change_password,
                                     style='TButton')
        change_button.pack()

    def change_password(self, event=None):
        new_password = self.new_password_entry.get()
        confirm_password = self.confirm_password_entry.get()

        if not new_password or not confirm_password:
            messagebox.showerror("Fehler", "Alle Felder müssen ausgefüllt sein.", parent=self)
            return
        if new_password != confirm_password:
            messagebox.showerror("Fehler", "Die Passwörter stimmen nicht überein.", parent=self)
            return

        user_id = self.user_data['id']
        self.user_data['password_changed'] = 1
        success, message = update_user_password(user_id, new_password)

        if success:
            messagebox.showinfo("Erfolg", "Passwort erfolgreich geändert.", parent=self)
            self.app.on_password_changed(self, self.user_data)
        else:
            messagebox.showerror("Fehler", f"Passwort konnte nicht geändert werden:\n{message}", parent=self)