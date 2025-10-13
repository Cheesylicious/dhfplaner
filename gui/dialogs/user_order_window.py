import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import get_ordered_users_for_schedule, save_user_order


class UserOrderWindow(tk.Toplevel):
    def __init__(self, parent, callback=None):
        super().__init__(parent)
        self.callback = callback
        self.title("Mitarbeiter-Reihenfolge und Sichtbarkeit")
        self.geometry("600x500")
        self.transient(parent)
        self.grab_set()

        self.users_data = []

        self.create_widgets()
        self.load_users()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame,
                  text="Sortieren per Drag & Drop oder mit den Buttons. Doppelklick zum Ein-/Ausblenden.").pack(
            anchor="w", pady=(0, 10))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(list_frame, columns=("name", "role", "visible"), show="headings", selectmode="browse")
        self.tree.heading("name", text="Name")
        self.tree.heading("role", text="Rolle")
        self.tree.heading("visible", text="Sichtbarkeit")
        self.tree.column("name", width=300)
        self.tree.column("role", width=150)
        self.tree.column("visible", width=150, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        # --- KORREKTUR: Buttons für die Sortierung hinzugefügt ---
        button_subframe = ttk.Frame(list_frame)
        button_subframe.grid(row=0, column=2, sticky="ns", padx=(10, 0))
        ttk.Button(button_subframe, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(pady=2, fill="x")
        ttk.Button(button_subframe, text="↓ Runter", command=lambda: self.move_item(1)).pack(pady=2, fill="x")

        self.tree.bind("<ButtonPress-1>", self.on_press)
        self.tree.bind("<B1-Motion>", self.on_drag)
        self.tree.bind("<ButtonRelease-1>", self.on_release)
        self.tree.bind("<Double-1>", self.toggle_visibility)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", pady=10, padx=10)

        save_button = ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_order)
        save_button.pack(side="right", padx=5)
        cancel_button = ttk.Button(button_frame, text="Abbrechen", command=self.destroy)
        cancel_button.pack(side="right")

    def load_users(self):
        self.users_data = get_ordered_users_for_schedule(include_hidden=True)
        self.populate_tree()

    def populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for user in self.users_data:
            visible_text = "Ja (Sichtbar)" if user.get('is_visible', 1) == 1 else "Nein (Ausgeblendet)"
            self.tree.insert("", "end", iid=user['id'],
                             values=(f"{user['vorname']} {user['name']}", user['role'], visible_text))

    def on_press(self, event):
        self.drag_item = self.tree.identify_row(event.y)

    def on_drag(self, event):
        if self.drag_item:
            moveto_item = self.tree.identify_row(event.y)
            if moveto_item and moveto_item != self.drag_item:
                self.tree.move(self.drag_item, '', self.tree.index(moveto_item))

    def on_release(self, event):
        self.drag_item = None

    # --- KORREKTUR: Logik zum Verschieben mit Buttons hinzugefügt ---
    def move_item(self, direction):
        selection = self.tree.selection()
        if not selection:
            return

        item_id = selection[0]
        current_index = self.tree.index(item_id)

        # Verschiebe das Item in der Treeview-Anzeige
        self.tree.move(item_id, '', current_index + direction)

        # Stelle sicher, dass das verschobene Item selektiert bleibt
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

    def toggle_visibility(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        for user in self.users_data:
            if str(user['id']) == str(item_id):
                user['is_visible'] = 1 - user.get('is_visible', 1)
                break

        self.populate_tree()
        # Selektion wiederherstellen
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

    def save_order(self):
        ordered_ids = self.tree.get_children()

        user_map = {str(u['id']): u for u in self.users_data}

        final_order_list = []
        for user_id in ordered_ids:
            if user_id in user_map:
                final_order_list.append(user_map[user_id])

        success, message = save_user_order(final_order_list)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            if self.callback:
                self.callback()  # Ruft refresh_all_tabs() im Hauptfenster auf
            self.destroy()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Benutzerreihenfolge: {message}", parent=self)