import tkinter as tk
from tkinter import ttk, messagebox
from database.db_shifts import get_ordered_shift_abbrevs, save_shift_order


class ShiftOrderWindow(tk.Toplevel):
    def __init__(self, parent, callback=None):
        super().__init__(parent)
        self.parent = parent
        self.callback = callback

        self.title("Schicht-Reihenfolge und Sichtbarkeit anpassen")
        self.transient(parent)
        self.grab_set()

        self.shift_list = []

        self.create_widgets()
        self.load_shifts()

        self.update_idletasks()

        header_height = 30
        row_height = 28
        button_frame_height = 60
        label_height = 40

        total_height = header_height + (len(self.shift_list) * row_height) + button_frame_height + label_height

        max_height = int(parent.winfo_height() * 0.8)
        total_height = min(total_height, max_height)

        # --- KORREKTUR: Mindestbreite erhöht ---
        min_width = 650

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
                  text="Sortieren per Drag & Drop oder mit Buttons. Doppelklick zum Ändern der Optionen.").pack(
            anchor="w", pady=(0, 10))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(list_frame, columns=("name", "abbreviation", "visible", "understaffing"),
                                 show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.heading("name", text="Name der Schicht")
        self.tree.heading("abbreviation", text="Abkürzung")
        self.tree.heading("visible", text="Sichtbar in Zählung")
        self.tree.heading("understaffing", text="Unterbesetzung prüfen")

        # --- KORREKTUR: "name"-Spalte dehnbar gemacht ---
        self.tree.column("name", minwidth=200, stretch=tk.YES)
        self.tree.column("abbreviation", width=80, anchor="center", stretch=tk.NO)
        self.tree.column("visible", width=120, anchor="center", stretch=tk.NO)
        self.tree.column("understaffing", width=150, anchor="center", stretch=tk.NO)

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

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(10, 0))

        save_button = ttk.Button(bottom_frame, text="Speichern & Schließen", command=self.save_order)
        save_button.pack(side="right")

        cancel_button = ttk.Button(bottom_frame, text="Abbrechen", command=self.destroy)
        cancel_button.pack(side="right", padx=10)

    def load_shifts(self):
        self.shift_list = get_ordered_shift_abbrevs(include_hidden=True)
        self.populate_tree()

    def populate_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        for shift in self.shift_list:
            visible_text = "Ja" if shift.get('is_visible', 1) else "Nein"
            understaffing_text = "Ja" if shift.get('check_for_understaffing', 0) else "Nein"
            tags = ()
            if not shift.get('is_visible', 1):
                tags = ('hidden',)
            self.tree.tag_configure('hidden', foreground='gray')

            self.tree.insert("", "end", iid=shift['abbreviation'],
                             values=(shift['name'], shift['abbreviation'], visible_text, understaffing_text),
                             tags=tags)

    def move_item_dnd(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.move(item_id, "", self.tree.index(item_id))

    def move_entry(self, direction):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        item_id = selected_items[0]
        current_index = self.tree.index(item_id)
        self.tree.move(item_id, '', current_index + direction)

    def toggle_visibility(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        column_id = self.tree.identify_column(event.x)

        for shift in self.shift_list:
            if shift['abbreviation'] == item_id:
                if column_id == "#3":  # Sichtbar-Spalte
                    shift['is_visible'] = 1 - shift.get('is_visible', 1)
                elif column_id == "#4":  # Unterbesetzung-Spalte
                    shift['check_for_understaffing'] = 1 - shift.get('check_for_understaffing', 0)
                break
        self.populate_tree()
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

    def save_order(self):
        new_order_abbrevs = self.tree.get_children()
        final_order_data = []

        shift_map = {s['abbreviation']: s for s in self.shift_list}

        for index, abbrev in enumerate(new_order_abbrevs):
            if abbrev in shift_map:
                shift = shift_map[abbrev]
                final_order_data.append(
                    (abbrev, index, shift.get('is_visible', 1), shift.get('check_for_understaffing', 0))
                )

        success, message = save_shift_order(final_order_data)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            if self.callback:
                self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)