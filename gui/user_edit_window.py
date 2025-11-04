import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
from tkcalendar import DateEntry
from database.db_dogs import get_available_dogs
# HIER WIRD 'update_user' durch 'update_user_details' ersetzt
from database.db_users import update_user_details
from database.db_admin import create_user_by_admin, admin_reset_password


class UserEditWindow(tk.Toplevel):
    # KORREKTUR: 'admin_user_id' als 7. Argument hinzugefügt
    def __init__(self, master, user_id, user_data, callback, is_new, allowed_roles, admin_user_id):
        super().__init__(master)
        self.user_id = user_id  # ID des Users, der bearbeitet wird
        # Stelle sicher, dass user_data ein Dictionary ist, auch wenn None übergeben wird
        self.user_data = user_data if user_data is not None else {}
        self.callback = callback
        self.is_new = is_new
        self.allowed_roles = allowed_roles
        self.admin_user_id = admin_user_id  # ID des Admins, der die Bearbeitung vornimmt

        title = "Neuen Benutzer anlegen" if self.is_new else f"Benutzer bearbeiten: {self.user_data.get('vorname', '')} {self.user_data.get('name', '')}"
        self.title(title)

        self.geometry("480x680")  # Höhe angepasst für neues Feld
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

        # KORREKTUR: last_seen zur Readonly-Liste hinzufügen
        readonly_fields = ['password_hash', 'urlaub_rest', 'last_seen']

        field_order = [
            ('vorname', 'Vorname'), ('name', 'Nachname'), ('geburtstag', 'Geburtstag'),
            ('telefon', 'Telefon'),
            ('last_ausbildung', 'Letzte Ausb.'), ('last_schiessen', 'Letztes Sch.'),
            ('entry_date', 'Eintrittsdatum'),
            ('activation_date', 'Aktiv ab Datum'),  # NEUES FELD
            ('urlaub_gesamt', 'Urlaub Gesamt'),
            ('urlaub_rest', 'Urlaub Rest'), ('diensthund', 'Diensthund'), ('role', 'Rolle'),
            ('password_hash', 'Passwort Hash'), ('has_seen_tutorial', 'Tutorial gesehen'),
            ('password_changed', 'Passwort geändert'),
            ('last_seen', 'Zuletzt Online')  # Hier belassen, da es unten als readonly behandelt wird
        ]

        # Datumsfelder für DateEntry-Widget (NICHT alle DATETIME-Felder)
        date_entry_fields = ["geburtstag", "entry_date", "activation_date", "last_ausbildung", "last_schiessen"]

        for key, display_name in field_order:
            if self.is_new and key in readonly_fields + ['password_hash', 'has_seen_tutorial', 'password_changed',
                                                         'last_ausbildung', 'last_schiessen']:
                continue
            if key == 'last_seen' and self.is_new:
                continue

            ttk.Label(main_frame, text=f"{display_name}:").grid(row=row_index, column=0, sticky="w", pady=5,
                                                                padx=(0, 10))

            # --- ANPASSUNG FÜR DATUMS-WIDGETS (DateEntry) ---
            if key in date_entry_fields:

                widget = DateEntry(main_frame, date_pattern='dd.mm.yyyy',
                                   locale='de_DE',
                                   selectmode='day', date=None)

                date_val = None
                db_value = self.user_data.get(key)

                if db_value:
                    date_str = str(db_value)
                    if date_str != 'None' and not date_str.startswith('0000-00-00'):
                        try:
                            if ' ' in date_str:
                                date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                                date_val = date_obj.date()
                            else:
                                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                                date_val = date_obj.date()
                        except (ValueError, TypeError):
                            pass

                if date_val:
                    widget.set_date(date_val)
                else:
                    widget.set_date(None)
                    widget.delete(0, 'end')

                self.widgets[key] = widget
            # --- ENDE ANPASSUNG DATUM ---

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
                # Normale Eingabefelder (auch last_seen, urlaub_gesamt, urlaub_rest)
                initial_value = self.user_data.get(key)

                # --- KORREKTUR: Handhabung von Datum/None für nicht-DateEntry-Felder ---
                if initial_value is None:
                    initial_value = ""
                elif key == 'last_seen' and isinstance(initial_value, datetime):
                    initial_value = initial_value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    initial_value = str(initial_value)
                # --- ENDE KORREKTUR ---

                self.vars[key] = tk.StringVar(value=initial_value)
                style_name = "Readonly.TEntry" if key in readonly_fields else "TEntry"
                widget = ttk.Entry(main_frame, textvariable=self.vars[key], style=style_name)
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
            # Annahme: user_id des angemeldeten Admins wird hier nicht benötigt,
            # da die Aktion von einem Admin-Fenster aus gestartet wird.
            # KORREKTUR: Wir verwenden self.admin_user_id für den Log-Eintrag
            success, message = admin_reset_password(self.user_id, new_password, self.admin_user_id)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def save(self):
        updated_data = {key: var.get().strip() for key, var in self.vars.items()}

        # --- LOGIK FÜR DATUMS-WIDGETS (um None/NULL zu erlauben) ---
        # (Diese Logik war bereits korrekt und bleibt unverändert)
        for key, widget in self.widgets.items():
            date_str = widget.get()  # Hole den Text-Wert (z.B. "29.10.2025" oder "")

            if not date_str:
                # Wenn Feld leer ist
                if key == 'entry_date':
                    # Entry date darf NICHT leer sein
                    messagebox.showwarning("Eingabe fehlt", "Das Eintrittsdatum darf nicht leer sein.", parent=self)
                    return
                else:
                    # Optionale Datumsfelder DÜRFEN leer sein (None -> NULL)
                    updated_data[key] = None
            else:
                # Wenn Feld nicht leer ist, versuche zu parsen
                try:
                    # get_date() parst den Text (dd.mm.yyyy) zu einem datetime.date Objekt
                    date_obj = widget.get_date()
                    updated_data[key] = date_obj.strftime('%Y-%m-%d')
                except (ValueError, TypeError):
                    # Wenn Parsen fehlschlägt (z.B. ungültige Eingabe wie "test")
                    if key == 'entry_date':
                        messagebox.showwarning("Eingabe ungültig", f"Das Eintrittsdatum ('{date_str}') ist ungültig.",
                                               parent=self)
                        return
                    else:
                        # Optionale Felder bei Fehler auf NULL setzen
                        updated_data[key] = None
        # --- ENDE DATUMS-LOGIK ---

        if not updated_data.get("vorname") or not updated_data.get("name"):
            messagebox.showwarning("Eingabe fehlt", "Vorname und Name dürfen nicht leer sein.", parent=self)
            return

        if self.is_new and not updated_data.get("password"):
            messagebox.showwarning("Eingabe fehlt", "Bei neuen Benutzern muss ein Passwort vergeben werden.",
                                   parent=self)
            return

        if updated_data.get('diensthund') == "Kein":
            updated_data['diensthund'] = ""  # In DB als Leerstring statt 'Kein' speichern

        updated_data['has_seen_tutorial'] = 1 if updated_data.get('has_seen_tutorial') == 'Ja' else 0
        updated_data['password_changed'] = 1 if updated_data.get('password_changed') == 'Ja' else 0

        success = False
        message = ""
        if self.is_new:
            # Annahme: create_user_by_admin erwartet ein Dictionary mit den Benutzerdaten
            # und die ID des Admins, der den Benutzer erstellt
            success, message = create_user_by_admin(updated_data, self.admin_user_id)
        else:
            # HIER WIRD der Funktionsaufruf angepasst
            # Wir übergeben die ID des Users (self.user_id), die Daten
            # und die ID des aktuellen Admins (self.admin_user_id)
            # KORREKTUR: self.admin_user_id statt self.user_id als 3. Argument
            success, message = update_user_details(self.user_id, updated_data, self.admin_user_id)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)