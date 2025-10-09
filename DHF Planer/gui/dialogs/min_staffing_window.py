# gui/dialogs/min_staffing_window.py
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import json
import os

STAFFING_RULES_FILE = 'min_staffing_rules.json'

DEFAULT_RULES = {
    "Colors": {"alert_bg": "#FF5555", "success_bg": "#90EE90", "overstaffed_bg": "#FFFF99"},
    "Mo-Do": {"T.": 1}, "Fr": {"T.": 1, "6": 1}, "Sa-So": {"T.": 2},
    "Holiday": {"T.": 2}, "Daily": {"N.": 2, "24": 2}
}


def load_staffing_rules():
    if os.path.exists(STAFFING_RULES_FILE):
        try:
            with open(STAFFING_RULES_FILE, 'r') as f:
                rules = json.load(f)
                if 'Colors' not in rules:
                    rules['Colors'] = DEFAULT_RULES['Colors']
                return rules
        except json.JSONDecodeError:
            return DEFAULT_RULES
    return DEFAULT_RULES


def save_staffing_rules(rules):
    try:
        with open(STAFFING_RULES_FILE, 'w') as f:
            json.dump(rules, f, indent=4)
        return True
    except Exception:
        return False


class MinStaffingWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.master = master # Referenz auf MainAdminWindow
        self.callback = callback
        self.rules = load_staffing_rules()
        self.title("Mindestbesetzungsregeln definieren (inkl. Farben)")
        self.geometry("600x600")
        self.transient(master)
        self.grab_set()
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True)
        regeln_frame = ttk.Frame(notebook, padding="10")
        notebook.add(regeln_frame, text="Besetzungsanforderungen")
        regeln_frame.columnconfigure(2, weight=1)
        self.vars = {}
        self.entry_widgets = {}
        row = 0
        ttk.Label(regeln_frame,
                  text="Definieren Sie die erforderliche Mindestanzahl an Mitarbeitern pro Schicht und Regelbereich.",
                  wraplength=550, font=("Segoe UI", 10, "italic")).grid(row=row, columnspan=3, sticky="w", pady=(0, 10))
        row += 1
        abbrevs_set = set()
        for rule_data in DEFAULT_RULES.values():
            if isinstance(rule_data, dict) and 'Colors' not in rule_data:
                abbrevs_set.update(rule_data.keys())
        abbrevs = sorted(list(abbrevs_set | set(DEFAULT_RULES['Daily'].keys())))
        ttk.Label(regeln_frame, text="Regelbereich", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w",
                                                                                         padx=5)
        ttk.Label(regeln_frame, text="Schichtkürzel", font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky="w",
                                                                                          padx=5)
        ttk.Label(regeln_frame, text="Min. Besetzung", font=("Segoe UI", 10, "bold")).grid(row=row, column=2,
                                                                                           sticky="w", padx=5)
        row += 1
        vcmd = (self.register(lambda P: P.isdigit() or P == ""), '%P')
        for rule_key, rule_data in self.rules.items():
            if rule_key == "Colors": continue
            ttk.Separator(regeln_frame).grid(row=row, columnspan=3, sticky="ew", pady=5)
            row += 1
            ttk.Label(regeln_frame, text=rule_key, font=("Segoe UI", 10, "italic")).grid(row=row, column=0, sticky="nw",
                                                                                         padx=5)
            for abbrev in abbrevs:
                if abbrev in rule_data or (rule_key == "Daily" and abbrev in DEFAULT_RULES["Daily"]):
                    current_val = rule_data.get(abbrev, 0)
                    var_key = f"{rule_key}_{abbrev}"
                    self.vars[var_key] = tk.StringVar(value=str(current_val))
                    ttk.Label(regeln_frame, text=abbrev).grid(row=row, column=1, sticky="w", padx=5)
                    entry = tk.Entry(regeln_frame, textvariable=self.vars[var_key], width=5, validate='key', vcmd=vcmd,
                                     font=("Segoe UI", 10))
                    entry.grid(row=row, column=2, sticky="w", padx=5)
                    self.entry_widgets[var_key] = entry
                    row += 1
            if rule_key != "Daily": row += 1
        farben_frame = ttk.Frame(notebook, padding="10")
        notebook.add(farben_frame, text="Farbeinstellungen")
        farben_frame.columnconfigure(1, weight=1)
        self.color_vars = {}
        self.color_widgets = {}
        color_row = 0
        color_map = {"alert_bg": "Hintergrund bei Unterschreitung (ROT)",
                     "success_bg": "Hintergrund bei Erfüllung (GRÜN)",
                     "overstaffed_bg": "Hintergrund bei Überbesetzung (GELB)"}
        for key, label_text in color_map.items():
            current_hex = self.rules['Colors'].get(key, DEFAULT_RULES['Colors'][key])
            self.color_vars[key] = tk.StringVar(value=current_hex)
            ttk.Label(farben_frame, text=label_text, font=("Segoe UI", 10)).grid(row=color_row, column=0, sticky="w",
                                                                                 pady=5, padx=5)
            color_preview = tk.Label(farben_frame, textvariable=self.color_vars[key], bg=current_hex, relief="sunken",
                                     borderwidth=1, cursor="hand2", width=20)
            color_preview.grid(row=color_row, column=1, sticky="ew", pady=5, padx=5)
            button = ttk.Button(farben_frame, text="Wählen",
                                command=lambda k=key, p=color_preview: self.choose_color(k, p))
            button.grid(row=color_row, column=2, sticky="w", pady=5, padx=5)
            self.color_widgets[key] = color_preview
            self.update_color_preview_text(key, color_preview, current_hex)
            color_row += 1
        button_bar = ttk.Frame(self)
        button_bar.pack(fill="x", pady=10)
        ttk.Button(button_bar, text="Speichern", command=self.save).pack(side="left", padx=15)
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).pack(side="left", padx=5)

    def update_color_preview_text(self, key, preview_widget, hex_code):
        try:
            # Greift auf die Methode im Hauptfenster zurück
            text_color = self.master.get_contrast_color(hex_code)
            preview_widget.config(bg=hex_code, fg=text_color)
        except AttributeError:
            preview_widget.config(bg=hex_code, fg='black')

    def choose_color(self, key, preview_widget):
        initial_color = self.color_vars[key].get()
        color_code = colorchooser.askcolor(parent=self, title=f"Wähle Farbe für {key}", initialcolor=initial_color)
        if color_code and color_code[1]:
            hex_code = color_code[1].upper()
            self.color_vars[key].set(hex_code)
            self.update_color_preview_text(key, preview_widget, hex_code)

    def save(self):
        new_rules = load_staffing_rules()
        success = True
        temp_rules_data = {k: {} for k in DEFAULT_RULES.keys() if k != 'Colors'}
        for var_key, var in self.vars.items():
            value_str = var.get().strip()
            if not value_str: continue
            try:
                value = int(value_str)
                if value < 0: raise ValueError("Negativer Wert")
            except ValueError:
                messagebox.showerror("Fehler",
                                     f"Ungültiger Wert '{value_str}' für ein Feld (nur positive ganze Zahlen erlaubt).",
                                     parent=self)
                self.entry_widgets[var_key].focus_set()
                success = False;
                break
            if value > 0:
                rule_key, abbrev = var_key.split('_', 1)
                temp_rules_data[rule_key][abbrev] = value
        if not success: return
        new_rules['Colors'] = {key: var.get().upper() for key, var in self.color_vars.items()}
        for key in temp_rules_data.keys():
            new_rules[key] = temp_rules_data[key]
        if save_staffing_rules(new_rules):
            messagebox.showinfo("Erfolg", "Mindestbesetzungsregeln gespeichert. Der Schichtplan wird aktualisiert.",
                                parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Fehler beim Speichern der Regeldatei.", parent=self)