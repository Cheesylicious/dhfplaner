# gui/dialogs/color_settings_window.py
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import json

class ColorSettingsWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.master = master
        self.callback = callback
        self.title("Farbeinstellungen")
        self.geometry("400x200")
        self.transient(master)
        self.grab_set()

        self.weekend_color = tk.StringVar()
        self.holiday_color = tk.StringVar()

        self.load_colors()
        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Wochenend-Farbe:").grid(row=0, column=0, sticky="w", pady=5)
        self.weekend_entry = ttk.Entry(main_frame, textvariable=self.weekend_color)
        self.weekend_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(main_frame, text="Farbe wählen", command=lambda: self.choose_color(self.weekend_color)).grid(row=0, column=2)

        ttk.Label(main_frame, text="Feiertags-Farbe:").grid(row=1, column=0, sticky="w", pady=5)
        self.holiday_entry = ttk.Entry(main_frame, textvariable=self.holiday_color)
        self.holiday_entry.grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(main_frame, text="Farbe wählen", command=lambda: self.choose_color(self.holiday_color)).grid(row=1, column=2)

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=10)
        ttk.Button(button_frame, text="Speichern", command=self.save_colors).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="left", padx=5)

    def choose_color(self, color_var):
        color_code = colorchooser.askcolor(title="Farbe auswählen")
        if color_code:
            color_var.set(color_code[1])

    def load_colors(self):
        try:
            with open('min_staffing_rules.json', 'r', encoding='utf-8') as f:
                rules = json.load(f)
                colors = rules.get("Colors", {})
                self.weekend_color.set(colors.get("weekend_bg", "#EAF4FF"))
                self.holiday_color.set(colors.get("holiday_bg", "#FFD700"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.weekend_color.set("#EAF4FF")
            self.holiday_color.set("#FFD700")

    def save_colors(self):
        try:
            with open('min_staffing_rules.json', 'r', encoding='utf-8') as f:
                rules = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            rules = {"Colors": {}}

        if "Colors" not in rules:
            rules["Colors"] = {}

        rules["Colors"]["weekend_bg"] = self.weekend_color.get()
        rules["Colors"]["holiday_bg"] = self.holiday_color.get()

        try:
            with open('min_staffing_rules.json', 'w', encoding='utf-8') as f:
                json.dump(rules, f, indent=4)
            messagebox.showinfo("Gespeichert", "Die Farbeinstellungen wurden erfolgreich gespeichert.", parent=self)
            self.callback()
            self.destroy()
        except IOError:
            messagebox.showerror("Fehler", "Die Farbeinstellungen konnten nicht gespeichert werden.", parent=self)