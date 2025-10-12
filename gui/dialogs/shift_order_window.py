# gui/dialogs/shift_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
# Hier ist die Korrektur: db_manager wurde zu db_shifts
from database.db_shifts import get_ordered_shift_abbrevs, save_shift_order


class ShiftOrderWindow(tk.Toplevel):
    def __init__(self, parent, include_hidden=False):
        super().__init__(parent)
        self.title("Schicht-Reihenfolge und Sichtbarkeit anpassen")
        self.parent = parent
        self.include_hidden = include_hidden
        self.geometry("600x500")

        self.shift_list = []

        self.create_widgets()
        self.load_shifts()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(main_frame, columns=("name", "abbreviation", "visible", "understaffing"),
                                 show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("abbreviation", text="Abk.")
        self.tree.heading("visible", text="Sichtbar")
        self.tree.heading("understaffing", text="Unterbesetzung prüfen")

        self.tree.column("name", width=200)
        self.tree.column("abbreviation", width=50, anchor="center")
        self.tree.column("visible", width=80, anchor="center")
        self.tree.column("understaffing", width=150, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True)

        # Scrollbar hinzufügen
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Binden der Drag-and-Drop-Events
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
        self.shift_list = get_ordered_shift_abbrevs(include_hidden=self.include_hidden)
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
                tv.move(self.drag_item, '', tv.index(moveto_item))

    def on_release(self, event):
        self.drag_item = None

    def toggle_visibility(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        column_id = self.tree.identify_column(event.x)

        for shift in self.shift_list:
            if shift['abbreviation'] == item_id:
                if column_id == "#3":  # Spalte "Sichtbar"
                    shift['is_visible'] = 1 - shift.get('is_visible', 1)
                elif column_id == "#4":  # Spalte "Unterbesetzung prüfen"
                    shift['check_for_understaffing'] = 1 - shift.get('check_for_understaffing', 0)
                break
        self.populate_tree()

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
            if hasattr(self.parent, 'refresh_data'):
                self.parent.refresh_data()
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)