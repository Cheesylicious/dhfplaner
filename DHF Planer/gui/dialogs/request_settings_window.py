# gui/dialogs/request_settings_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from gui.request_config_manager import RequestConfigManager

class RequestSettingsWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Verfügbare Benutzer-Anfragen verwalten")
        self.geometry("450x350")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame,
                  text="Wählen Sie aus, welche Anfragetypen für Benutzer verfügbar sein sollen.",
                  wraplength=400, font=("Segoe UI", 10, "italic")).pack(pady=(0, 20), anchor="w")

        self.config = RequestConfigManager.load_config()
        self.vars = {}

        display_names = {
            "WF": "Wunschfrei beantragen",
            "T.": "Tagdienst-Wunsch (T.)",
            "N.": "Nachtdienst-Wunsch (N.)",
            "6": "6-Stunden-Dienst-Wunsch (6)",
            "24": "24-Stunden-Dienst-Wunsch (24)"
        }

        for key, display_text in display_names.items():
            self.vars[key] = tk.BooleanVar(value=self.config.get(key, True))
            cb = ttk.Checkbutton(main_frame, text=display_text, variable=self.vars[key])
            cb.pack(anchor="w", pady=4)

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(30, 0), side="bottom")
        button_bar.columnconfigure((0, 1), weight=1)

        ttk.Button(button_bar, text="Speichern", command=self.save).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def save(self):
        new_config = {key: var.get() for key, var in self.vars.items()}
        success, message = RequestConfigManager.save_config(new_config)
        if success:
            messagebox.showinfo("Erfolg", "Einstellungen wurden gespeichert.", parent=self)
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)