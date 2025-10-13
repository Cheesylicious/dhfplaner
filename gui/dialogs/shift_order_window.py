import tkinter as tk
from tkinter import ttk, messagebox
from database.db_shifts import get_ordered_shift_abbrevs, save_shift_order


class ShiftOrderWindow(tk.Toplevel):
    def __init__(self, parent, callback=None):
        super().__init__(parent)
        self.parent = parent
        self.callback = callback

        self.title("Schicht-Reihenfolge und Sichtbarkeit anpassen")
        self.geometry("600x500")
        self.transient(parent)
        self.grab_set()

        self.shift_list = []

        self.create_widgets()
        self.load_shifts()

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
                                 show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("abbreviation", text="Abk.")
        self.tree.heading("visible", text="Sichtbar")
        self.tree.heading("understaffing", text="Unterbesetzung prüfen")

        self.tree.column("name", width=200)
        self.tree.column("abbreviation", width=50, anchor="center")
        self.tree.column("visible", width=80, anchor="center")
        self.tree.column("understaffing", width=150, anchor="center")
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

        save_button = ttk.Button(button_frame, text="Speichern", command=self.save_order)
        save_button.pack(side="right", padx=5)

        cancel_button = ttk.Button(button_frame, text="Abbrechen", command=self.destroy)
        cancel_button.pack(side="right")

    def load_shifts(self):
        self.shift_list = get_ordered_shift_abbrevs(include_hidden=True)
        self.populate_tree()

    def populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for shift in self.shift_list:
            visible_text = "Ja" if shift.get('is_visible', 1) else "Nein"
            understaffing_text = "Ja" if shift.get('check_for_understaffing', 0) else "Nein"
            self.tree.insert("", "end", values=(shift['name'], shift['abbreviation'], visible_text, understaffing_text),
                             iid=shift['abbreviation'])

    def on_press(self, event):
        self.drag_item = self.tree.identify_row(event.y)

    def on_drag(self, event):
        if self.drag_item:
            tv = event.widget
            moveto_item = tv.identify_row(event.y)
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

        self.tree.move(item_id, '', current_index + direction)

        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

    def toggle_visibility(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        column_id = self.tree.identify_column(event.x)

        for shift in self.shift_list:
            if shift['abbreviation'] == item_id:
                if column_id == "#3":
                    shift['is_visible'] = 1 - shift.get('is_visible', 1)
                elif column_id == "#4":
                    shift['check_for_understaffing'] = 1 - shift.get('check_for_understaffing', 0)
                break
        self.populate_tree()
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)

    def save_order(self):
        new_order_abbrevs = self.tree.get_children()
        final_order_data = []
        for index, abbrev in enumerate(new_order_abbrevs):
            for shift in self.shift_list:
                if shift['abbreviation'] == abbrev:
                    final_order_data.append(
                        (abbrev, index, shift.get('is_visible', 1), shift.get('check_for_understaffing', 0))
                    )
                    break

        success, message = save_shift_order(final_order_data)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            if self.callback:
                self.callback()  # Ruft refresh_all_tabs() im Hauptfenster auf
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)