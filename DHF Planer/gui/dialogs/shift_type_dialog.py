# gui/dialogs/shift_type_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from datetime import datetime

class ShiftTypeDialog(tk.Toplevel):
    def __init__(self, admin_instance, callback_func, is_new, initial_data=None):
        super().__init__(admin_instance.master)
        self.admin_instance = admin_instance
        self.callback_func = callback_func
        self.is_new = is_new
        self.initial_data = initial_data if initial_data is not None else {}
        self.result = None
        self.title("Neue Schichtart anlegen" if is_new else "Schichtart bearbeiten")
        self.geometry("400x420")
        self.transient(admin_instance)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.body(self)
        self.buttonbox(self)
        self.update_idletasks()
        if self.winfo_children(): self.winfo_children()[0].focus_set()

    def body(self, master):
        main_frame = ttk.Frame(master, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        self.vars = {
            "name": tk.StringVar(value=self.initial_data.get("name", "")),
            "abbreviation": tk.StringVar(value=self.initial_data.get("abbreviation", "")),
            "hours": tk.StringVar(value=str(self.initial_data.get("hours", 0))),
            "start_time": tk.StringVar(value=self.initial_data.get("start_time", "")),
            "end_time": tk.StringVar(value=self.initial_data.get("end_time", "")),
            "description": tk.StringVar(value=self.initial_data.get("description", "")),
            "color": tk.StringVar(value=self.initial_data.get("color", "#FFFFFF")),
        }

        labels = [
            "Art (Name):", "Abkürzung (max. 3 Zeichen):", "Stunden (pro Schicht):",
            "Startzeit (HH:MM):", "Endzeit (HH:MM):", "Beschreibung:", "Farbe wählen:"
        ]
        keys = [
            "name", "abbreviation", "hours", "start_time", "end_time", "description", "color"
        ]
        root = self.admin_instance.master

        for i, (label_text, key) in enumerate(zip(labels, keys)):
            ttk.Label(main_frame, text=label_text).grid(row=i, column=0, sticky="w", pady=5, padx=5)

            if key == "color":
                color_frame = ttk.Frame(main_frame)
                color_frame.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                self.color_preview = tk.Label(
                    color_frame, textvariable=self.vars["color"], bg=self.vars[key].get(),
                    relief="sunken", borderwidth=1, cursor="hand2",
                    font=("Segoe UI", 10, "bold"), width=20
                )
                self.color_preview.config(fg=self.admin_instance.get_contrast_color(self.vars['color'].get()))
                self.color_preview.pack(side=tk.LEFT, fill="both", expand=True)
                self.color_preview.bind("<Button-1>", lambda e: self.choose_color())
                self.vars[key].trace_add('write', lambda *args: self.update_color_preview())
            else:
                entry = tk.Entry(main_frame, textvariable=self.vars[key], width=40)
                entry.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)

                if key == "abbreviation":
                    vcmd_abbrev = (root.register(self.validate_abbreviation), '%P')
                    entry.config(validate='key', vcmd=vcmd_abbrev)
                    if not self.is_new:
                        entry.config(state='readonly', disabledbackground="lightgrey")
                elif key == "hours":
                    vcmd_hours = (root.register(self.validate_hours), '%P')
                    entry.config(validate='key', vcmd=vcmd_hours)
                elif key in ["start_time", "end_time"]:
                    vcmd_time = (root.register(self.validate_time), '%P')
                    entry.config(validate='key', vcmd=vcmd_time)

        self.update_color_preview()

    def choose_color(self):
        initial_color = self.vars['color'].get()
        color_code = colorchooser.askcolor(parent=self, title="Wähle eine Farbe", initialcolor=initial_color)
        if color_code and color_code[1]:
            hex_code = color_code[1].upper()
            self.vars['color'].set(hex_code)
            self.color_preview.config(bg=hex_code, fg=self.admin_instance.get_contrast_color(hex_code))

    def update_color_preview(self):
        color_val = self.vars['color'].get()
        text_color = self.admin_instance.get_contrast_color(color_val)
        try:
            self.color_preview.config(bg=color_val, fg=text_color)
        except tk.TclError:
            self.color_preview.config(bg="#FFFFFF", fg='black')

    def buttonbox(self, master):
        box = ttk.Frame(master, padding="10")
        ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="Abbrechen", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack(pady=(0, 10))

    def validate_abbreviation(self, P):
        if P == "": return True
        if len(P) > 3: return False
        for char in P:
            if not (char.isalnum() or char == '.'): return False
        return True

    def validate_hours(self, P):
        return P.isdigit() or P == ""

    def validate_time(self, P):
        if len(P) > 5:
            return False
        if P == "":
            return True
        if P.count(':') > 1:
            return False
        if not all(c.isdigit() or c == ':' for c in P):
            return False
        if ':' in P:
            parts = P.split(':')
            if len(parts[0]) > 2 or len(parts[1]) > 2:
                return False
        elif len(P) > 2:
            return False
        return True

    def ok(self, event=None):
        data = {key: var.get().strip() for key, var in self.vars.items()}
        data['abbreviation'] = data['abbreviation'].upper()
        data['color'] = data['color'].upper()

        required_fields = ["name", "abbreviation", "hours", "color"]
        if not all(data[f] for f in required_fields):
            messagebox.showwarning("Eingabe fehlt",
                                   "Felder (Name, Abkürzung, Stunden, Farbe) sind Pflichtfelder.", parent=self)
            return

        for time_key in ["start_time", "end_time"]:
            time_val = data.get(time_key)
            if time_val:
                try:
                    datetime.strptime(time_val, '%H:%M')
                except ValueError:
                    messagebox.showwarning("Falsches Format",
                                           f"Die Eingabe für '{time_key}' ist ungültig. Bitte HH:MM verwenden.",
                                           parent=self)
                    return

        color = data['color']
        if not (color.startswith('#') and len(color) == 7 and all(c in '0123456789ABCDEF' for c in color[1:])):
            messagebox.showwarning("Eingabe Fehler", "Interner Fehler: Ungültiger Hex-Code.", parent=self)
            return

        if not self.validate_abbreviation(data['abbreviation']):
            messagebox.showwarning("Eingabe Fehler",
                                   "Die Abkürzung ist ungültig. Max. 3 Zeichen (Buchstaben, Zahlen, Punkt).",
                                   parent=self)
            return
        try:
            data['hours'] = int(data['hours'])
        except ValueError:
            messagebox.showerror("Fehler", "Stunden müssen eine ganze Zahl sein.", parent=self)
            return

        self.result = data
        self.callback_func(self.result, self.initial_data.get('id') if not self.is_new else None)
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.destroy()