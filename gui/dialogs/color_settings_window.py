# dialogs/color_settings_window.py
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import json


class ColorSettingsWindow(tk.Toplevel):
    def __init__(self, parent, callback=None):
        super().__init__(parent)
        self.transient(parent)
        self.title("Farbeinstellungen")
        self.grab_set()
        self.callback = callback

        self.rules = self.load_rules()
        self.color_vars = {}

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=5)

        general_tab = ttk.Frame(notebook, padding=10)
        notebook.add(general_tab, text="Allgemein")

        # General colors
        self.create_color_picker(general_tab, "Hintergrund Wochenende", "weekend_bg", "#EAF4FF", 0)
        self.create_color_picker(general_tab, "Hintergrund Feiertag", "holiday_bg", "#FFD700", 1)
        self.create_color_picker(general_tab, "Hintergrund Quartals Ausbildung", "quartals_ausbildung_bg", "#ADD8E6", 2)
        self.create_color_picker(general_tab, "Hintergrund Schießen", "schiessen_bg", "#FFB6C1", 3)
        self.create_color_picker(general_tab, "Unterbesetzung (Alarm)", "alert_bg", "#FF5555", 4)
        self.create_color_picker(general_tab, "Überbesetzung", "overstaffed_bg", "#FFFF99", 5)
        self.create_color_picker(general_tab, "Besetzung korrekt", "success_bg", "#90EE90", 6)

        request_tab = ttk.Frame(notebook, padding=10)
        notebook.add(request_tab, text="Anfragen-Status")

        self.create_color_picker(request_tab, "Ausstehend (Benutzer)", "Ausstehend", "orange", 0)
        self.create_color_picker(request_tab, "Ausstehend (Admin)", "Admin_Ausstehend", "#E0B0FF", 1)

        # Button Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_settings).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=5)

    def load_rules(self):
        try:
            with open('min_staffing_rules.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def create_color_picker(self, parent, label_text, key, default_color, row):
        color = self.rules.get('Colors', {}).get(key, default_color)
        self.color_vars[key] = tk.StringVar(value=color)

        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=5)

        color_frame = ttk.Frame(parent)
        color_frame.grid(row=row, column=1, sticky="ew", padx=5)
        parent.grid_columnconfigure(1, weight=1)

        color_entry = ttk.Entry(color_frame, textvariable=self.color_vars[key])
        color_entry.pack(side="left", fill="x", expand=True)

        color_btn = ttk.Button(color_frame, text="Farbe wählen",
                               command=lambda var=self.color_vars[key]: self.choose_color(var))
        color_btn.pack(side="left", padx=(5, 0))

    def choose_color(self, color_var):
        color_code = colorchooser.askcolor(title="Farbe auswählen", initialcolor=color_var.get())
        if color_code and color_code[1]:
            color_var.set(color_code[1])

    def save_settings(self):
        if 'Colors' not in self.rules:
            self.rules['Colors'] = {}
        for key, var in self.color_vars.items():
            self.rules['Colors'][key] = var.get()

        try:
            with open('min_staffing_rules.json', 'w', encoding='utf-8') as f:
                json.dump(self.rules, f, indent=4)
            messagebox.showinfo("Gespeichert", "Die Farbeinstellungen wurden erfolgreich gespeichert.", parent=self)

            if self.callback:
                self.callback()

            self.destroy()

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Einstellungen: {e}", parent=self)