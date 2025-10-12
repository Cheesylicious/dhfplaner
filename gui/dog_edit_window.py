# gui/dog_edit_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from tkcalendar import DateEntry


class DogEditWindow(tk.Toplevel):
    def __init__(self, master, dog_data, callback, is_new):
        super().__init__(master)
        self.dog_data = dog_data
        self.callback = callback
        self.is_new = is_new

        self.title(
            "Neuen Diensthund anlegen" if self.is_new else f"Diensthund bearbeiten: {self.dog_data.get('name', '')}")
        self.geometry("450x550")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("TEntry", fieldbackground="white", foreground="black", font=("Segoe UI", 10))

        self.vars = {}
        self.widgets = {}
        row_index = 0

        fields = {
            "Name:": "name", "Rasse:": "breed", "Chipnummer:": "chip_number",
            "Geburtsdatum:": "birth_date", "Zugang (Datum):": "acquisition_date", "Abgang (Datum):": "departure_date",
            "Letzte DPO:": "last_dpo_date", "Impftermine (Info):": "vaccination_info"
        }

        for label, key in fields.items():
            ttk.Label(main_frame, text=label).grid(row=row_index, column=0, sticky="w", pady=5, padx=(0, 10))

            if "date" in key or "datum" in key:
                date_val = None
                if self.dog_data.get(key):
                    try:
                        date_val = datetime.strptime(self.dog_data[key], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pass
                widget = DateEntry(main_frame, date_pattern='dd.mm.yyyy', date=date_val, foreground="black",
                                   headersforeground="black")
                self.widgets[key] = widget
            else:
                self.vars[key] = tk.StringVar(value=self.dog_data.get(key, ""))
                widget = ttk.Entry(main_frame, textvariable=self.vars[key])

            widget.grid(row=row_index, column=1, sticky="ew", pady=5, ipady=2)
            row_index += 1

        button_bar = ttk.Frame(main_frame)
        button_bar.grid(row=row_index, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Speichern", command=self.save).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def save(self):
        updated_data = {key: var.get().strip() for key, var in self.vars.items()}

        for key, widget in self.widgets.items():
            date_obj = widget.get_date()
            updated_data[key] = date_obj.strftime('%Y-%m-%d')

        if not updated_data.get("name") or not updated_data.get("chip_number"):
            messagebox.showwarning("Eingabe fehlt", "Name und Chipnummer sind Pflichtfelder.", parent=self)
            return

        self.callback(self.dog_data.get("id"), updated_data)
        self.destroy()