# gui/dialogs/shift_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_manager import get_ordered_shift_abbrevs, save_shift_order

class ShiftOrderWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Schicht-Zählungsreihenfolge und Sichtbarkeit anpassen")
        self.geometry("550x650") # Breite angepasst
        self.transient(master)
        self.grab_set()
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        ttk.Label(main_frame,
                  text="Sortieren Sie die Schichtkürzel für die Zählungszeilen und blenden Sie nicht benötigte Zeilen aus.",
                  wraplength=500, font=("Segoe UI", 10, "italic")).pack(pady=(0, 10), anchor="w")
        columns = ("abbrev", "name", "is_visible", "check_understaffing") # Neue Spalte
        self.shift_tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=20)
        self.shift_tree.heading("abbrev", text="Kürzel")
        self.shift_tree.heading("name", text="Schichtname")
        self.shift_tree.heading("is_visible", text="Sichtbar")
        self.shift_tree.heading("check_understaffing", text="Prüfen?") # Neuer Header
        self.shift_tree.column("abbrev", width=80, anchor="center")
        self.shift_tree.column("name", width=180, anchor="w")
        self.shift_tree.column("is_visible", width=80, anchor="center")
        self.shift_tree.column("check_understaffing", width=80, anchor="center") # Neue Spaltenkonfiguration
        self.shift_tree.pack(fill="both", expand=True)
        self.shift_tree.bind('<Button-1>', self.toggle_on_click)
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
            check_understaffing = item.get('check_for_understaffing', 0) == 1
            name = item.get('name', 'N/A')
            visible_text = "Ja" if is_visible else "Nein (Ausgeblendet)"
            check_text = "Ja" if check_understaffing else "Nein"
            tag = "visible" if is_visible else "hidden"
            self.shift_tree.insert("", tk.END, iid=abbrev, values=(abbrev, name, visible_text, check_text), tags=(tag,))
            self.shift_tree.tag_configure("hidden", foreground="grey", font=("Segoe UI", 10, "italic"))

    def toggle_on_click(self, event):
        region = self.shift_tree.identify('region', event.x, event.y)
        if region != 'cell': return
        column_name = self.shift_tree.heading(self.shift_tree.identify_column(event.x))['text']
        item_id = self.shift_tree.identify_row(event.y)

        if column_name in ['Sichtbar', 'Prüfen?']:
            current_values = list(self.shift_tree.item(item_id, 'values'))
            current_tags = list(self.shift_tree.item(item_id, 'tags'))

            if column_name == 'Sichtbar':
                is_currently_visible = current_tags[0] == 'visible'
                new_visible = not is_currently_visible
                new_text = "Ja" if new_visible else "Nein (Ausgeblendet)"
                new_tag = "visible" if new_visible else "hidden"
                current_values[2] = new_text
                current_tags[0] = new_tag
            elif column_name == 'Prüfen?':
                is_currently_checked = current_values[3] == "Ja"
                new_checked = not is_currently_checked
                new_text = "Ja" if new_checked else "Nein"
                current_values[3] = new_text

            self.shift_tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))

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
        ordered_data = []
        all_item_ids = self.shift_tree.get_children()
        for index, item_id in enumerate(all_item_ids):
            values = self.shift_tree.item(item_id, 'values')
            tags = self.shift_tree.item(item_id, 'tags')
            is_visible = 1 if tags[0] == 'visible' else 0
            check_for_understaffing = 1 if values[3] == "Ja" else 0
            abbrev = item_id
            sort_order = index + 1
            ordered_data.append((abbrev, sort_order, is_visible, check_for_understaffing))

        success, message = save_shift_order(ordered_data)
        if success:
            messagebox.showinfo("Erfolg", "Schichtreihenfolge gespeichert.", parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern der Schichtreihenfolge fehlgeschlagen.", parent=self)