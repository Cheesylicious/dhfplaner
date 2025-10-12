# gui/user_edit_window.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
from tkcalendar import DateEntry
from database.db_dogs import get_available_dogs
from database.db_users import update_user
from database.db_admin import create_user_by_admin, admin_reset_password


class UserEditWindow(tk.Toplevel):
    def __init__(self, master, user_id, user_data, callback, is_new, allowed_roles):
        super().__init__(master)
        self.user_id = user_id
        self.user_data = user_data if user_data is not None else {}
        self.callback = callback
        self.is_new = is_new
        self.allowed_roles = allowed_roles

        title = "Neuen Benutzer anlegen" if self.is_new else f"Benutzer bearbeiten: {self.user_data.get('vorname', '')} {self.user_data.get('name', '')}"
        self.title(title)

        self.geometry("480x650")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("TEntry", fieldbackground="white", foreground="black", font=("Segoe UI", 10))
        style.configure("Readonly.TEntry", fieldbackground="#f0f0f0", foreground="#555555")

        self.vars = {}
        self.widgets = {}
        row_index = 0

        readonly_fields = ['password_hash', 'urlaub_rest']

        field_order = [
            ('vorname', 'Vorname'), ('name', 'Nachname'), ('geburtstag', 'Geburtstag'),
            ('telefon', 'Telefon'), ('entry_date', 'Eintrittsdatum'), ('urlaub_gesamt', 'Urlaub Gesamt'),
            ('urlaub_rest', 'Urlaub Rest'), ('diensthund', 'Diensthund'), ('role', 'Rolle'),
            ('password_hash', 'Passwort Hash'), ('has_seen_tutorial', 'Tutorial gesehen'),
            ('password_changed', 'Passwort geändert')
        ]

        for key, display_name in field_order:
            if self.is_new and key in readonly_fields + ['password_hash']:
                continue

            ttk.Label(main_frame, text=f"{display_name}:").grid(row=row_index, column=0, sticky="w", pady=5,
                                                                padx=(0, 10))

            if key in ["geburtstag", "entry_date"]:
                date_val = None
                if self.user_data.get(key):
                    try:
                        date_val = datetime.strptime(self.user_data.get(key), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pass
                widget = DateEntry(main_frame, date_pattern='dd.mm.yyyy', date=date_val)
                self.widgets[key] = widget

            elif key == 'diensthund':
                self.vars[key] = tk.StringVar(value=self.user_data.get(key, 'Kein'))
                dog_options = get_available_dogs()
                current_dog = self.user_data.get('diensthund')
                if current_dog and current_dog not in dog_options:
                    dog_options.append(current_dog)
                dog_options.insert(0, "Kein")
                widget = ttk.Combobox(main_frame, textvariable=self.vars[key], values=sorted(dog_options),
                                      state="readonly")

            elif key == 'role':
                self.vars[key] = tk.StringVar(value=self.user_data.get('role', 'Benutzer'))
                widget = ttk.Combobox(main_frame, textvariable=self.vars[key], values=self.allowed_roles,
                                      state="readonly")
                if not self.allowed_roles: widget.config(state="disabled")

            elif key in ['has_seen_tutorial', 'password_changed']:
                val = self.user_data.get(key, 0)
                self.vars[key] = tk.StringVar(value="Ja" if val == 1 else "Nein")
                widget = ttk.Combobox(main_frame, textvariable=self.vars[key], values=["Ja", "Nein"], state="readonly")

            else:
                self.vars[key] = tk.StringVar(value=str(self.user_data.get(key, "")))
                style = "Readonly.TEntry" if key in readonly_fields else "TEntry"
                widget = ttk.Entry(main_frame, textvariable=self.vars[key], style=style)
                if key in readonly_fields:
                    widget.config(state='readonly')

            widget.grid(row=row_index, column=1, sticky="ew", pady=5, ipady=2)
            row_index += 1

        if self.is_new:
            ttk.Label(main_frame, text="Passwort:").grid(row=row_index, column=0, sticky="w", pady=5, padx=(0, 10))
            self.vars['password'] = tk.StringVar()
            ttk.Entry(main_frame, textvariable=self.vars['password'], show="*").grid(row=row_index, column=1,
                                                                                     sticky="ew", pady=5, ipady=2)
            row_index += 1
        else:
            ttk.Button(main_frame, text="Passwort zurücksetzen", command=self.reset_password).grid(row=row_index,
                                                                                                   column=0,
                                                                                                   columnspan=2,
                                                                                                   pady=15)
            row_index += 1

        button_bar = ttk.Frame(main_frame)
        button_bar.grid(row=row_index, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Speichern", command=self.save).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def reset_password(self):
        new_password = simpledialog.askstring("Passwort zurücksetzen", "Geben Sie ein neues temporäres Passwort ein:",
                                              parent=self, show='*')
        if new_password:
            success, message = admin_reset_password(self.user_id, new_password)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def save(self):
        updated_data = {key: var.get().strip() for key, var in self.vars.items()}

        for key, widget in self.widgets.items():
            try:
                date_obj = widget.get_date()
                updated_data[key] = date_obj.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                updated_data[key] = ""

        if not updated_data.get("vorname") or not updated_data.get("name"):
            messagebox.showwarning("Eingabe fehlt", "Vorname und Name dürfen nicht leer sein.", parent=self)
            return

        if self.is_new and not updated_data.get("password"):
            messagebox.showwarning("Eingabe fehlt", "Bei neuen Benutzern muss ein Passwort vergeben werden.",
                                   parent=self)
            return

        if updated_data.get('diensthund') == "Kein":
            updated_data['diensthund'] = ""

        updated_data['has_seen_tutorial'] = 1 if updated_data.get('has_seen_tutorial') == 'Ja' else 0
        updated_data['password_changed'] = 1 if updated_data.get('password_changed') == 'Ja' else 0

        success = False
        message = ""
        if self.is_new:
            success = create_user_by_admin(updated_data)
            message = "Mitarbeiter erfolgreich hinzugefügt." if success else "Ein Mitarbeiter mit diesem Namen existiert bereits."
        else:
            success = update_user(self.user_id, updated_data)
            message = "Mitarbeiterdaten erfolgreich aktualisiert." if success else "Fehler beim Aktualisieren der Mitarbeiterdaten."

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)