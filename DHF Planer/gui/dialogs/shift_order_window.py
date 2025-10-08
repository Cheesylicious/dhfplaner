# gui/dialogs/shift_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_manager import get_ordered_shift_abbrevs, save_shift_order

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
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern der Schichtreihenfolge fehlgeschlagen.", parent=self)