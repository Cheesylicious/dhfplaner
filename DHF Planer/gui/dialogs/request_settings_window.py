# gui/dialogs/request_settings_window.py (KORRIGIERT: Liest/Schreibt Anfragen-Einstellungen in DB)
import tkinter as tk
from tkinter import ttk, messagebox
import json

from database.db_manager import load_request_settings, save_request_setting  # Importiert DB-Funktionen


class RequestSettingsWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Wunschanfragen-Einstellungen")
        self.geometry("450x250")
        self.transient(master)
        self.grab_set()

        self.settings = load_request_settings()  # LÄDT AUS DB
        self.vars = {}

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        # Felder definieren
        fields = [
            ("max_requests_per_month", "Max. 'Wunschfrei'-Anfragen pro Monat:"),
            ("max_total_requests", "Max. Wunschanfragen gesamt (WF & Schicht) pro Monat:")
        ]

        row_index = 0
        for key, display_name in fields:
            ttk.Label(main_frame, text=display_name).grid(row=row_index, column=0, sticky="w", pady=5, padx=(0, 10))
            self.vars[key] = tk.StringVar(value=self.settings.get(key, ''))
            ttk.Entry(main_frame, textvariable=self.vars[key]).grid(row=row_index, column=1, sticky="ew", pady=5)
            row_index += 1

        ttk.Label(main_frame, text="Hinweis: Die Änderung betrifft nur zukünftige Anfragen.").grid(row=row_index,
                                                                                                   column=0,
                                                                                                   columnspan=2,
                                                                                                   sticky="w",
                                                                                                   pady=(10, 0))

        # Action Buttons
        button_bar = ttk.Frame(main_frame)
        button_bar.grid(row=row_index + 1, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Speichern", command=self.save_settings).grid(row=0, column=0, sticky="ew",
                                                                                  padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def save_settings(self):
        new_settings = {}
        has_changed = False

        # Validierung und Speicherung
        for key, var in self.vars.items():
            value = var.get().strip()

            if not value.isdigit() or int(value) < 0:
                messagebox.showerror("Fehler", f"'{key}' muss eine positive ganze Zahl sein.", parent=self)
                return

            if value != self.settings.get(key):
                has_changed = True
                save_request_setting(key, value)  # SCHREIBT EINZELN IN DB

        if has_changed:
            messagebox.showinfo("Erfolg", "Anfragen-Einstellungen gespeichert.", parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showinfo("Info", "Keine Änderungen vorgenommen.", parent=self)
            self.destroy()