# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog
from datetime import date, timedelta, datetime
import calendar
import json
import os
import holidays
from .holiday_manager import HolidayManager

from database.db_manager import (
    get_all_users, update_user, create_user_by_admin, delete_user,
    get_pending_requests, ROLE_HIERARCHY, get_all_dogs, add_dog, update_dog,
    delete_dog, get_dog_handlers, assign_dog,
    get_all_shift_types, add_shift_type, update_shift_type, delete_shift_type,
    save_shift_entry, get_shifts_for_month,
    get_ordered_users_for_schedule, save_user_order, get_daily_shift_counts_for_month,
    get_ordered_shift_abbrevs, save_shift_order,
    get_pending_wunschfrei_requests, update_wunschfrei_status, get_wunschfrei_requests_for_month,
    get_unread_admin_notifications, mark_admin_notifications_as_read, get_all_logs_formatted
)
from gui.registration_window import RegistrationWindow
from gui.column_manager import ColumnManager
from gui.column_settings_window import ColumnSettingsWindow
from tkcalendar import DateEntry
from .user_edit_window import UserEditWindow
from .dog_edit_window import DogEditWindow

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


class EditHolidayDialog(tk.Toplevel):
    def __init__(self, master, year, existing_holidays, holiday_to_edit=None):
        super().__init__(master)
        self.year = year
        self.existing_holidays = existing_holidays
        self.holiday_to_edit = holiday_to_edit
        self.result = None
        is_new = holiday_to_edit is None
        self.title("Neuen Feiertag anlegen" if is_new else "Feiertag bearbeiten")
        self.geometry("400x200")
        self.transient(master)
        self.grab_set()
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)
        ttk.Label(main_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        self.name_var = tk.StringVar()
        name_entry = ttk.Entry(main_frame, textvariable=self.name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(main_frame, text="Datum:").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 10))
        self.date_entry = DateEntry(main_frame, year=self.year, date_pattern='dd.mm.yyyy',
                                    foreground="black", headersforeground="black")
        self.date_entry.grid(row=1, column=1, sticky="ew")
        if not is_new:
            self.name_var.set(holiday_to_edit['name'])
            self.date_entry.set_date(holiday_to_edit['date'])
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_frame.columnconfigure((0, 1), weight=1)
        ttk.Button(button_frame, text="Speichern", command=self.save).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).grid(row=0, column=1, padx=(5, 0), sticky="ew")
        name_entry.focus_set()
        self.bind("<Return>", lambda e: self.save())

    def save(self):
        name = self.name_var.get().strip()
        new_date = self.date_entry.get_date()
        if not name:
            messagebox.showwarning("Eingabe fehlt", "Der Name darf nicht leer sein.", parent=self)
            return
        is_date_taken = new_date in self.existing_holidays and (
                self.holiday_to_edit is None or new_date != self.holiday_to_edit['date'])
        if is_date_taken:
            messagebox.showwarning("Datum belegt",
                                   f"Das Datum {new_date.strftime('%d.%m.%Y')} ist bereits als '{self.existing_holidays[new_date]}' vergeben.",
                                   parent=self)
            return
        self.result = {'name': name, 'date': new_date}
        self.destroy()


class HolidaySettingsWindow(tk.Toplevel):
    def __init__(self, master, year, callback):
        super().__init__(master)
        self.year = year
        self.callback = callback
        self.title(f"Feiertage für {self.year} verwalten")
        self.geometry("550x500")
        self.transient(master)
        self.grab_set()
        self.holidays = HolidayManager.get_holidays_for_year(self.year)
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        columns = ("date", "name")
        self.holiday_tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=15)
        self.holiday_tree.heading("date", text="Datum")
        self.holiday_tree.heading("name", text="Feiertag")
        self.holiday_tree.column("date", width=120, anchor="w")
        self.holiday_tree.column("name", width=300, anchor="w")
        self.holiday_tree.pack(fill="both", expand=True)
        self.holiday_tree.bind("<Double-1>", lambda e: self.edit_holiday())
        self.populate_tree()
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Hinzufügen", command=self.add_holiday).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Bearbeiten", command=self.edit_holiday).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Löschen", command=self.delete_holiday).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_and_close).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right")

    def populate_tree(self):
        for item in self.holiday_tree.get_children():
            self.holiday_tree.delete(item)
        sorted_holidays = sorted(self.holidays.items())
        for holiday_date, name in sorted_holidays:
            self.holiday_tree.insert("", tk.END, iid=holiday_date.isoformat(),
                                     values=(holiday_date.strftime('%d.%m.%Y'), name))

    def add_holiday(self):
        dialog = EditHolidayDialog(self, self.year, self.holidays)
        self.wait_window(dialog)
        if dialog.result:
            self.holidays[dialog.result['date']] = dialog.result['name']
            self.populate_tree()

    def edit_holiday(self):
        selection = self.holiday_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Feiertag zum Bearbeiten aus.", parent=self)
            return
        date_iso = selection[0]
        old_date = date.fromisoformat(date_iso)
        current_name = self.holidays[old_date]
        holiday_to_edit = {'date': old_date, 'name': current_name}
        dialog = EditHolidayDialog(self, self.year, self.holidays, holiday_to_edit)
        self.wait_window(dialog)
        if dialog.result:
            if old_date in self.holidays:
                del self.holidays[old_date]
            self.holidays[dialog.result['date']] = dialog.result['name']
            self.populate_tree()

    def delete_holiday(self):
        selection = self.holiday_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Feiertag zum Löschen aus.", parent=self)
            return
        date_iso = selection[0]
        holiday_date = date.fromisoformat(date_iso)
        if messagebox.askyesno("Bestätigen", f"Möchten Sie '{self.holidays[holiday_date]}' wirklich löschen?",
                               parent=self):
            del self.holidays[holiday_date]
            self.populate_tree()

    def save_and_close(self):
        all_holidays = {}
        if os.path.exists(HolidayManager.HOLIDAYS_FILE):
            with open(HolidayManager.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                try:
                    all_holidays = json.load(f)
                except json.JSONDecodeError:
                    pass
        all_holidays[str(self.year)] = {dt.isoformat(): name for dt, name in self.holidays.items()}
        HolidayManager.save_holidays(all_holidays)
        messagebox.showinfo("Gespeichert", "Die Feiertage wurden erfolgreich gespeichert.", parent=self)
        self.callback()
        self.destroy()


class UserOrderWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Mitarbeiter-Reihenfolge und Sichtbarkeit anpassen")
        self.geometry("550x650")
        self.transient(master)
        self.grab_set()
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        ttk.Label(main_frame,
                  text="Sortieren Sie die Mitarbeiter per Mausklick und den ↑/↓-Buttons. Haken Sie die Box 'Sichtbar' ab, um den Mitarbeiter im Schichtplan auszublenden.",
                  wraplength=500, font=("Segoe UI", 10, "italic")).pack(pady=(0, 10), anchor="w")
        columns = ("name", "dog", "is_visible")
        self.user_tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=20)
        self.user_tree.heading("name", text="Mitarbeiter")
        self.user_tree.heading("dog", text="Diensthund")
        self.user_tree.heading("is_visible", text="Sichtbar")
        self.user_tree.column("name", width=200, anchor="w")
        self.user_tree.column("dog", width=150, anchor="w")
        self.user_tree.column("is_visible", width=80, anchor="center")
        self.user_tree.pack(fill="both", expand=True)
        self.user_tree.bind('<Button-1>', self.toggle_visibility_on_click)
        self.populate_tree()
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)
        button_frame.columnconfigure((0, 1), weight=1)
        move_frame = ttk.Frame(button_frame)
        move_frame.pack(side="left", padx=(0, 20))
        ttk.Button(move_frame, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(side="left", padx=5)
        ttk.Button(move_frame, text="↓ Runter", command=lambda: self.move_item(1)).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_order).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def populate_tree(self):
        for item in self.user_tree.get_children(): self.user_tree.delete(item)
        all_users_in_order = get_ordered_users_for_schedule(include_hidden=True)
        for user in all_users_in_order:
            full_name = f"{user['vorname']} {user['name']}"
            dog_name = user.get('diensthund', '---')
            is_visible = user.get('is_visible', 1) == 1
            checkbox_text = "Ja" if is_visible else "Nein (Ausgeblendet)"
            tag = "visible" if is_visible else "hidden"
            self.user_tree.insert("", tk.END, iid=str(user['id']),
                                  values=(full_name, dog_name, checkbox_text),
                                  tags=(tag, str(user['id'])))
            self.user_tree.tag_configure("hidden", foreground="grey", font=("Segoe UI", 10, "italic"))

    def toggle_visibility_on_click(self, event):
        region = self.user_tree.identify('region', event.x, event.y)
        if region != 'cell': return
        column = self.user_tree.identify_column(event.x)
        item_id = self.user_tree.identify_row(event.y)
        if self.user_tree.heading(column)['text'] == 'Sichtbar':
            current_values = self.user_tree.item(item_id, 'values')
            current_tag = self.user_tree.item(item_id, 'tags')[0]
            is_currently_visible = current_tag == 'visible'
            new_visible = not is_currently_visible
            new_text = "Ja" if new_visible else "Nein (Ausgeblendet)"
            new_tag = "visible" if new_visible else "hidden"
            self.user_tree.item(item_id, values=(current_values[0], current_values[1], new_text),
                                tags=(new_tag, item_id))

    def move_item(self, direction):
        selection = self.user_tree.selection()
        if not selection: return
        item_id = selection[0]
        all_ids = self.user_tree.get_children()
        try:
            current_index = all_ids.index(item_id)
        except ValueError:
            return
        new_index = current_index + direction
        if 0 <= new_index < len(all_ids):
            self.user_tree.move(item_id, '', new_index)
            self.user_tree.selection_set(item_id)
            self.user_tree.focus(item_id)

    def save_order(self):
        ordered_ids_and_visibility = []
        all_item_ids = self.user_tree.get_children()
        for index, item_id in enumerate(all_item_ids):
            is_visible = 1 if self.user_tree.item(item_id, 'tags')[0] == 'visible' else 0
            user_id = int(item_id)
            sort_order = index + 1
            ordered_ids_and_visibility.append((user_id, sort_order, is_visible))
        success, message = save_user_order(ordered_ids_and_visibility)
        if success:
            messagebox.showinfo("Erfolg", "Mitarbeiterreihenfolge gespeichert.", parent=self)
            self.callback();
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern der Mitarbeiterreihenfolge fehlgeschlagen.", parent=self)


class ShiftOrderWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Schicht-Zählungsreihenfolge und Sichtbarkeit anpassen")
        self.geometry("450x650")
        self.transient(master)
        self.grab_set()
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        ttk.Label(main_frame,
                  text="Sortieren Sie die Schichtkürzel für die Zählungszeilen und blenden Sie nicht benötigte Zeilen aus.",
                  wraplength=400, font=("Segoe UI", 10, "italic")).pack(pady=(0, 10), anchor="w")
        columns = ("abbrev", "name", "is_visible")
        self.shift_tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=20)
        self.shift_tree.heading("abbrev", text="Kürzel")
        self.shift_tree.heading("name", text="Schichtname")
        self.shift_tree.heading("is_visible", text="Sichtbar")
        self.shift_tree.column("abbrev", width=80, anchor="center")
        self.shift_tree.column("name", width=180, anchor="w")
        self.shift_tree.column("is_visible", width=80, anchor="center")
        self.shift_tree.pack(fill="both", expand=True)
        self.shift_tree.bind('<Button-1>', self.toggle_visibility_on_click)
        self.populate_tree()
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)
        button_frame.columnconfigure((0, 1), weight=1)
        move_frame = ttk.Frame(button_frame)
        move_frame.pack(side="left", padx=(0, 20))
        ttk.Button(move_frame, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(side="left", padx=5)
        ttk.Button(move_frame, text="↓ Runter", command=lambda: self.move_item(1)).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_order).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def populate_tree(self):
        for item in self.shift_tree.get_children(): self.shift_tree.delete(item)
        all_abbrevs_in_order = get_ordered_shift_abbrevs(include_hidden=True)
        for item in all_abbrevs_in_order:
            abbrev = item['abbreviation']
            is_visible = item.get('is_visible', 1) == 1
            name = item.get('name', 'N/A')
            checkbox_text = "Ja" if is_visible else "Nein (Ausgeblendet)"
            tag = "visible" if is_visible else "hidden"
            self.shift_tree.insert("", tk.END, iid=abbrev, values=(abbrev, name, checkbox_text), tags=(tag,))
            self.shift_tree.tag_configure("hidden", foreground="grey", font=("Segoe UI", 10, "italic"))

    def toggle_visibility_on_click(self, event):
        region = self.shift_tree.identify('region', event.x, event.y)
        if region != 'cell': return
        column = self.shift_tree.identify_column(event.x)
        item_id = self.shift_tree.identify_row(event.y)
        if self.shift_tree.heading(column)['text'] == 'Sichtbar':
            current_values = self.shift_tree.item(item_id, 'values')
            current_tag = self.shift_tree.item(item_id, 'tags')[0]
            is_currently_visible = current_tag == 'visible'
            new_visible = not is_currently_visible
            new_text = "Ja" if new_visible else "Nein (Ausgeblendet)"
            new_tag = "visible" if new_visible else "hidden"
            self.shift_tree.item(item_id, values=(current_values[0], current_values[1], new_text), tags=(new_tag,))

    def move_item(self, direction):
        selection = self.shift_tree.selection()
        if not selection: return
        item_id = selection[0]
        all_ids = self.shift_tree.get_children()
        try:
            current_index = all_ids.index(item_id)
        except ValueError:
            return
        new_index = current_index + direction
        if 0 <= new_index < len(all_ids):
            self.shift_tree.move(item_id, '', new_index)
            self.shift_tree.selection_set(item_id)
            self.shift_tree.focus(item_id)

    def save_order(self):
        ordered_abbrevs_and_visibility = []
        all_item_ids = self.shift_tree.get_children()
        for index, item_id in enumerate(all_item_ids):
            is_visible = 1 if self.shift_tree.item(item_id, 'tags')[0] == 'visible' else 0
            abbrev = item_id
            sort_order = index + 1
            ordered_abbrevs_and_visibility.append((abbrev, sort_order, is_visible))
        success, message = save_shift_order(ordered_abbrevs_and_visibility)
        if success:
            messagebox.showinfo("Erfolg", "Schichtreihenfolge gespeichert.", parent=self)
            self.callback();
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern der Schichtreihenfolge fehlgeschlagen.", parent=self)


class MinStaffingWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.master = master
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
            self.callback();
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Fehler beim Speichern der Regeldatei.", parent=self)


class ShiftTypeDialog(tk.Toplevel):
    def __init__(self, admin_instance, callback_func, is_new, initial_data=None):
        super().__init__(admin_instance.master)
        self.admin_instance = admin_instance
        self.callback_func = callback_func
        self.is_new = is_new
        self.initial_data = initial_data if initial_data is not None else {}
        self.result = None
        self.title("Neue Schichtart anlegen" if is_new else "Schichtart bearbeiten")
        self.geometry("400x300")
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
        self.vars = {"name": tk.StringVar(value=self.initial_data.get("name", "")),
                     "abbreviation": tk.StringVar(value=self.initial_data.get("abbreviation", "")),
                     "hours": tk.StringVar(value=str(self.initial_data.get("hours", 0))),
                     "description": tk.StringVar(value=self.initial_data.get("description", "")),
                     "color": tk.StringVar(value=self.initial_data.get("color", "#FFFFFF")), }
        labels = ["Art (Name):", "Abkürzung (max. 3 Zeichen):", "Stunden (pro Schicht):", "Beschreibung:",
                  "Farbe wählen:"]
        keys = ["name", "abbreviation", "hours", "description", "color"]
        root = self.admin_instance.master
        for i, (label_text, key) in enumerate(zip(labels, keys)):
            ttk.Label(main_frame, text=label_text).grid(row=i, column=0, sticky="w", pady=5, padx=5)
            if key == "color":
                color_frame = ttk.Frame(main_frame)
                color_frame.grid(row=i, column=1, sticky="ew", pady=5, padx=5, columnspan=2)
                self.color_preview = tk.Label(color_frame, textvariable=self.vars["color"], bg=self.vars[key].get(),
                                              relief="sunken", borderwidth=1, cursor="hand2",
                                              font=("Segoe UI", 10, "bold"), width=20)
                self.color_preview.config(fg=self.admin_instance.get_contrast_color(self.vars['color'].get()))
                self.color_preview.pack(side=tk.LEFT, fill="both", expand=True)
                self.color_preview.bind("<Button-1>", lambda e: self.choose_color())
                self.vars[key].trace_add('write', lambda *args: self.update_color_preview())
            else:
                entry = tk.Entry(main_frame, textvariable=self.vars[key], width=40)
                entry.grid(row=i, column=1, sticky="ew", pady=5, padx=5,
                           columnspan=(1 if key in ["abbreviation", "hours"] else 2))
                if key == "abbreviation":
                    vcmd_abbrev = (root.register(self.validate_abbreviation), '%P')
                    entry.config(validate='key', vcmd=vcmd_abbrev)
                    if not self.is_new:
                        entry.config(state='readonly', disabledbackground="lightgrey")
                        ttk.Label(main_frame, text="(Nicht änderbar)").grid(row=i, column=2, sticky="w", pady=5, padx=5)
                if key == "hours":
                    vcmd_hours = (root.register(self.validate_hours), '%P')
                    entry.config(validate='key', vcmd=vcmd_hours)
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
        if P.isdigit() or P == "": return True
        return False

    def ok(self, event=None):
        name = self.vars['name'].get().strip()
        abbreviation = self.vars['abbreviation'].get().strip().upper()
        hours_str = self.vars['hours'].get().strip()
        description = self.vars['description'].get().strip()
        color = self.vars['color'].get().strip().upper()
        if not name or not abbreviation or not hours_str or not color:
            messagebox.showwarning("Eingabe fehlt", "Alle Felder (Name, Abkürzung, Stunden, Farbe) sind Pflichtfelder.",
                                   parent=self)
            return
        if not (color.startswith('#') and len(color) == 7 and all(c in '0123456789ABCDEF' for c in color[1:])):
            messagebox.showwarning("Eingabe Fehler", "Interner Fehler: Ungültiger Hex-Code.", parent=self)
            return
        if not self.validate_abbreviation(abbreviation) and abbreviation != abbreviation.upper():
            messagebox.showwarning("Eingabe Fehler",
                                   "Die Abkürzung ist ungültig. Bitte maximal 3 Zeichen (Buchstaben, Zahlen, Punkt) verwenden.",
                                   parent=self)
            return
        try:
            hours = int(hours_str)
        except ValueError:
            messagebox.showerror("Fehler", "Stunden müssen eine ganze Zahl sein.", parent=self)
            return
        self.result = {"name": name, "abbreviation": abbreviation, "hours": hours, "description": description,
                       "color": color}
        self.callback_func(self.result, self.initial_data.get('id') if not self.is_new else None)
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.destroy()


class MainAdminWindow(tk.Toplevel):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.master = master
        self.logged_in_user = user_data
        full_name = f"{self.logged_in_user.get('vorname')} {self.logged_in_user.get('name')}".strip()
        self.title(f"Admin-Dashboard - Angemeldet als {full_name}")
        self.geometry("1200x800")
        self.state("zoomed")
        self.current_display_date = date.today()
        self.user_data_store = {}
        self.dog_data_store = []
        self.shift_types_data = {}
        self.shift_schedule_data = {}
        self.staffing_rules = load_staffing_rules()
        self.current_year_holidays = {}
        self._load_holidays_for_year(self.current_display_date.year)
        self.user_data_store = get_all_users()
        self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)

        # NEU: Kopfzeile für Benachrichtigungen
        header_frame = ttk.Frame(self, padding=5)
        header_frame.pack(fill="x", side="top")

        style = ttk.Style(self)
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"))

        self.pending_urlaub_var = tk.StringVar()
        urlaub_label = ttk.Label(header_frame, textvariable=self.pending_urlaub_var, style="Header.TLabel")
        urlaub_label.pack(side="right", padx=10)

        self.pending_wunschfrei_var = tk.StringVar()
        wunschfrei_label = ttk.Label(header_frame, textvariable=self.pending_wunschfrei_var, style="Header.TLabel")
        wunschfrei_label.pack(side="right", padx=10)

        # Notebook für die Haupt-Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))  # pady top entfernt

        self.create_requests_tab()
        self.create_wunschfrei_tab()
        self.create_user_management_tab()
        self.create_dogs_tab()
        self.create_shift_type_settings_tab()
        self.create_log_tab()
        self.create_shift_plan_tab()
        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)
        self.load_shift_types()

        self.after(100, self.check_for_admin_notifications)
        self.update_notification_indicators()

    # NEUE METHODEN
    def update_notification_indicators(self):
        """Aktualisiert die Zähler für offene Anträge in der Kopfzeile."""
        num_wunschfrei = len(get_pending_wunschfrei_requests())
        num_urlaub = len(get_pending_requests())

        self.pending_wunschfrei_var.set(f"🔔 Offene Wunschfrei-Anträge: {num_wunschfrei}")
        self.pending_urlaub_var.set(f"🔔 Offene Urlaubsanträge: {num_urlaub}")

    def check_for_admin_notifications(self):
        unread_notifications = get_unread_admin_notifications()
        if not unread_notifications:
            return

        message_lines = ["Seit Ihrem letzten Login gab es folgende Aktivitäten:"]
        notified_ids = []
        for notification in unread_notifications:
            message_lines.append(f"- {notification['message']}")
            notified_ids.append(notification['id'])

        messagebox.showinfo("Benachrichtigung", "\n".join(message_lines), parent=self)
        mark_admin_notifications_as_read(notified_ids)
        self.refresh_log_tab()  # Log-Tab aktualisieren, falls sichtbar

    def create_log_tab(self):
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text="Protokoll")

        button_frame = ttk.Frame(log_frame)
        button_frame.pack(fill="x", pady=(0, 5))
        ttk.Button(button_frame, text="Aktualisieren", command=self.refresh_log_tab).pack(side="left")

        columns = ("timestamp", "user", "action", "details")
        self.log_tree = ttk.Treeview(log_frame, columns=columns, show="headings")
        self.log_tree.heading("timestamp", text="Zeitstempel")
        self.log_tree.heading("user", text="Benutzer")
        self.log_tree.heading("action", text="Aktion")
        self.log_tree.heading("details", text="Details")

        self.log_tree.column("timestamp", width=150, anchor="w")
        self.log_tree.column("user", width=150, anchor="w")
        self.log_tree.column("action", width=150, anchor="w")
        self.log_tree.column("details", width=500, anchor="w")

        self.log_tree.pack(fill="both", expand=True)
        self.refresh_log_tab()

    def refresh_log_tab(self):
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

        logs = get_all_logs_formatted()
        for log_entry in logs:
            self.log_tree.insert("", tk.END, values=(
                log_entry['timestamp'],
                log_entry['user_name'],
                log_entry['action_type'],
                log_entry['details']
            ))

    # (Rest der Methoden bleibt gleich, nur die Aufrufe zur Aktualisierung werden hinzugefügt)
    # ...
    def _load_holidays_for_year(self, year):
        # ... (unverändert)
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def is_holiday(self, check_date):
        # ... (unverändert)
        return check_date in self.current_year_holidays

    def get_min_staffing_for_date(self, current_date):
        # ... (unverändert)
        weekday = current_date.weekday()
        is_holiday_check = self.is_holiday(current_date)
        rules = self.staffing_rules
        min_staffing = {}
        min_staffing.update(rules.get('Daily', {}))
        if is_holiday_check:
            min_staffing.update(rules.get('Holiday', {}))
        elif weekday in [5, 6]:
            min_staffing.update(rules.get('Sa-So', {}))
        elif weekday == 4:
            min_staffing.update(rules.get('Fr', {}))
        elif weekday in [0, 1, 2, 3]:
            min_staffing.update(rules.get('Mo-Do', {}))
        return {k: int(v) for k, v in min_staffing.items() if v is not None and str(v).isdigit()}

    def create_requests_tab(self):
        # ... (unverändert)
        requests_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(requests_frame, text="Urlaubsanträge")
        columns = ("user", "start_date", "end_date", "status")
        self.request_tree = ttk.Treeview(requests_frame, columns=columns, show="headings")
        self.request_tree.heading("user", text="Mitarbeiter")
        self.request_tree.heading("start_date", text="Von")
        self.request_tree.heading("end_date", text="Bis")
        self.request_tree.heading("status", text="Status")
        self.request_tree.pack(fill="both", expand=True)
        self.request_tree.tag_configure("ausstehend", background="khaki")
        self.refresh_requests_tree()
        button_frame = ttk.Frame(requests_frame)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Antrag genehmigen", command=self.approve_request).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Antrag ablehnen", command=self.deny_request).pack(side="left", padx=5)

    def refresh_requests_tree(self):
        # ... (unverändert)
        for item in self.request_tree.get_children(): self.request_tree.delete(item)
        pending_requests = get_pending_requests()
        for req in pending_requests:
            full_name = f"{req['vorname']} {req['name']}".strip()
            start_date_obj = datetime.strptime(req['start_date'], '%Y-%m-%d')
            end_date_obj = datetime.strptime(req['end_date'], '%Y-%m-%d')
            display_values = (
                full_name, start_date_obj.strftime('%d.%m.%Y'), end_date_obj.strftime('%d.%m.%Y'), req['status'])
            self.request_tree.insert("", tk.END, iid=req['id'], values=display_values, tags=("ausstehend",))

    def approve_request(self):
        messagebox.showinfo("Info", "Funktion 'Genehmigen' noch nicht implementiert.")
        self.update_notification_indicators()  # Platzhalter-Aufruf

    def deny_request(self):
        messagebox.showinfo("Info", "Funktion 'Ablehnen' noch nicht implementiert.")
        self.update_notification_indicators()  # Platzhalter-Aufruf

    def create_wunschfrei_tab(self):
        # ... (unverändert)
        wunschfrei_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(wunschfrei_frame, text="Wunschfrei Anträge")
        columns = ("user", "date")
        self.wunschfrei_tree = ttk.Treeview(wunschfrei_frame, columns=columns, show="headings")
        self.wunschfrei_tree.heading("user", text="Mitarbeiter")
        self.wunschfrei_tree.heading("date", text="Datum")
        self.wunschfrei_tree.pack(fill="both", expand=True)
        self.wunschfrei_tree.tag_configure("Ausstehend", background="orange")
        self.refresh_wunschfrei_tree()
        button_frame = ttk.Frame(wunschfrei_frame)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Anfrage genehmigen", command=self.approve_wunschfrei).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Anfrage ablehnen", command=self.deny_wunschfrei).pack(side="left", padx=5)

    def refresh_wunschfrei_tree(self):
        # ... (unverändert)
        for item in self.wunschfrei_tree.get_children():
            self.wunschfrei_tree.delete(item)
        pending_requests = get_pending_wunschfrei_requests()
        for req in pending_requests:
            full_name = f"{req['vorname']} {req['name']}".strip()
            date_obj = datetime.strptime(req['request_date'], '%Y-%m-%d')
            display_values = (full_name, date_obj.strftime('%d.%m.%Y'))
            self.wunschfrei_tree.insert("", tk.END, iid=req['id'], values=display_values, tags=("Ausstehend",))

    def process_wunschfrei_request(self, approve):
        selection = self.wunschfrei_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Anfrage aus.", parent=self)
            return

        request_id = int(selection[0])
        all_pending_requests = get_pending_wunschfrei_requests()
        req_data = next((r for r in all_pending_requests if r['id'] == request_id), None)

        if not req_data:
            messagebox.showerror("Fehler", "Anfrage nicht mehr gefunden.", parent=self)
            self.refresh_wunschfrei_tree()
            return

        user_id = req_data['user_id']
        request_date_str = req_data['request_date']
        new_status = "Genehmigt" if approve else "Abgelehnt"
        rejection_reason = None

        if not approve:
            reason = simpledialog.askstring("Ablehnungsgrund", "Bitte geben Sie einen Grund für die Ablehnung an:",
                                            parent=self)
            if reason is None:
                return
            rejection_reason = reason.strip()

        success_status, msg_status = update_wunschfrei_status(request_id, new_status, reason=rejection_reason)

        if not success_status:
            messagebox.showerror("Fehler", f"Status konnte nicht aktualisiert werden: {msg_status}", parent=self)
            return

        if approve:
            if 'X' not in self.shift_types_data:
                messagebox.showwarning("Hinweis",
                                       "Die Schichtart 'X' für genehmigtes Wunschfrei existiert nicht. Der Tag wird als 'FREI' eingetragen, aber es wird empfohlen, 'X' unter 'Schichtarten' anzulegen.",
                                       parent=self)
                success_shift, msg_shift = save_shift_entry(user_id, request_date_str, "FREI")
            else:
                success_shift, msg_shift = save_shift_entry(user_id, request_date_str, 'X')

            if not success_shift:
                messagebox.showerror("Fehler beim Eintragen", msg_shift, parent=self)
                return

        action = "genehmigt" if approve else "abgelehnt"
        messagebox.showinfo("Erfolg",
                            f"Anfrage wurde {action}. Der Mitarbeiter wird beim nächsten Login benachrichtigt.",
                            parent=self)
        self.refresh_wunschfrei_tree()
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
        self.update_notification_indicators()  # NEU: Zähler aktualisieren

    def approve_wunschfrei(self):
        # ... (unverändert)
        self.process_wunschfrei_request(approve=True)

    def deny_wunschfrei(self):
        # ... (unverändert)
        self.process_wunschfrei_request(approve=False)

    def create_user_management_tab(self):
        # ... (unverändert)
        user_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(user_frame, text="Benutzerverwaltung")
        self.column_config = ColumnManager.load_config()
        visible_columns = self.column_config.get('visible', ColumnManager.DEFAULT_VISIBLE)
        all_columns_dict = self.column_config.get('all_columns', {})
        self.user_tree = ttk.Treeview(user_frame, columns=list(all_columns_dict.keys()), show="headings")
        self.user_tree["columns"] = list(all_columns_dict.keys())
        for col_key, col_text in all_columns_dict.items():
            self.user_tree.heading(col_key, text=col_text)
            self.user_tree.column(col_key, width=120, anchor="w")
        self.user_tree["displaycolumns"] = tuple(visible_columns)
        self.user_tree.pack(fill="both", expand=True, side="left")
        self.refresh_user_tree()
        user_buttons_frame = ttk.Frame(user_frame, padding="10")
        user_buttons_frame.pack(side="left", fill="y", padx=10)
        ttk.Button(user_buttons_frame, text="Benutzer anlegen...", command=self.create_user).pack(fill="x", pady=5)
        ttk.Button(user_buttons_frame, text="Benutzer bearbeiten...", command=self.edit_user).pack(fill="x", pady=5)
        ttk.Button(user_buttons_frame, text="Benutzer löschen", command=self.delete_selected_user).pack(fill="x",
                                                                                                        pady=5)
        ttk.Separator(user_buttons_frame).pack(fill="x", pady=10)
        ttk.Button(user_buttons_frame, text="Spalten anpassen...", command=self.open_column_settings).pack(fill="x",
                                                                                                           pady=5)

    def open_column_settings(self):
        # ... (unverändert)
        ColumnSettingsWindow(self, self)

    def refresh_user_management_tab(self):
        # ... (unverändert)
        for i, tab_name in enumerate(self.notebook.tabs()):
            if self.notebook.tab(i, "text") == "Benutzerverwaltung":
                self.notebook.forget(i)
                self.create_user_management_tab()
                self.notebook.select(i)
                return

    def refresh_user_tree(self):
        # ... (unverändert)
        for item in self.user_tree.get_children(): self.user_tree.delete(item)
        self.user_data_store = get_all_users()
        all_columns = self.user_tree["columns"]
        for user_id, data in self.user_data_store.items():
            values_for_all_columns = []
            for col_key in all_columns:
                value = data.get(col_key, "")
                if col_key == 'entry_date' and value:
                    try:
                        value = datetime.strptime(value, '%Y-%m-%d').strftime('%d.%m.%Y')
                    except (ValueError, TypeError):
                        pass
                values_for_all_columns.append(value)
            self.user_tree.insert("", tk.END, values=values_for_all_columns, iid=user_id)

    def get_allowed_roles(self):
        # ... (unverändert)
        admin_level = ROLE_HIERARCHY.get(self.logged_in_user['role'], 0)
        if self.logged_in_user['role'] == "SuperAdmin":
            return sorted([role for role, level in ROLE_HIERARCHY.items() if level <= admin_level],
                          key=lambda r: ROLE_HIERARCHY.get(r, 0))
        return sorted([role for role, level in ROLE_HIERARCHY.items() if level < admin_level],
                      key=lambda r: ROLE_HIERARCHY.get(r, 0))

    def edit_user(self):
        # ... (unverändert)
        if not self.user_tree.selection():
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Benutzer aus.", parent=self)
            return
        selected_id = self.user_tree.selection()[0]
        user_data_to_edit = self.user_data_store.get(selected_id)
        is_super_admin = self.logged_in_user['role'] == "SuperAdmin"
        if not is_super_admin:
            if str(self.logged_in_user['id']) == selected_id:
                messagebox.showerror("Zugriff verweigert",
                                     "Sie können Ihr eigenes Konto nicht über diese Maske bearbeiten.", parent=self)
                return
            admin_level = ROLE_HIERARCHY.get(self.logged_in_user['role'], 0)
            target_level = ROLE_HIERARCHY.get(user_data_to_edit['role'], 0)
            if admin_level <= target_level:
                messagebox.showerror("Zugriff verweigert",
                                     "Sie können nur Benutzer mit einer niedrigeren Rolle bearbeiten.", parent=self)
                return
        if user_data_to_edit:
            UserEditWindow(self, selected_id, user_data_to_edit, self.update_user_data, is_new=False,
                           allowed_roles=self.get_allowed_roles())
        else:
            messagebox.showerror("Fehler", "Benutzerdaten konnten nicht gefunden werden.", parent=self)

    def update_user_data(self, user_id, new_data):
        # ... (unverändert)
        update_user(user_id, new_data)
        self.refresh_user_tree()
        self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def create_user(self):
        # ... (unverändert)
        today_str = date.today().strftime('%Y-%m-%d')
        empty_data = {"vorname": "", "name": "", "geburtstag": "", "telefon": "", "diensthund": "", "urlaub_gesamt": 30,
                      "role": "Benutzer", "entry_date": today_str}
        UserEditWindow(self, None, empty_data, self.add_new_user, is_new=True, allowed_roles=self.get_allowed_roles())

    def add_new_user(self, user_id, new_data):
        # ... (unverändert)
        success = create_user_by_admin(new_data)
        if success:
            messagebox.showinfo("Erfolg", "Benutzer wurde erfolgreich angelegt.", parent=self)
            self.refresh_user_tree()
            self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)
            self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
        else:
            messagebox.showerror("Fehler", "Ein Benutzer mit diesem Namen existiert bereits.", parent=self)

    def delete_selected_user(self):
        # ... (unverändert)
        if not self.user_tree.selection():
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Benutzer aus.", parent=self)
            return
        selected_id = self.user_tree.selection()[0]
        user_to_delete = self.user_data_store.get(selected_id)
        admin_level = ROLE_HIERARCHY.get(self.logged_in_user['role'], 0)
        target_level = ROLE_HIERARCHY.get(user_to_delete['role'], 0)
        if admin_level <= target_level:
            messagebox.showerror("Zugriff verweigert",
                                 "Sie können keine Benutzer mit gleicher oder höherer Rolle löschen.", parent=self)
            return
        full_name = f"{user_to_delete['vorname']} {user_to_delete['name']}"
        if messagebox.askyesno("Bestätigen", f"Möchten Sie den Benutzer {full_name} wirklich endgültig löschen?",
                               parent=self):
            if delete_user(selected_id):
                messagebox.showinfo("Erfolg", "Benutzer wurde gelöscht.", parent=self)
                self.refresh_user_tree()
                self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)
                self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
            else:
                messagebox.showerror("Fehler", "Der Benutzer konnte nicht gelöscht werden.", parent=self)

    def create_dogs_tab(self):
        # ... (unverändert)
        dogs_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(dogs_frame, text="Diensthunde")
        paned_window = ttk.PanedWindow(dogs_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill="both", expand=True)
        list_frame = ttk.Frame(paned_window, padding="5")
        paned_window.add(list_frame, weight=1)
        columns = ("name", "breed", "age")
        self.dog_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.dog_tree.heading("name", text="Name")
        self.dog_tree.heading("breed", text="Rasse")
        self.dog_tree.heading("age", text="Alter")
        self.dog_tree.column("age", width=60, anchor="center")
        self.dog_tree.pack(fill="both", expand=True)
        self.dog_tree.bind("<<TreeviewSelect>>", self.on_dog_selected)
        dog_buttons = ttk.Frame(list_frame)
        dog_buttons.pack(fill="x", pady=5)
        ttk.Button(dog_buttons, text="Hund anlegen...", command=self.add_new_dog).pack(side="left", padx=5)
        ttk.Button(dog_buttons, text="Bearbeiten...", command=self.open_dog_edit_window).pack(side="left", padx=5)
        ttk.Button(dog_buttons, text="Löschen", command=self.delete_selected_dog).pack(side="left", padx=5)
        self.detail_frame = ttk.LabelFrame(paned_window, text="Details", padding="15")
        paned_window.add(self.detail_frame, weight=2)
        self.dog_detail_vars = {"Name": tk.StringVar(), "Rasse": tk.StringVar(), "Geburtsdatum": tk.StringVar(),
                                "Alter": tk.StringVar(), "Chipnummer": tk.StringVar(), "Zugang": tk.StringVar(),
                                "Abgang": tk.StringVar(), "Letzte DPO": tk.StringVar(), "Impfungen": tk.StringVar(),
                                "Hundeführer": tk.StringVar()}
        for i, (label_text, var) in enumerate(self.dog_detail_vars.items()):
            ttk.Label(self.detail_frame, text=f"{label_text}:", font=("Segoe UI", 10, "bold")).grid(row=i, column=0,
                                                                                                    sticky="nw", pady=2,
                                                                                                    padx=5)
            ttk.Label(self.detail_frame, textvariable=var, wraplength=400).grid(row=i, column=1, sticky="nw", pady=2,
                                                                                padx=5)
        assign_frame = ttk.LabelFrame(self.detail_frame, text="Hundeführer zuweisen", padding=10)
        assign_frame.grid(row=len(self.dog_detail_vars), column=0, columnspan=2, sticky="ew", pady=10)
        self.user_combobox = ttk.Combobox(assign_frame, state="readonly")
        self.user_combobox.pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(assign_frame, text="Zuweisen", command=self.assign_selected_dog).pack(side="left", padx=5)
        handlers_frame = ttk.LabelFrame(self.detail_frame, text="Aktuelle Hundeführer", padding=10)
        handlers_frame.grid(row=len(self.dog_detail_vars) + 1, column=0, columnspan=2, sticky="ew", pady=5)
        self.dog_handlers_var = tk.StringVar()
        ttk.Label(handlers_frame, textvariable=self.dog_handlers_var, font=("Segoe UI", 10, "italic")).pack(anchor="w")
        self.refresh_dogs_list()
        self.clear_dog_details()

    def refresh_dogs_list(self):
        # ... (unverändert)
        for item in self.dog_tree.get_children(): self.dog_tree.delete(item)
        self.dog_data_store = get_all_dogs()
        for dog in self.dog_data_store:
            age = "Unbekannt"
            if dog.get("birth_date"):
                try:
                    birth_date = datetime.strptime(dog["birth_date"], '%Y-%m-%d').date()
                    age = (date.today() - birth_date).days // 365
                except (ValueError, TypeError):
                    pass
            self.dog_tree.insert("", tk.END, iid=dog['id'], values=(dog['name'], dog['breed'], age))
        self.clear_dog_details()

    def on_dog_selected(self, event=None):
        # ... (unverändert)
        selection = self.dog_tree.selection()
        if not selection: return
        dog_id = int(selection[0])
        dog_data = next((d for d in self.dog_data_store if d['id'] == dog_id), None)
        if not dog_data: return
        for key, var in self.dog_detail_vars.items(): var.set("---")
        age = "Unbekannt"
        if dog_data.get("birth_date"):
            try:
                birth_date = datetime.strptime(dog_data["birth_date"], '%Y-%m-%d').date()
                age = f"{(date.today() - birth_date).days // 365} Jahre"
                self.dog_detail_vars["Geburtsdatum"].set(birth_date.strftime('%d.%m.%Y'))
            except (ValueError, TypeError):
                pass
        self.dog_detail_vars["Name"].set(dog_data.get('name', '---'))
        self.dog_detail_vars["Rasse"].set(dog_data.get('breed', '---'))
        self.dog_detail_vars["Alter"].set(age)
        self.dog_detail_vars["Chipnummer"].set(dog_data.get('chip_number', '---'))
        if dog_data.get('acquisition_date'): self.dog_detail_vars["Zugang"].set(
            datetime.strptime(dog_data['acquisition_date'], '%Y-%m-%d').strftime('%d.%m.%Y'))
        if dog_data.get('departure_date'): self.dog_detail_vars["Abgang"].set(
            datetime.strptime(dog_data['departure_date'], '%Y-%m-%d').strftime('%d.%m.%Y'))
        if dog_data.get('last_dpo_date'): self.dog_detail_vars["Letzte DPO"].set(
            datetime.strptime(dog_data['last_dpo_date'], '%Y-%m-%d').strftime('%d.%m.%Y'))
        self.dog_detail_vars["Impfungen"].set(dog_data.get('vaccination_info', '---'))
        handlers = get_dog_handlers(dog_data['name'])
        if handlers:
            handler_names = [f"{h['vorname']} {h['name']}" for h in handlers]
            self.dog_handlers_var.set(", ".join(handler_names))
        else:
            self.dog_handlers_var.set("Nicht zugewiesen")
        all_users = get_all_users()
        user_list = [f"{user['vorname']} {user['name']}" for user in all_users.values()]
        self.user_combobox['values'] = user_list

    def clear_dog_details(self):
        # ... (unverändert)
        for var in self.dog_detail_vars.values(): var.set("")
        self.dog_handlers_var.set("")
        self.user_combobox['values'] = []
        self.user_combobox.set("")

    def add_new_dog(self):
        # ... (unverändert)
        empty_data = {"name": "", "breed": "", "birth_date": "", "chip_number": "", "acquisition_date": "",
                      "departure_date": "", "last_dpo_date": "", "vaccination_info": ""}
        DogEditWindow(self, empty_data, self.save_new_dog_callback, is_new=True)

    def save_new_dog_callback(self, dog_id, new_data):
        # ... (unverändert)
        if add_dog(new_data):
            messagebox.showinfo("Erfolg", "Diensthund wurde erfolgreich angelegt.", parent=self)
            self.refresh_dogs_list()
        else:
            messagebox.showerror("Fehler", "Ein Hund mit diesem Namen oder Chipnummer existiert bereits.", parent=self)

    def open_dog_edit_window(self):
        # ... (unverändert)
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Hund zum Bearbeiten aus.", parent=self)
            return
        dog_id = int(selection[0])
        dog_data = next((d for d in self.dog_data_store if d['id'] == dog_id), None)
        if dog_data:
            DogEditWindow(self, dog_data, self.save_edit_dog_callback, is_new=False)

    def save_edit_dog_callback(self, dog_id, new_data):
        # ... (unverändert)
        if update_dog(dog_id, new_data):
            messagebox.showinfo("Erfolg", "Änderungen wurden gespeichert.", parent=self)
            self.refresh_dogs_list()
            self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
        else:
            messagebox.showerror("Fehler", "Speichern fehlgeschlagen. Name oder Chipnummer möglicherweise doppelt.",
                                 parent=self)

    def delete_selected_dog(self):
        # ... (unverändert)
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Hund zum Bearbeiten aus.", parent=self)
            return
        dog_id = int(selection[0])
        dog_name = self.dog_tree.item(selection[0])['values'][0]
        if messagebox.askyesno("Bestätigen", f"Möchten Sie den Hund '{dog_name}' wirklich endgültig löschen?",
                               parent=self, icon="warning"):
            if delete_dog(dog_id):
                messagebox.showinfo("Erfolg", "Diensthund wurde gelöscht.", parent=self)
                self.refresh_dogs_list()
                self.refresh_user_tree()
                self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
            else:
                messagebox.showerror("Fehler", "Der Hund konnte nicht gelöscht werden.", parent=self)

    def assign_selected_dog(self):
        # ... (unverändert)
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Hund aus.", parent=self)
            return
        dog_name = self.dog_tree.item(selection[0])['values'][0]
        selected_user_name = self.user_combobox.get()
        if not selected_user_name:
            messagebox.showwarning("Keine Auswahl",
                                   "Bitte wählen Sie einen Benutzer aus, dem der Hund zugewiesen werden soll.",
                                   parent=self)
            return
        all_users = get_all_users()
        user_id_to_assign = None
        for uid, udata in all_users.items():
            if f"{udata['vorname']} {udata['name']}" == selected_user_name:
                user_id_to_assign = uid
                break
        if user_id_to_assign:
            if assign_dog(dog_name, user_id_to_assign):
                messagebox.showinfo("Erfolg", f"'{dog_name}' wurde erfolgreich {selected_user_name} zugewiesen.",
                                    parent=self)
                self.on_dog_selected(None)
                self.refresh_user_tree()
                self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
            else:
                messagebox.showerror("Fehler", "Zuweisung fehlgeschlagen.", parent=self)
        else:
            messagebox.showerror("Fehler", "Ausgewählter Benutzer nicht gefunden.", parent=self)

    def load_shift_types(self):
        # ... (unverändert)
        shift_types_list = get_all_shift_types()
        self.shift_types_data = {st['abbreviation']: st for st in shift_types_list}
        if hasattr(self, 'shift_tree') and self.shift_type_frame.winfo_exists():
            self.refresh_shift_type_tree()
            self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def create_shift_type_settings_tab(self):
        # ... (unverändert)
        self.shift_type_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.shift_type_frame, text="Schichtarten")
        main_frame = ttk.Frame(self.shift_type_frame)
        main_frame.pack(fill="both", expand=True)
        ttk.Label(main_frame,
                  text="Hier können Sie alle verfügbaren Schichtarten (Art, Abkürzung, Stunden, Farbe, etc.) definieren.",
                  font=("Segoe UI", 12, "italic")).pack(pady=(10, 20), anchor="w")
        columns = ("id", "name", "abbreviation", "hours", "description", "color")
        self.shift_tree = ttk.Treeview(main_frame, columns=columns, show="headings")
        self.shift_tree.column("id", width=0, stretch=tk.NO)
        self.shift_tree.heading("name", text="Art")
        self.shift_tree.heading("abbreviation", text="Abkürzung")
        self.shift_tree.heading("hours", text="Std.")
        self.shift_tree.heading("description", text="Beschreibung")
        self.shift_tree.heading("color", text="Farbe (Hex)")
        self.shift_tree.column("name", width=150, anchor="w")
        self.shift_tree.column("abbreviation", width=80, anchor="center")
        self.shift_tree.column("hours", width=60, anchor="center")
        self.shift_tree.column("description", width=250, anchor="w")
        self.shift_tree.column("color", width=100, anchor="center")
        self.shift_tree.pack(fill="both", expand=True, pady=(0, 10))
        self.shift_tree.bind('<Double-1>', self.edit_selected_shift_type)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(button_frame, text="+ Hinzufügen", command=self.add_shift_type).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Bearbeiten", command=self.edit_selected_shift_type).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Löschen", command=self.delete_shift_type).pack(side="left", padx=5)
        self.refresh_shift_type_tree()

    def refresh_shift_type_tree(self):
        # ... (unverändert)
        if not hasattr(self, 'shift_tree') or not self.shift_type_frame.winfo_exists(): return
        for item in self.shift_tree.get_children(): self.shift_tree.delete(item)
        shift_types = get_all_shift_types()
        for st in shift_types:
            values = (st['id'], st['name'], st['abbreviation'], st['hours'], st['description'], st['color'])
            self.shift_tree.insert("", tk.END, iid=str(st['id']), values=values, tags=(st['color'],))
            self.shift_tree.tag_configure(st['color'], background=st['color'],
                                          foreground=self.get_contrast_color(st['color']))

    def get_contrast_color(self, hex_color):
        # ... (unverändert)
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def handle_shift_type_dialog_result(self, data, shift_type_id=None):
        # ... (unverändert)
        if not data: return
        if shift_type_id is None:
            success, message = add_shift_type(data)
        else:
            success, message = update_shift_type(shift_type_id, data)
        if success:
            action = "hinzugefügt" if shift_type_id is None else "aktualisiert"
            messagebox.showinfo("Erfolg", f"Schichtart erfolgreich {action}.", parent=self)
            self.load_shift_types()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def add_shift_type(self):
        # ... (unverändert)
        ShiftTypeDialog(self, self.handle_shift_type_dialog_result, is_new=True)

    def edit_selected_shift_type(self, event=None):
        # ... (unverändert)
        selection = self.shift_tree.selection()
        if not selection:
            if event: return
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Bearbeiten aus.", parent=self)
            return
        shift_type_id = int(selection[0])
        current_values = self.shift_tree.item(shift_type_id, 'values')
        initial_data = {"id": current_values[0], "name": current_values[1], "abbreviation": current_values[2],
                        "hours": current_values[3], "description": current_values[4], "color": current_values[5]}
        ShiftTypeDialog(self, self.handle_shift_type_dialog_result, is_new=False, initial_data=initial_data)

    def delete_shift_type(self):
        # ... (unverändert)
        selection = self.shift_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Bearbeiten aus.", parent=self)
            return
        shift_type_id = int(selection[0])
        name = self.shift_tree.item(shift_type_id, 'values')[1]
        if messagebox.askyesno("Bestätigen", f"Möchten Sie die Schichtart '{name}' wirklich löschen?", parent=self,
                               icon='warning'):
            success, message = delete_shift_type(shift_type_id)
            if success:
                self.load_shift_types()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def open_user_order_window(self):
        # ... (unverändert)
        UserOrderWindow(self, self.refresh_shift_plan_tab)

    def open_shift_order_window(self):
        # ... (unverändert)
        ShiftOrderWindow(self, self.refresh_shift_plan_tab)

    def open_staffing_rules_window(self):
        # ... (unverändert)
        MinStaffingWindow(self, self.refresh_staffing_rules)

    def open_holiday_settings_window(self):
        # ... (unverändert)
        HolidaySettingsWindow(self, self.current_display_date.year, self.refresh_holidays_and_plan)

    def refresh_holidays_and_plan(self):
        # ... (unverändert)
        self._load_holidays_for_year(self.current_display_date.year)
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def refresh_staffing_rules(self):
        # ... (unverändert)
        self.staffing_rules = load_staffing_rules()
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def refresh_shift_plan_tab(self):
        # ... (unverändert)
        self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def create_shift_plan_tab(self):
        # ... (unverändert)
        self.plan_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.plan_tab_frame, text="Schichtplan")
        main_view_container = ttk.Frame(self.plan_tab_frame)
        main_view_container.pack(fill="both", expand=True)
        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))
        nav_left_frame = ttk.Frame(nav_frame)
        nav_left_frame.pack(side="left")
        prev_button = ttk.Button(nav_left_frame, text="< Voriger Monat", command=self.show_previous_month)
        prev_button.pack(side="left")
        self.month_label_var = tk.StringVar()
        month_label = ttk.Label(nav_frame, textvariable=self.month_label_var, font=("Segoe UI", 14, "bold"),
                                anchor="center")
        month_label.pack(side="left", expand=True, fill="x")
        nav_right_frame = ttk.Frame(nav_frame)
        nav_right_frame.pack(side="right")
        ttk.Button(nav_right_frame, text="Feiertage verwalten", command=self.open_holiday_settings_window).pack(
            side="left", padx=(10, 5))
        ttk.Button(nav_right_frame, text="Besetzungsregeln", command=self.open_staffing_rules_window).pack(side="left",
                                                                                                           padx=(10, 5))
        ttk.Button(nav_right_frame, text="Schicht-Sortierung", command=self.open_shift_order_window).pack(side="left",
                                                                                                          padx=(10, 5))
        ttk.Button(nav_right_frame, text="Mitarbeiter-Sortierung", command=self.open_user_order_window).pack(
            side="left", padx=(10, 5))
        next_button = ttk.Button(nav_right_frame, text="Nächster Monat >", command=self.show_next_month)
        next_button.pack(side="left")
        grid_container_frame = ttk.Frame(main_view_container)
        grid_container_frame.pack(fill="both", expand=True)
        self.vsb = ttk.Scrollbar(grid_container_frame, orient="vertical")
        self.vsb.pack(side="right", fill="y")
        self.hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal")
        self.hsb.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.config(command=self.canvas.yview)
        self.hsb.config(command=self.canvas.xview)
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")
        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)
        self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

    def on_grid_cell_click(self, event):
        # ... (unverändert)
        try:
            x, y = event.x_root, event.y_root
            widget = self.plan_grid_frame.winfo_containing(x, y)
            if not widget: return
            while widget.master != self.plan_grid_frame:
                widget = widget.master
                if widget is None or widget == self: return
            grid_info = widget.grid_info()
            if not grid_info: return
            col, row = int(grid_info['column']), int(grid_info['row'])
            num_users = len(self.current_user_order)
            if row < 2 or col < 2 or row >= (num_users + 2): return
            user_index = row - 2
            users = self.current_user_order
            if user_index >= len(users): return
            user_id = str(users[user_index]['id'])
            day = col - 1
            if day > calendar.monthrange(self.current_display_date.year, self.current_display_date.month)[1]: return
            shift_date = date(self.current_display_date.year, self.current_display_date.month, day)
            shift_date_str = shift_date.strftime('%Y-%m-%d')
            current_shift = ""
            if isinstance(widget, tk.Frame):
                if widget.pack_slaves():
                    current_shift = widget.pack_slaves()[0].cget("text")
            elif isinstance(widget, ttk.Label):
                current_shift = widget.cget("text")
            shift_options = sorted(list(self.shift_types_data.keys()))
            shift_options.insert(0, "FREI")
            combobox_var = tk.StringVar(value=current_shift if current_shift else "FREI")

            def on_select(event=None):
                new_shift = combobox_var.get()
                success, message = save_shift_entry(user_id, shift_date_str, new_shift)
                combo.destroy()
                if success:
                    self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)
                else:
                    messagebox.showerror("Fehler", message, parent=self)

            def on_focus_out(event):
                if combo.winfo_exists():
                    combo.destroy()
                    self.build_shift_plan_grid(self.current_display_date.year, self.current_display_date.month)

            for w in widget.winfo_children(): w.destroy()
            if not isinstance(widget, tk.Frame): widget.grid_forget()
            combo_parent = widget if isinstance(widget, tk.Frame) else self.plan_grid_frame
            combo = ttk.Combobox(combo_parent, textvariable=combobox_var, values=shift_options, state="readonly",
                                 width=5)
            if isinstance(widget, tk.Frame):
                combo.pack(fill="both", expand=True)
            else:
                combo.grid(row=row, column=col, sticky="nsew")
            combo.bind("<<ComboboxSelected>>", on_select)
            combo.bind("<Return>", on_select)
            combo.bind("<FocusOut>", on_focus_out)
            combo.focus_set()
            combo.event_generate('<Down>')
        except Exception:
            pass

    def build_shift_plan_grid(self, year, month):
        # ... (unverändert)
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        self.current_user_order = get_ordered_users_for_schedule(include_hidden=False)
        users = self.current_user_order
        self.shift_schedule_data = get_shifts_for_month(year, month)
        wunschfrei_data = get_wunschfrei_requests_for_month(year, month)
        daily_counts = get_daily_shift_counts_for_month(year, month)
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        color_map = {"URLAUB": "mediumseagreen", "KRANK": "lightcoral", "FREI": "white", "WF": "orange",
                     "X": "lightgreen"}
        for abbrev, data in self.shift_types_data.items():
            color_map[abbrev] = data.get('color', '#FFFFFF')
        month_name = date(year, month, 1).strftime('%B')
        self.month_label_var.set(f"{month_name.capitalize()} {year}")
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        days_in_month = calendar.monthrange(year, month)[1]
        header_bg, weekend_bg = "#E0E0E0", "#F0F0F0"
        summary_bg = "#D0D0FF"
        color_rules = self.staffing_rules.get('Colors', DEFAULT_RULES['Colors'])
        alert_bg, success_bg, overstaffed_bg = color_rules.get('alert_bg'), color_rules.get(
            'success_bg'), color_rules.get('overstaffed_bg')
        MIN_NAME_WIDTH, MIN_DOG_WIDTH = 150, 100
        ttk.Label(self.plan_grid_frame, text="Mitarbeiter", font=("Segoe UI", 10, "bold"), background=header_bg,
                  padding=5, borderwidth=1, relief="solid", foreground="black").grid(row=0, column=0, columnspan=2,
                                                                                     sticky="nsew")
        ttk.Label(self.plan_grid_frame, text="Name", font=("Segoe UI", 9, "bold"), background=header_bg, padding=5,
                  borderwidth=1, relief="solid", foreground="black").grid(row=1, column=0, sticky="nsew")
        ttk.Label(self.plan_grid_frame, text="Diensthund", font=("Segoe UI", 9, "bold"), background=header_bg,
                  padding=5, borderwidth=1, relief="solid", foreground="black").grid(row=1, column=1, sticky="nsew")
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_abbr = day_map[current_date.weekday()]
            is_weekend = current_date.weekday() >= 5
            is_holiday_check = self.is_holiday(current_date)
            bg = weekend_bg if is_weekend else header_bg
            if is_holiday_check: bg = "#FFD700"
            if is_weekend or is_holiday_check:
                frame_h1 = tk.Frame(self.plan_grid_frame, bg="blue")
                frame_h1.grid(row=0, column=day + 1, sticky="nsew")
                ttk.Label(frame_h1, text=day_abbr, font=("Segoe UI", 9, "bold"), background=bg, padding=5,
                          anchor="center", foreground="black").pack(fill="both", expand=True, padx=1, pady=1)
                frame_h2 = tk.Frame(self.plan_grid_frame, bg="blue")
                frame_h2.grid(row=1, column=day + 1, sticky="nsew")
                ttk.Label(frame_h2, text=str(day), font=("Segoe UI", 9), background=bg, padding=5, anchor="center",
                          foreground="black").pack(fill="both", expand=True, padx=1, pady=1)
            else:
                ttk.Label(self.plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), background=bg, padding=5,
                          borderwidth=1, relief="solid", anchor="center", foreground="black").grid(row=0,
                                                                                                   column=day + 1,
                                                                                                   sticky="nsew")
                ttk.Label(self.plan_grid_frame, text=str(day), font=("Segoe UI", 9), background=bg, padding=5,
                          borderwidth=1, relief="solid", anchor="center", foreground="black").grid(row=1,
                                                                                                   column=day + 1,
                                                                                                   sticky="nsew")
        ttk.Label(self.plan_grid_frame, text="Stunden", font=("Segoe UI", 10, "bold"), background=header_bg, padding=5,
                  borderwidth=1, relief="solid", foreground="black").grid(row=0, column=days_in_month + 2, rowspan=2,
                                                                          sticky="nsew")
        current_row = 2
        for row_idx, user_data_row in enumerate(users):
            user_name = f"{user_data_row['vorname']} {user_data_row['name']}"
            user_dog = user_data_row.get('diensthund', '---')
            user_id_str = str(user_data_row['id'])
            ttk.Label(self.plan_grid_frame, text=user_name, font=("Segoe UI", 10, "bold"), padding=5, borderwidth=1,
                      relief="solid", foreground="black", background="white").grid(row=current_row, column=0,
                                                                                   sticky="nsew")
            ttk.Label(self.plan_grid_frame, text=user_dog, font=("Segoe UI", 10), padding=5, borderwidth=1,
                      relief="solid", foreground="black", anchor="center", background="white").grid(row=current_row,
                                                                                                    column=1,
                                                                                                    sticky="nsew")
            total_hours = 0
            for day in range(1, days_in_month + 1):
                col_idx = day + 1
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str, "")

                wunschfrei_status = wunschfrei_data.get(user_id_str, {}).get(date_str)
                if wunschfrei_status == 'Ausstehend':
                    shift = 'WF'
                elif wunschfrei_status == 'Genehmigt' and shift != 'X':
                    shift = 'X'

                if shift in self.shift_types_data:
                    shift_hours = self.shift_types_data[shift]['hours']
                    if day == days_in_month:
                        if shift in self.OVERNIGHT_SHIFT_24H_ABBREVIATIONS:
                            total_hours += self.OVERNIGHT_SHIFT_24H_CURRENT_MONTH_HOURS
                        elif shift in self.OVERNIGHT_SHIFT_12H_ABBREVIATIONS:
                            total_hours += self.OVERNIGHT_SHIFT_12H_CURRENT_MONTH_HOURS
                        else:
                            total_hours += shift_hours
                    else:
                        total_hours += shift_hours
                bg_color, text_color = color_map.get(shift, "white"), self.get_contrast_color(
                    color_map.get(shift, "white"))
                is_weekend, is_holiday_check = current_date.weekday() >= 5, self.is_holiday(current_date)
                if is_weekend or is_holiday_check:
                    cell_frame = tk.Frame(self.plan_grid_frame, bg="blue")
                    cell_frame.grid(row=current_row, column=col_idx, sticky="nsew")
                    label = ttk.Label(cell_frame, text=shift, background=bg_color, padding=5, anchor="center",
                                      foreground=text_color, cursor="hand2")
                    label.pack(fill="both", expand=True, padx=1, pady=1)
                    cell_frame.bind("<Button-1>", self.on_grid_cell_click)
                    label.bind("<Button-1>", self.on_grid_cell_click)
                else:
                    label = ttk.Label(self.plan_grid_frame, text=shift, background=bg_color, padding=5, borderwidth=1,
                                      relief="solid", anchor="center", foreground=text_color, cursor="hand2")
                    label.grid(row=current_row, column=col_idx, sticky="nsew")
                    label.bind("<Button-1>", self.on_grid_cell_click)
            ttk.Label(self.plan_grid_frame, text=str(total_hours), font=("Segoe UI", 10, "bold"), padding=5,
                      borderwidth=1, relief="solid", anchor="e", foreground="black", background="white").grid(
                row=current_row, column=days_in_month + 2, sticky="nsew")
            current_row += 1
        ttk.Label(self.plan_grid_frame, text="", background=header_bg, padding=2, borderwidth=0).grid(row=current_row,
                                                                                                      column=0,
                                                                                                      columnspan=days_in_month + 3,
                                                                                                      sticky="nsew")
        current_row += 1
        ttk.Label(self.plan_grid_frame, text="Tageszählungen und Mindestbesetzung", font=("Segoe UI", 10, "bold"),
                  background=header_bg, padding=5, borderwidth=1, relief="solid", foreground="black").grid(
            row=current_row, column=0, columnspan=days_in_month + 3, sticky="nsew")
        current_row += 1
        for item in ordered_abbrevs_to_show:
            abbrev, name_text = item['abbreviation'], item.get('name', 'N/A')
            ttk.Label(self.plan_grid_frame, text=abbrev, font=("Segoe UI", 9, "bold"), padding=5, borderwidth=1,
                      relief="solid", anchor="center", background=summary_bg, foreground="black").grid(row=current_row,
                                                                                                       column=0,
                                                                                                       sticky="nsew")
            ttk.Label(self.plan_grid_frame, text=name_text, font=("Segoe UI", 9), padding=5, borderwidth=1,
                      relief="solid", anchor="w", background=summary_bg, foreground="black").grid(row=current_row,
                                                                                                  column=1,
                                                                                                  sticky="nsew")
            for day in range(1, days_in_month + 1):
                col_idx = day + 1
                current_date = date(year, month, day)
                count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                min_required = self.get_min_staffing_for_date(current_date).get(abbrev)
                bg, text_color = summary_bg, "black"
                if min_required is not None:
                    if count < min_required:
                        bg, text_color = alert_bg, "white"
                    elif count > min_required:
                        bg, text_color = overstaffed_bg, "black"
                    else:
                        bg, text_color = success_bg, "black"
                display_text = f"{count}/{min_required}" if min_required is not None else str(count)
                is_weekend, is_holiday_check = current_date.weekday() >= 5, self.is_holiday(current_date)
                if is_weekend or is_holiday_check:
                    summary_frame = tk.Frame(self.plan_grid_frame, bg="blue")
                    summary_frame.grid(row=current_row, column=col_idx, sticky="nsew")
                    ttk.Label(summary_frame, text=display_text, background=bg, padding=5, anchor="center",
                              foreground=text_color).pack(fill="both", expand=True, padx=1, pady=1)
                else:
                    ttk.Label(self.plan_grid_frame, text=display_text, background=bg, padding=5, borderwidth=1,
                              relief="solid", anchor="center", foreground=text_color).grid(row=current_row,
                                                                                           column=col_idx,
                                                                                           sticky="nsew")
            ttk.Label(self.plan_grid_frame, text="---", font=("Segoe UI", 9), padding=5, borderwidth=1, relief="solid",
                      anchor="e", background=summary_bg, foreground="black").grid(row=current_row,
                                                                                  column=days_in_month + 2,
                                                                                  sticky="nsew")
            current_row += 1
        self.plan_grid_frame.grid_columnconfigure(0, weight=0, minsize=MIN_NAME_WIDTH)
        self.plan_grid_frame.grid_columnconfigure(1, weight=0, minsize=MIN_DOG_WIDTH)
        for day_col in range(2, days_in_month + 3): self.plan_grid_frame.grid_columnconfigure(day_col, weight=1)
        self.plan_grid_frame.grid_columnconfigure(days_in_month + 2, weight=0)
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def show_previous_month(self):
        current_year, current_month = self.current_display_date.year, self.current_display_date.month
        prev_month, prev_year = (current_month - 1, current_year) if current_month > 1 else (12, current_year - 1)
        if prev_year != current_year: self._load_holidays_for_year(prev_year)
        self.current_display_date = date(prev_year, prev_month, 1)
        self.build_shift_plan_grid(prev_year, prev_month)

    def show_next_month(self):
        current_year, current_month = self.current_display_date.year, self.current_display_date.month
        next_month, next_year = (current_month + 1, current_year) if current_month < 12 else (1, current_year + 1)
        if next_year != current_year: self._load_holidays_for_year(next_year)
        self.current_display_date = date(next_year, next_month, 1)
        self.build_shift_plan_grid(next_year, next_month)