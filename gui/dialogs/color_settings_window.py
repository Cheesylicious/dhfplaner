# gui/dialogs/color_settings_window.py
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import json
import os

class ColorSettingsWindow(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title("Farbeinstellungen")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()

        self.callback = callback
        self.config_file = "staffing_rules.json"
        self.colors = self.load_colors()
        self.vars = {}

        self.create_widgets()

    def load_colors(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                try:
                    config = json.load(f)
                    # Lade die Farben oder nutze Standardwerte, falls der Schlüssel fehlt
                    return config.get("Colors", self.get_default_colors())
                except json.JSONDecodeError:
                    return self.get_default_colors()
        return self.get_default_colors()

    def get_default_colors(self):
        # Standardfarben, falls die Konfigurationsdatei nicht existiert oder fehlerhaft ist
        return {
            "Ausstehend": "orange",
            "Admin_Ausstehend": "#E0B0FF",
            "alert_bg": "#FF5555",
            "overstaffed_bg": "#FFFF99",
            "success_bg": "#90EE90",
            "weekend_bg": "#EAF4FF",
            "holiday_bg": "#FFD700",
            "quartals_ausbildung_bg": "#ADD8E6",
            "schiessen_bg": "#FFB6C1"
        }

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        # Mapping der internen Schlüssel zu den angezeigten Namen
        color_map = {
            "Ausstehend": "Anfrage Ausstehend",
            "Admin_Ausstehend": "Admin Anfrage Ausstehend",
            "alert_bg": "Unterbesetzung",
            "overstaffed_bg": "Überbesetzung",
            "success_bg": "Korrekte Besetzung",
            "weekend_bg": "Wochenende",
            "holiday_bg": "Feiertag",
            "quartals_ausbildung_bg": "Quartals Ausbildung",
            "schiessen_bg": "Schießen"
        }

        for key, text in color_map.items():
            frame = ttk.Frame(main_frame)
            frame.pack(fill='x', pady=5, padx=5)

            ttk.Label(frame, text=text, width=25).pack(side='left')

            color_val = self.colors.get(key, "#FFFFFF")
            var = tk.StringVar(value=color_val)
            self.vars[key] = var

            # --- ANFANG DER ÄNDERUNG ---
            # Das Label für die Farbvorschau wird etwas breiter gemacht
            color_label = ttk.Label(frame, text="       ", background=color_val, relief="solid", borderwidth=1)
            color_label.pack(side='left', padx=10)

            # Das Eingabefeld für den Hex-Code wurde entfernt
            # --- ENDE DER ÄNDERUNG ---

            ttk.Button(frame, text="Farbe wählen",
                       command=lambda v=var, l=color_label: self.choose_color(v, l)).pack(side='left')

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Speichern", command=self.save).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def choose_color(self, var, label):
        # Öffnet den Farbwähler-Dialog
        color_code = colorchooser.askcolor(title="Farbe wählen", initialcolor=var.get())
        if color_code and color_code[1]:
            # Setzt den neuen Farbwert in der Variable und aktualisiert die Vorschau
            var.set(color_code[1])
            label.config(background=color_code[1])

    def save(self):
        # Sammelt die neuen Farbwerte aus den Variablen
        new_colors = {key: var.get() for key, var in self.vars.items()}

        try:
            # Lädt die gesamte Konfigurationsdatei, um nur den "Colors"-Teil zu aktualisieren
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            else:
                config = {}

            config["Colors"] = new_colors

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)

            # Ruft die Callback-Funktion auf, um das Hauptfenster zu aktualisieren
            if self.callback:
                self.callback()

            self.destroy()
        except Exception as e:
            messagebox.showerror("Fehler beim Speichern", f"Die Farben konnten nicht gespeichert werden:\n{e}", parent=self)