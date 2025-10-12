# gui/registration_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import add_user, get_user_count


class RegistrationWindow(tk.Toplevel):
    def __init__(self, master, callback=None):
        super().__init__(master)
        self.callback = callback
        self.title("Neuen Benutzer registrieren")
        self.geometry("400x420")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)

        style = ttk.Style(self)
        style.configure("TEntry", fieldbackground="white", foreground="black", font=("Segoe UI", 10))

        if get_user_count() == 0:
            ttk.Label(main_frame, text="Der erste registrierte Benutzer wird automatisch zum Administrator.",
                      wraplength=350, foreground="blue").pack(pady=(0, 15))

        fields = {
            "Vorname:": tk.StringVar(),
            "Nachname:": tk.StringVar(),
            "Passwort:": tk.StringVar(),
            "Passwort wiederholen:": tk.StringVar()
        }
        self.vars = list(fields.values())

        for label, var in fields.items():
            ttk.Label(main_frame, text=label).pack(anchor="w")
            entry = ttk.Entry(main_frame, textvariable=var)
            if "Passwort" in label:
                entry.config(show="*")
            entry.pack(fill="x", pady=(2, 10), ipady=2)

        ttk.Button(main_frame, text="Registrieren", command=self.attempt_registration).pack(pady=15)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        if self.callback:
            self.callback()
        self.destroy()

    def attempt_registration(self):
        vorname, name, pw1, pw2 = [var.get().strip() for var in self.vars]

        if not all((vorname, name, pw1, pw2)):
            messagebox.showwarning("Fehlende Eingabe", "Bitte füllen Sie alle Felder aus.", parent=self)
            return
        if pw1 != pw2:
            messagebox.showerror("Fehler", "Die Passwörter stimmen nicht überein.", parent=self)
            return

        success, message = add_user(vorname, name, pw1)

        if success:
            messagebox.showinfo("Erfolg", "Der Benutzer wurde erfolgreich angelegt!", parent=self)
            self.on_close()
        else:
            messagebox.showerror("Fehler", message, parent=self)