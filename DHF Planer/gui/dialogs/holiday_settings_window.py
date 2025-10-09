# gui/dialogs/holiday_settings_window.py (KORRIGIERT: Liest/Schreibt Feiertage in DB)
import tkinter as tk
from tkinter import ttk, messagebox
import json

from database.db_manager import load_holiday_config, save_holiday_config  # Importiert DB-Funktionen


class HolidaySettingsWindow(tk.Toplevel):
    def __init__(self, master, current_year, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Feiertags-Einstellungen")
        self.geometry("400x200")
        self.transient(master)
        self.grab_set()

        self.current_year = current_year
        self.config = load_holiday_config()  # LÄDT AUS DB
        self.state_var = tk.StringVar(value=self.config.get('state', 'BB'))

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        # Bundesland Selection
        ttk.Label(main_frame, text="Bundesland (DE):").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        states = [
            "BB", "BE", "BW", "BY", "HB", "HE", "HH", "MV", "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH"
        ]  # ISO 3166-2 Codes

        ttk.Combobox(main_frame, textvariable=self.state_var, values=states, state="readonly").grid(row=0, column=1,
                                                                                                    sticky="ew",
                                                                                                    pady=5)

        ttk.Label(main_frame, text=f"Feiertage werden für {current_year} neu geladen.").grid(row=1, column=0,
                                                                                             columnspan=2, sticky="w",
                                                                                             pady=10)

        # Action Buttons
        button_bar = ttk.Frame(main_frame)
        button_bar.grid(row=2, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Speichern", command=self.save_settings).grid(row=0, column=0, sticky="ew",
                                                                                  padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def save_settings(self):
        new_state = self.state_var.get()

        if new_state == self.config.get('state'):
            messagebox.showinfo("Info", "Keine Änderungen vorgenommen.", parent=self)
            self.destroy()
            return

        self.config['state'] = new_state

        success = save_holiday_config(self.config)  # SCHREIBT IN DB

        if success:
            messagebox.showinfo("Erfolg", "Feiertags-Einstellungen gespeichert. Der Plan wird neu geladen.",
                                parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern in der Datenbank fehlgeschlagen.", parent=self)