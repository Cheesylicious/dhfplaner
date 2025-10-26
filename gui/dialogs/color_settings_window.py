# gui/dialogs/color_settings_window.py
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import json
import os
# Importiere die DB-Funktionen
from database.db_core import load_config_json, save_config_json, MIN_STAFFING_RULES_CONFIG_KEY


class ColorSettingsWindow(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title("Farbeinstellungen")
        self.geometry("400x500")
        self.transient(parent)
        self.grab_set()

        self.callback = callback

        # --- ANPASSUNG: Wir verwenden jetzt den DB-Config-Key ---
        # Die Farben werden zusammen mit den Staffing-Regeln gespeichert.
        self.config_key = MIN_STAFFING_RULES_CONFIG_KEY

        self.colors = self.load_colors_from_db()
        self.vars = {}

        self.create_widgets()

    def load_colors_from_db(self):
        """Lädt die Konfiguration aus der Datenbank."""
        config = load_config_json(self.config_key)

        if config and "Colors" in config:
            # Lade Farben aus der DB
            loaded_colors = config.get("Colors", {})
            # Stelle sicher, dass alle Standardfarben vorhanden sind, falls neue hinzugefügt wurden
            defaults = self.get_default_colors()
            defaults.update(loaded_colors)  # Überschreibe Defaults mit geladenen Werten
            return defaults
        else:
            # Wenn keine Config oder kein "Colors"-Schlüssel gefunden wurde, nutze Defaults
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

            color_label = ttk.Label(frame, text="       ", background=color_val, relief="solid", borderwidth=1)
            color_label.pack(side='left', padx=10)

            ttk.Button(frame, text="Farbe wählen",
                       command=lambda v=var, l=color_label: self.choose_color(v, l)).pack(side='left')

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Speichern", command=self.save_to_db).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def choose_color(self, var, label):
        # Öffnet den Farbwähler-Dialog
        color_code = colorchooser.askcolor(title="Farbe wählen", initialcolor=var.get())
        if color_code and color_code[1]:
            # Setzt den neuen Farbwert in der Variable und aktualisiert die Vorschau
            var.set(color_code[1])
            label.config(background=color_code[1])

    def save_to_db(self):
        """Speichert die Farben in der Datenbank."""
        # Sammelt die neuen Farbwerte aus den Variablen
        new_colors = {key: var.get() for key, var in self.vars.items()}

        try:
            # Lädt die gesamte Konfigurationsdatei (z.B. Staffing Rules)
            config = load_config_json(self.config_key)
            if config is None:
                config = {}

            # Aktualisiert nur den "Colors"-Teil
            config["Colors"] = new_colors

            # Speichert die gesamte Konfiguration zurück
            if save_config_json(self.config_key, config):
                messagebox.showinfo("Gespeichert", "Farbeinstellungen erfolgreich in der Datenbank gespeichert.",
                                    parent=self)
                # Ruft die Callback-Funktion auf, um das Hauptfenster zu aktualisieren
                if self.callback:
                    self.callback()
                self.destroy()
            else:
                messagebox.showerror("Fehler", "Die Farben konnten nicht in der Datenbank gespeichert werden.",
                                     parent=self)

        except Exception as e:
            messagebox.showerror("Fehler beim Speichern", f"Die Farben konnten nicht gespeichert werden:\n{e}",
                                 parent=self)