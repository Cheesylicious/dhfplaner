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
        self.geometry("400x450")
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
            "font_color": tk.StringVar(value=self.initial_data.get("font_color", "#000000")),
        }

        labels = [
            "Art (Name):", "Abkürzung (max. 3 Zeichen):", "Stunden (pro Schicht):",
            "Startzeit (HH:MM):", "Endzeit (HH:MM):", "Beschreibung:", "Hintergrundfarbe:", "Schriftfarbe:"
        ]
        keys = [
            "name", "abbreviation", "hours", "start_time", "end_time", "description", "color", "font_color"
        ]
        root = self.admin_instance.master

        for i, (label_text, key) in enumerate(zip(labels, keys)):
            ttk.Label(main_frame, text=label_text).grid(row=i, column=0, sticky="w", pady=5, padx=5)
            if key == "color":
                color_frame = ttk.Frame(main_frame)
                color_frame.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                self.color_preview = tk.Label(color_frame, text=" Beispiel ", bg=self.vars[key].get(),
                                              relief="sunken", borderwidth=1, cursor="hand2",
                                              font=("Segoe UI", 10, "bold"), width=20)
                self.color_preview.pack(side=tk.LEFT, fill="both", expand=True)
                self.color_preview.bind("<Button-1>", lambda e, k=key, p=self.color_preview: self.choose_color(k, p))
                self.vars[key].trace_add('write',
                                         lambda *args, k=key, p=self.color_preview: self.update_color_preview(k, p))
            elif key == "font_color":
                font_color_frame = ttk.Frame(main_frame)
                font_color_frame.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                self.font_color_preview = tk.Label(font_color_frame, text=" Beispiel ", bg="white",
                                                   fg=self.vars[key].get(),
                                                   relief="sunken", borderwidth=1, cursor="hand2",
                                                   font=("Segoe UI", 10, "bold"), width=20)
                self.font_color_preview.pack(side=tk.LEFT, fill="both", expand=True)
                self.font_color_preview.bind("<Button-1>",
                                             lambda e, k=key, p=self.font_color_preview: self.choose_color(k, p))
                self.vars[key].trace_add('write',
                                         lambda *args, k=key, p=self.font_color_preview: self.update_color_preview(k,
                                                                                                                   p))
            else:
                entry = tk.Entry(main_frame, textvariable=self.vars[key], width=40)
                entry.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                if key == "abbreviation":
                    vcmd_abbrev = (root.register(self.validate_abbreviation), '%P')
                    entry.config(validate='key', vcmd=vcmd_abbrev)
                    if not self.is_new: entry.config(state='readonly')
                elif key == "hours":
                    vcmd_hours = (root.register(self.validate_hours), '%P')
                    entry.config(validate='key', vcmd=vcmd_hours)
                elif key in ["start_time", "end_time"]:
                    vcmd_time = (root.register(self.validate_time), '%P')
                    entry.config(validate='key', vcmd=vcmd_time)
        self.update_color_preview('color', self.color_preview)

    def choose_color(self, var_key, preview_widget):
        initial_color = self.vars[var_key].get()
        color_code = colorchooser.askcolor(parent=self, title="Wähle eine Farbe", initialcolor=initial_color)
        if color_code and color_code[1]:
            self.vars[var_key].set(color_code[1].upper())

    def update_color_preview(self, var_key, preview_widget):
        color_val = self.vars[var_key].get()
        try:
            if var_key == 'color':
                text_color = self.admin_instance.get_contrast_color(color_val)
                preview_widget.config(bg=color_val, fg=text_color)
            else:  # font_color
                preview_widget.config(fg=color_val)
        except tk.TclError:
            if var_key == 'color':
                preview_widget.config(bg="#FFFFFF", fg='black')
            else:
                preview_widget.config(fg='#000000')

    def buttonbox(self, master):
        box = ttk.Frame(master, padding="10")
        ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="Abbrechen", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack(pady=(0, 10))

    def validate_abbreviation(self, P):
        return len(P) <= 3 and all(c.isalnum() or c == '.' for c in P)

    def validate_hours(self, P):
        return P.isdigit() or P == ""

    def validate_time(self, P):
        if P == "": return True
        if len(P) > 5 or P.count(':') > 1 or not all(c.isdigit() or c == ':' for c in P): return False
        if ':' in P:
            parts = P.split(':')
            if len(parts) != 2 or len(parts[0]) > 2 or len(parts[1]) > 2: return False
        elif len(P) > 2:
            return False
        return True

    def ok(self, event=None):
        data = {key: var.get().strip() for key, var in self.vars.items()}
        data['abbreviation'] = data['abbreviation'].upper()
        data['color'] = data['color'].upper()
        data['font_color'] = data['font_color'].upper()

        required_fields = ["name", "abbreviation", "hours"]
        if not all(data.get(f) for f in required_fields):
            messagebox.showwarning("Eingabe fehlt", "Name, Abkürzung und Stunden sind Pflichtfelder.", parent=self)
            return

        for time_key in ["start_time", "end_time"]:
            if data[time_key]:
                try:
                    datetime.strptime(data[time_key], '%H:%M')
                except ValueError:
                    messagebox.showwarning("Falsches Format", f"'{time_key}' muss im HH:MM Format sein.", parent=self)
                    return

        for color_key in ['color', 'font_color']:
            color = data[color_key]
            if not (color.startswith('#') and len(color) == 7 and all(
                    c in '0123456789ABCDEF' for c in color[1:].upper())):
                messagebox.showwarning("Eingabe Fehler", f"Ungültiger Hex-Code für {color_key}.", parent=self)
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