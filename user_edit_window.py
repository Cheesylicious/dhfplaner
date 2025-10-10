# gui/user_edit_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from tkcalendar import DateEntry
from .column_manager import ColumnManager
# NEUE IMPORTE
from database.db_manager import get_available_dogs, get_dog_assignment_count


class UserEditWindow(tk.Toplevel):
    def __init__(self, master, user_id, user_data, callback, is_new, allowed_roles):
        super().__init__(master)
        self.user_id = user_id
        self.user_data = user_data
        self.callback = callback
        self.is_new = is_new
        self.allowed_roles = allowed_roles

        self.title(
            "Neuen Benutzer anlegen" if self.is_new else f"Benutzer bearbeiten: {self.user_data['vorname']} {self.user_data['name']}")

        self.geometry("450x520")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("TEntry", fieldbackground="white", foreground="black", font=("Segoe UI", 10))

        all_columns = ColumnManager.load_config().get('all_columns', {})

        self.vars = {}
        self.widgets = {}
        row_index = 0

        for key, display_name in all_columns.items():
            if key in ['urlaub_rest']: continue

            ttk.Label(main_frame, text=f"{display_name}:").grid(row=row_index, column=0, sticky="w", pady=5,
                                                                padx=(0, 10))

            if "date" in key or "geburtstag" in key:
                date_val = None
                if self.user_data.get(key):
                    try:
                        date_val = datetime.strptime(self.user_data.get(key), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pass
                widget = DateEntry(main_frame, date_pattern='dd.mm.yyyy', date=date_val, foreground="black",
                                   headersforeground="black")
                self.widgets[key] = widget

            # GEÄNDERT: Spezielle Logik für das "Diensthund"-Feld
            elif key == 'diensthund':
                self.vars['diensthund'] = tk.StringVar(value=self.user_data.get('diensthund', ''))

                # Hole die Liste der verfügbaren Hunde
                dog_options = get_available_dogs()
                current_dog = self.user_data.get('diensthund')

                # Füge den aktuellen Hund des Benutzers hinzu, falls er nicht in der Liste ist
                if current_dog and current_dog not in dog_options:
                    dog_options.append(current_dog)

                # Füge eine Option hinzu, um die Zuweisung aufzuheben
                dog_options.insert(0, "Kein")

                widget = ttk.Combobox(main_frame, textvariable=self.vars['diensthund'], values=sorted(dog_options),
                                      state="readonly")

            elif key == 'role':
                self.vars['role'] = tk.StringVar(value=self.user_data.get('role', 'Benutzer'))
                widget = ttk.Combobox(main_frame, textvariable=self.vars['role'], values=self.allowed_roles,
                                      state="readonly")
                if not self.allowed_roles: widget.config(state="disabled")

            else:
                self.vars[key] = tk.StringVar(value=str(self.user_data.get(key, "")))
                widget = ttk.Entry(main_frame, textvariable=self.vars[key])

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
        messagebox.showinfo("Info", "Passwort-Reset-Funktion noch nicht implementiert.", parent=self)

    def save(self):
        updated_data = {key: var.get().strip() for key, var in self.vars.items()}

        for key, widget in self.widgets.items():
            date_obj = widget.get_date()
            updated_data[key] = date_obj.strftime('%Y-%m-%d')

        if not updated_data.get("vorname") or not updated_data.get("name"):
            messagebox.showwarning("Eingabe fehlt", "Vorname und Name dürfen nicht leer sein.", parent=self)
            return

        if self.is_new and not updated_data.get("password"):
            messagebox.showwarning("Eingabe fehlt", "Bei neuen Benutzern muss ein Passwort vergeben werden.",
                                   parent=self)
            return

        # NEU: Validierung der Hund-Zuweisung
        new_dog = updated_data.get('diensthund')
        original_dog = self.user_data.get('diensthund')

        # Prüfe nur, wenn sich die Zuweisung ändert und es nicht "Kein" ist
        if new_dog and new_dog != "Kein" and new_dog != original_dog:
            assignment_count = get_dog_assignment_count(new_dog)
            if assignment_count >= 2:
                messagebox.showerror("Fehler",
                                     f"Der Diensthund '{new_dog}' ist bereits {assignment_count} Mal zugewiesen und kann nicht weiter zugeteilt werden.",
                                     parent=self)
                return

        # Korrigiere "Kein" zu einem leeren String für die Datenbank
        if updated_data.get('diensthund') == "Kein":
            updated_data['diensthund'] = ""

        self.callback(self.user_id, updated_data)
        self.destroy()