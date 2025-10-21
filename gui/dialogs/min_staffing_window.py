# gui/dialogs/min_staffing_window.py
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import json
import os

from database.db_shifts import get_all_shift_types
from database.db_core import save_config_json  # Importieren der Speicherfunktion


class MinStaffingWindow(tk.Toplevel):
    def __init__(self, parent, current_rules, callback):
        super().__init__(parent)
        self.title("Besetzungsregeln")
        self.geometry("800x600")
        self.transient(parent)
        self.grab_set()

        self.callback = callback
        self.rules = current_rules  # Regeln vom Hauptfenster übernehmen
        self.shifts = get_all_shift_types()
        self.vars = {}

        self.create_widgets()

    def get_default_rules(self):
        # Diese Funktion wird jetzt als Fallback genutzt, falls keine Regeln übergeben werden
        return {
            "Mo-Do": {}, "Fr": {}, "Sa-So": {}, "Holiday": {}, "Daily": {},
            "Colors": {
                "alert_bg": "#FF5555",
                "overstaffed_bg": "#FFFF99",
                "success_bg": "#90EE90",
                "weekend_bg": "#EAF4FF",
                "holiday_bg": "#FFD700"
            }
        }

    def create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)

        days_map = {
            "Mo-Do": "Montag - Donnerstag",
            "Fr": "Freitag",
            "Sa-So": "Samstag - Sonntag",
            "Holiday": "Feiertag",
            "Daily": "Täglich"
        }

        for key, text in days_map.items():
            frame = ttk.Frame(self.notebook, padding="10")
            self.notebook.add(frame, text=text)
            self.populate_shift_rules(frame, key)

        colors_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(colors_frame, text="Farben")
        self.populate_color_settings(colors_frame)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Speichern", command=self.save).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def populate_shift_rules(self, parent_frame, day_key):
        self.vars[day_key] = {}
        header_frame = ttk.Frame(parent_frame)
        header_frame.pack(fill='x', pady=(0, 5))
        ttk.Label(header_frame, text="Schichtkürzel", font=("Segoe UI", 10, "bold")).pack(side='left', expand=True,
                                                                                          fill='x')
        ttk.Label(header_frame, text="Mindestanzahl", font=("Segoe UI", 10, "bold")).pack(side='left', expand=True,
                                                                                          fill='x')

        canvas = tk.Canvas(parent_frame)
        scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for shift in self.shifts:
            abbrev = shift['abbreviation']
            row_frame = ttk.Frame(scrollable_frame)
            row_frame.pack(fill='x', pady=2)

            ttk.Label(row_frame, text=f"{abbrev} ({shift['name']})").pack(side='left', expand=True, fill='x', padx=5)

            # Stelle sicher, dass der Schlüssel existiert, bevor darauf zugegriffen wird
            if day_key not in self.rules:
                self.rules[day_key] = {}

            var = tk.StringVar(value=self.rules.get(day_key, {}).get(abbrev, ""))
            self.vars[day_key][abbrev] = var
            ttk.Entry(row_frame, textvariable=var, width=10).pack(side='left', expand=True, fill='x', padx=5)

    def populate_color_settings(self, parent_frame):
        self.vars['Colors'] = {}

        color_map = {
            "alert_bg": "Unterbesetzung",
            "overstaffed_bg": "Überbesetzung",
            "success_bg": "Korrekte Besetzung",
            "weekend_bg": "Wochenende",
            "holiday_bg": "Feiertag"
        }

        # Stelle sicher, dass der "Colors"-Schlüssel existiert
        if "Colors" not in self.rules:
            self.rules["Colors"] = self.get_default_rules()["Colors"]

        for key, text in color_map.items():
            frame = ttk.Frame(parent_frame)
            frame.pack(fill='x', pady=5, padx=5)

            ttk.Label(frame, text=text, width=25).pack(side='left')

            color_val = self.rules.get("Colors", {}).get(key, "#FFFFFF")
            var = tk.StringVar(value=color_val)
            self.vars['Colors'][key] = var

            color_label = ttk.Label(frame, text="     ", background=color_val, relief="solid", borderwidth=1)
            color_label.pack(side='left', padx=10)

            ttk.Button(frame, text="Farbe wählen",
                       command=lambda v=var, l=color_label: self.choose_color(v, l)).pack(side='left')

    def choose_color(self, var, label):
        color_code = colorchooser.askcolor(title="Farbe wählen", initialcolor=var.get())
        if color_code and color_code[1]:
            var.set(color_code[1])
            label.config(background=color_code[1])

    def save(self):
        new_rules = {}
        for day_key, shift_vars in self.vars.items():
            if day_key == "Colors":
                new_rules["Colors"] = {k: v.get() for k, v in shift_vars.items()}
            else:
                new_rules[day_key] = {}
                for abbrev, var in shift_vars.items():
                    val = var.get()
                    if val.isdigit():
                        new_rules[day_key][abbrev] = int(val)
                    elif not val:
                        continue
                    else:
                        messagebox.showerror("Fehler",
                                             f"Ungültige Eingabe für {abbrev} am {day_key}. Bitte geben Sie eine Zahl ein.",
                                             parent=self)
                        return

        # Die neuen Regeln werden jetzt an die Callback-Funktion übergeben,
        # die sich um das Speichern und Aktualisieren kümmert.
        if self.callback:
            self.callback(new_rules)

        self.destroy()