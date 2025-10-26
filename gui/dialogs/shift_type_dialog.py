# gui/dialogs/shift_type_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from datetime import datetime


class ShiftTypeDialog(tk.Toplevel):
    def __init__(self, parent, app, is_new, initial_data=None):
        super().__init__(parent)
        self.app = app
        self.is_new = is_new
        self.initial_data = initial_data if initial_data is not None else {}
        self.result = None
        self.title("Neue Schichtart anlegen" if is_new else "Schichtart bearbeiten")
        self.geometry("400x450") # Feste Größe beibehalten
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        # --- KORREKTUR: Reihenfolge der Methodenaufrufe geändert ---
        # Zuerst die Buttons am unteren Rand platzieren
        self.buttonbox(self)
        # Dann den Rest des Inhalts darüber platzieren
        self.body(self)
        # --- ENDE KORREKTUR ---

        self.update_idletasks()
        # Fokus auf das erste Eingabeelement im body setzen (falls vorhanden)
        # Da body jetzt nach buttonbox aufgerufen wird, müssen wir den body Frame finden
        body_frame = self._find_body_frame()
        if body_frame and body_frame.winfo_children():
            first_widget = self._find_first_entry(body_frame)
            if first_widget:
                first_widget.focus_set()

    # --- NEU: Hilfsfunktion, um den body Frame zu finden ---
    def _find_body_frame(self):
        for child in self.winfo_children():
            # Annahme: Der Body-Frame hat den Namen 'main_frame' intern oder ist der erste Frame nach dem Button-Frame
            # Sicherer ist es, ihn direkt zu speichern, aber das würde mehr Umbauten erfordern.
            # Wir suchen nach dem Frame, der NICHT der Button-Frame ist.
            if isinstance(child, ttk.Frame) and hasattr(child, '_is_body_frame'): # Markieren wir den Frame in body()
                return child
        # Fallback: Nimm den ersten Frame, der nicht der Button-Frame ist (weniger robust)
        for child in self.winfo_children():
             if isinstance(child, ttk.Frame) and child.winfo_manager() == 'pack' and child.winfo_ismapped():
                  # Prüfen, ob es der Button-Frame ist (der hat spezifische Pack-Optionen)
                  pack_info = child.pack_info()
                  if pack_info.get('side') != tk.BOTTOM:
                       return child
        return None # Nicht gefunden

    # --- NEU: Hilfsfunktion, um das erste Eingabefeld zu finden ---
    def _find_first_entry(self, parent_widget):
         for child in parent_widget.winfo_children():
              if isinstance(child, tk.Entry):
                   return child
              elif isinstance(child, ttk.Frame) or isinstance(child, tk.Frame) or isinstance(child, ttk.LabelFrame):
                   # Rekursiv in Containern suchen
                   found = self._find_first_entry(child)
                   if found:
                        return found
         return None


    def body(self, master):
        # Pack options modified below
        main_frame = ttk.Frame(master, padding="15")
        # --- NEU: Markierung für _find_body_frame ---
        main_frame._is_body_frame = True
        # --------------------------------------------
        main_frame.columnconfigure(1, weight=1)

        self.vars = {
            "name": tk.StringVar(value=self.initial_data.get("name", "")),
            "abbreviation": tk.StringVar(value=self.initial_data.get("abbreviation", "")),
            "hours": tk.StringVar(value=str(self.initial_data.get("hours", 0.0))), # Float erlauben
            "start_time": tk.StringVar(value=self.initial_data.get("start_time", "")),
            "end_time": tk.StringVar(value=self.initial_data.get("end_time", "")),
            "description": tk.StringVar(value=self.initial_data.get("description", "")),
            "color": tk.StringVar(value=self.initial_data.get("color", "#FFFFFF")),
            "check_for_understaffing": tk.BooleanVar(value=self.initial_data.get("check_for_understaffing", False))
        }

        labels = [
            "Art (Name):", "Abkürzung (max. 3 Zeichen):", "Stunden (z.B. 8 oder 7.5):", # Text angepasst
            "Startzeit (HH:MM):", "Endzeit (HH:MM):", "Beschreibung:", "Hintergrundfarbe:"
        ]
        keys = [
            "name", "abbreviation", "hours", "start_time", "end_time", "description", "color"
        ]

        for i, (label_text, key) in enumerate(zip(labels, keys)):
            ttk.Label(main_frame, text=label_text).grid(row=i, column=0, sticky="w", pady=5, padx=5)
            if key == "color":
                color_frame = ttk.Frame(main_frame)
                color_frame.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                self.color_preview = tk.Label(color_frame, text=" Beispiel ", bg=self.vars[key].get(),
                                              relief="sunken", borderwidth=1, cursor="hand2",
                                              font=("Segoe UI", 10, "bold"), width=20)
                self.color_preview.pack(side=tk.LEFT, fill="both", expand=True)
                self.color_preview.bind("<Button-1>", lambda e, k=key: self.choose_color(k, self.color_preview))
                self.vars[key].trace_add('write', lambda *args, k=key: self.update_color_preview(k, self.color_preview))
            else:
                entry = tk.Entry(main_frame, textvariable=self.vars[key], width=40)
                entry.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                if key == "abbreviation":
                    vcmd_abbrev = (self.register(self.validate_abbreviation), '%P')
                    entry.config(validate='key', vcmd=vcmd_abbrev)
                    # Erlaube Bearbeitung der Abkürzung nicht mehr, um Konsistenzprobleme zu vermeiden
                    # if not self.is_new: entry.config(state='readonly') # Temporär entfernt, kann gefährlich sein
                elif key == "hours":
                    vcmd_hours = (self.register(self.validate_hours), '%P') # Geänderte Validierung
                    entry.config(validate='key', vcmd=vcmd_hours)
                elif key in ["start_time", "end_time"]:
                    vcmd_time = (self.register(self.validate_time), '%P')
                    entry.config(validate='key', vcmd=vcmd_time)

        ttk.Checkbutton(main_frame, text="Auf Unterbesetzung prüfen",
                        variable=self.vars["check_for_understaffing"]).grid(row=len(labels), column=0, columnspan=2,
                                                                            sticky="w", pady=10)
        self.update_color_preview('color', self.color_preview)

        # --- KORREKTUR: Pack-Optionen für main_frame ---
        # Füllt den restlichen Platz oberhalb der Buttons aus
        main_frame.pack(fill="both", expand=True, side=tk.TOP, padx=5, pady=5)
        # --- ENDE KORREKTUR ---


    def choose_color(self, var_key, preview_widget):
        initial_color = self.vars[var_key].get()
        color_code = colorchooser.askcolor(parent=self, title="Wähle eine Farbe", initialcolor=initial_color)
        if color_code and color_code[1]:
            self.vars[var_key].set(color_code[1].upper())

    def update_color_preview(self, var_key, preview_widget):
        color_val = self.vars[var_key].get()
        try:
            text_color = self.app.get_contrast_color(color_val) # self.app ist jetzt korrekt
            preview_widget.config(bg=color_val, fg=text_color)
        except tk.TclError:
            preview_widget.config(bg="#FFFFFF", fg='black')
        except AttributeError:
             # Fallback, falls get_contrast_color nicht verfügbar ist (sollte nicht passieren)
             print("[WARNUNG] get_contrast_color nicht in self.app gefunden.")
             preview_widget.config(bg="#FFFFFF", fg='black')


    def buttonbox(self, master):
        box = ttk.Frame(master, padding="10")
        ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="Abbrechen", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", (lambda event: self.ok()))
        self.bind("<Escape>", (lambda event: self.cancel()))
        # --- KORREKTUR: Pack-Optionen für box ---
        # Platziert die Buttons am unteren Rand
        box.pack(side=tk.BOTTOM, fill='x', padx=5, pady=5)
        # --- ENDE KORREKTUR ---

    def validate_abbreviation(self, P):
        # Erlaubt Buchstaben, Zahlen, Punkt und optional Bindestrich/Unterstrich
        # Länge immer noch max. 3 (oder wie benötigt)
        return len(P) <= 3 and all(c.isalnum() or c in '._-' for c in P)

    def validate_hours(self, P):
        # Erlaubt Zahlen und einen Dezimalpunkt
        if P == "": return True
        try:
            float(P)
            return True
        except ValueError:
            return False

    def validate_time(self, P):
        if P == "": return True
        # Erlaubt HH:MM Format
        if len(P) > 5: return False
        parts = P.split(':')
        if len(parts) > 2: return False
        if not all(part.isdigit() for part in parts): return False
        if len(parts) == 1 and len(P) > 2 : return False # z.B. 123
        if len(parts) == 2 and (len(parts[0]) > 2 or len(parts[1]) > 2): return False # z.B. 123:45 oder 12:345
        return True


    def ok(self, event=None):
        data = {key: var.get() for key, var in self.vars.items()}
        data['abbreviation'] = data['abbreviation'].strip().upper()
        data['color'] = data['color'].strip().upper()

        required_fields = ["name", "abbreviation", "hours"]
        if not all(str(data.get(f)).strip() for f in required_fields): # Prüfe auf leere Strings
            messagebox.showwarning("Eingabe fehlt", "Name, Abkürzung und Stunden sind Pflichtfelder.", parent=self)
            return

        # Zeit validieren
        for time_key in ["start_time", "end_time"]:
            time_str = data[time_key].strip()
            if time_str: # Nur prüfen, wenn nicht leer
                try:
                    # Versuche, verschiedene Formate zu parsen (HH:MM, H:MM, HH:M, H:M)
                    parts = time_str.split(':')
                    if len(parts) != 2: raise ValueError("Muss HH:MM Format sein")
                    hour = int(parts[0])
                    minute = int(parts[1])
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError("Ungültige Zeit")
                    # Formatiere auf HH:MM (z.B. 8:5 -> 08:05)
                    data[time_key] = f"{hour:02d}:{minute:02d}"
                except (ValueError, TypeError) as e:
                    messagebox.showwarning("Falsches Zeitformat", f"'{time_key}' ('{time_str}') ist ungültig. Bitte HH:MM verwenden (z.B. 08:00 oder 16:30).\nFehler: {e}", parent=self)
                    return
            else:
                 data[time_key] = None # Setze leere Zeiten auf None für die DB


        # Farbe validieren
        if not (data['color'].startswith('#') and len(data['color']) == 7 and all(
                c in '0123456789ABCDEF' for c in data['color'][1:].upper())):
            messagebox.showwarning("Eingabe Fehler", f"Ungültiger Hex-Code '{data['color']}' für die Hintergrundfarbe. Muss #RRGGBB sein.", parent=self)
            return

        # Stunden validieren (jetzt als Float)
        try:
            hours_val = float(data['hours'])
            if hours_val < 0: raise ValueError("Stunden dürfen nicht negativ sein")
            data['hours'] = hours_val # Speichere als Float
        except ValueError:
            messagebox.showerror("Fehler", "Stunden müssen eine gültige Zahl sein (z.B. 8 oder 7.5).", parent=self)
            return

        # ID für Update hinzufügen
        if not self.is_new:
            data['id'] = self.initial_data.get('id')

        self.result = data
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.destroy()