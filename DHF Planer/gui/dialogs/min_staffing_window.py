# gui/dialogs/min_staffing_window.py (KORRIGIERT: Liest/Schreibt Regeln in DB)
import tkinter as tk
from tkinter import ttk, messagebox
import json
from collections import defaultdict

from database.db_manager import load_staffing_rules, save_staffing_rules # Importiert DB-Funktionen


class MinStaffingWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Mindestbesetzungs-Regeln bearbeiten")
        self.geometry("700x500")
        self.transient(master)
        self.grab_set()

        self.rules = load_staffing_rules() # LÄDT AUS DB
        self.temp_rules = defaultdict(dict, self.rules.copy())
        self.shift_types = master.shift_types_data
        self.selected_rule_set = tk.StringVar(value="Daily")
        self.vars = {}

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)

        # Rule Set Selection
        rule_set_frame = ttk.Frame(main_frame)
        rule_set_frame.pack(fill="x", pady=5)
        ttk.Label(rule_set_frame, text="Regel-Set:").pack(side="left", padx=(0, 10))
        rule_sets = ["Daily", "Sa-So", "Fr", "Mo-Do", "Holiday"]
        ttk.Combobox(rule_set_frame, textvariable=self.selected_rule_set, values=rule_sets, state="readonly",
                     command=self.load_rule_set).pack(side="left")

        # Color Rules Button
        ttk.Button(rule_set_frame, text="Farben anpassen...", command=self.open_color_rules).pack(side="right")

        # Treeview for Rules
        self.rules_tree = ttk.Treeview(main_frame, columns=("shift", "min_staff"), show="headings", height=15)
        self.rules_tree.heading("shift", text="Schicht")
        self.rules_tree.heading("min_staff", text="Mindestbesetzung")
        self.rules_tree.column("shift", width=150, anchor="w")
        self.rules_tree.column("min_staff", width=150, anchor="center")
        self.rules_tree.pack(fill="both", expand=True, pady=10)
        self.rules_tree.bind('<Double-1>', self.edit_rule)

        # Input Frame
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill="x", pady=5)
        input_frame.columnconfigure((1, 3), weight=1)

        ttk.Label(input_frame, text="Schicht:").grid(row=0, column=0, padx=5, sticky="w")
        self.vars['shift'] = tk.StringVar()
        shift_options = sorted(list(self.shift_types.keys()))
        self.shift_combobox = ttk.Combobox(input_frame, textvariable=self.vars['shift'], values=shift_options,
                                           state="readonly")
        self.shift_combobox.grid(row=0, column=1, padx=5, sticky="ew")

        ttk.Label(input_frame, text="Besetzung:").grid(row=0, column=2, padx=5, sticky="w")
        self.vars['min_staff'] = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.vars['min_staff']).grid(row=0, column=3, padx=5, sticky="ew")

        # Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)
        button_frame.columnconfigure((0, 1, 2), weight=1)

        ttk.Button(button_frame, text="Hinzufügen/Speichern", command=self.add_or_update_rule).grid(row=0, column=0,
                                                                                                    sticky="ew", padx=5)
        ttk.Button(button_frame, text="Löschen", command=self.delete_rule).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_rules).grid(row=0, column=2,
                                                                                               sticky="ew", padx=5)

        self.load_rule_set()

    def load_rule_set(self, event=None):
        for item in self.rules_tree.get_children():
            self.rules_tree.delete(item)

        current_set = self.selected_rule_set.get()
        current_rules = self.temp_rules[current_set]

        for shift, staff in current_rules.items():
            self.rules_tree.insert("", tk.END, values=(shift, staff), tags=(shift,))

        self.rules_tree.tag_configure("Warning", background="yellow")

    def add_or_update_rule(self):
        shift = self.vars['shift'].get()
        staff_str = self.vars['min_staff'].get()
        current_set = self.selected_rule_set.get()

        if not shift or not staff_str.isdigit():
            messagebox.showwarning("Eingabe ungültig", "Bitte eine Schicht auswählen und eine gültige Zahl für die Besetzung eingeben.", parent=self)
            return

        staff = int(staff_str)
        self.temp_rules[current_set][shift] = staff
        self.load_rule_set()
        self.clear_inputs()

    def delete_rule(self):
        selection = self.rules_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte eine Regel zum Löschen auswählen.", parent=self)
            return

        item_id = selection[0]
        shift = self.rules_tree.item(item_id, 'values')[0]
        current_set = self.selected_rule_set.get()

        if shift in self.temp_rules[current_set]:
            del self.temp_rules[current_set][shift]
            self.load_rule_set()

    def edit_rule(self, event):
        item = self.rules_tree.selection()
        if not item: return

        values = self.rules_tree.item(item[0], 'values')
        self.vars['shift'].set(values[0])
        self.vars['min_staff'].set(values[1])

    def clear_inputs(self):
        self.vars['shift'].set("")
        self.vars['min_staff'].set("")

    def save_rules(self):
        """Speichert die Regeln in der Datenbank (ersetzt JSON-Speicherung)."""
        success = save_staffing_rules(self.temp_rules) # SCHREIBT IN DB
        if success:
            messagebox.showinfo("Erfolg", "Mindestbesetzungs-Regeln gespeichert.", parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern in der Datenbank fehlgeschlagen.", parent=self)

    def open_color_rules(self):
        messagebox.showinfo("Farben anpassen", "Die Farbregeln (im 'Colors'-Set) können hier bearbeitet werden.", parent=self)
        # Implementierung des Farbregel-Dialogs wäre hier, wenn er existiert.
        # Da hier nur eine MessageBox steht, wird diese beibehalten.