import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import get_ordered_users_for_schedule, save_user_order


class UserOrderWindow(tk.Toplevel):
    def __init__(self, parent, callback=None):
        super().__init__(parent)
        self.callback = callback
        self.title("Mitarbeiter-Reihenfolge und Sichtbarkeit")
        self.transient(parent)
        self.grab_set()

        self.users_data = []

        self.create_widgets()
        self.load_users()

        # --- Fenstergröße dynamisch anpassen und zentrieren ---
        self.update_idletasks()

        header_height = 30
        row_height = 28  # Feste Annahme für die Zeilenhöhe
        button_frame_height = 60
        label_height = 40

        total_height = header_height + (len(self.users_data) * row_height) + button_frame_height + label_height

        max_height = int(parent.winfo_height() * 0.8)
        total_height = min(total_height, max_height)

        # --- KORREKTUR: Mindestbreite erhöht ---
        min_width = 700

        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        position_x = parent_x + (parent_width // 2) - (min_width // 2)
        position_y = parent_y + (parent_height // 2) - (total_height // 2)

        self.geometry(f"{min_width}x{total_height}+{position_x}+{position_y}")
        self.minsize(min_width, 300)

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
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.heading("name", text="Name")
        self.tree.heading("role", text="Rolle")
        self.tree.heading("visible", text="Sichtbar im Plan")

        # --- KORREKTUR: "name"-Spalte dehnbar gemacht ---
        self.tree.column("name", minwidth=300, stretch=tk.YES)
        self.tree.column("role", width=150, stretch=tk.NO)
        self.tree.column("visible", width=150, anchor="center", stretch=tk.NO)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        button_subframe = ttk.Frame(list_frame)
        button_subframe.grid(row=0, column=2, sticky="ns", padx=(10, 0))

        up_button = ttk.Button(button_subframe, text="▲", command=lambda: self.move_entry(-1))
        up_button.pack(pady=5)

        down_button = ttk.Button(button_subframe, text="▼", command=lambda: self.move_entry(1))
        down_button.pack(pady=5)

        self.tree.bind("<Double-1>", self.toggle_visibility)
        self.tree.bind("<B1-Motion>", self.move_item_dnd)
        self.tree.bind("<ButtonRelease-1>", self.on_dnd_release)

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(10, 0))

        save_button = ttk.Button(bottom_frame, text="Speichern & Schließen", command=self.save_order)
        save_button.pack(side="right")

        cancel_button = ttk.Button(bottom_frame, text="Abbrechen", command=self.destroy)
        cancel_button.pack(side="right", padx=10)

    def load_users(self):
        self.users_data = get_ordered_users_for_schedule(include_hidden=True)
        self.populate_tree()

    def populate_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        for user in self.users_data:
            visibility_text = "Ja" if user.get('is_visible', 1) else "Nein"
            tags = ()
            if not user.get('is_visible', 1):
                tags = ('hidden',)
            self.tree.tag_configure('hidden', foreground='gray')
            self.tree.insert("", "end", iid=user['id'],
                             values=(f"{user['name']}, {user['vorname']}", user['role'], visibility_text),
                             tags=tags)

    def move_item_dnd(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.move(item_id, "", self.tree.index(item_id))

    def on_dnd_release(self, event):
        ordered_ids = self.tree.get_children()
        id_map = {str(u['id']): u for u in self.users_data}
        self.users_data = [id_map[str(uid)] for uid in ordered_ids if str(uid) in id_map]

    def move_entry(self, direction):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        item_id = selected_items[0]
        current_index = self.tree.index(item_id)

        self.tree.move(item_id, '', current_index + direction)

        self.on_dnd_release(None)

    def toggle_visibility(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        for user in self.users_data:
            if str(user['id']) == str(item_id):
                user['is_visible'] = 1 - user.get('is_visible', 1)
                break

        self.populate_tree()
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

    def save_order(self):
        ordered_ids = self.tree.get_children()

        user_map = {str(u['id']): u for u in self.users_data}

        final_order_list = []
        for index, user_id in enumerate(ordered_ids):
            if user_id in user_map:
                user_data = user_map[user_id]
                user_data['order_index'] = index
                final_order_list.append(user_data)

        success, message = save_user_order(final_order_list)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            if self.callback:
                self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)