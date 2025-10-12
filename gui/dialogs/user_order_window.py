# gui/dialogs/user_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import get_ordered_users_for_schedule, save_user_order

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
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Speichern der Mitarbeiterreihenfolge fehlgeschlagen.", parent=self)