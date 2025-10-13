# gui/dialogs/color_settings_window.py
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
# NEUE IMPORTS FÜR DB-ZENTRALISIERUNG
from database.db_core import load_config_json, save_config_json


class ColorSettingsWindow(tk.Toplevel):
    def __init__(self, parent, callback=None):
        super().__init__(parent)
        self.transient(parent)
        self.title("Farbeinstellungen")
        self.grab_set()
        self.callback = callback

        # 💥 DB PERSISTENCE: Läd Regeln aus der DB 💥
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
        """Läd die Besetzungsregeln (inklusive Farb-Key) aus der Datenbank."""
        # Nutzt die zentrale DB-Funktion
        rules = load_config_json('MIN_STAFFING_RULES')
        # Stellt sicher, dass ein gültiges Dictionary zurückgegeben wird
        return rules if rules is not None else {"Daily": {}, "Sa-So": {}, "Fr": {}, "Mo-Do": {}, "Holiday": {},
                                                "Colors": {}}

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
        """Speichert die aktualisierten Farbregeln direkt in der Datenbank."""
        if 'Colors' not in self.rules:
            self.rules['Colors'] = {}
        for key, var in self.color_vars.items():
            self.rules['Colors'][key] = var.get()

        # 💥 DB PERSISTENCE: Speichere die gesamte Rules-Struktur zurück in die DB 💥
        success = save_config_json('MIN_STAFFING_RULES', self.rules)

        if success:
            messagebox.showinfo("Gespeichert", "Die Farbeinstellungen wurden erfolgreich gespeichert.", parent=self)

            if self.callback:
                # Callback ruft refresh_all_tabs() im MainAdminWindow auf
                self.callback()

            self.destroy()

        else:
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Einstellungen.", parent=self)