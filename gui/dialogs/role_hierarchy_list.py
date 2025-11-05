# gui/dialogs/role_hierarchy_list.py
import tkinter as tk
from tkinter import ttk


class RoleHierarchyList(tk.Frame):
    """
    Ein Listbox-Widget, das Drag-and-Drop-Sortierung
    für die Rollen-Hierarchie ermöglicht.
    """

    def __init__(self, master):
        super().__init__(master, borderwidth=1, relief="sunken")

        self.listbox = tk.Listbox(self, selectmode=tk.SINGLE, exportselection=False)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox.config(yscrollcommand=scrollbar.set)

        self.listbox.bind("<Button-1>", self.on_press)
        self.listbox.bind("<B1-Motion>", self.on_drag)
        self.listbox.bind("<ButtonRelease-1>", self.on_release)

        self.drag_start_index = None
        self.roles_data = []  # Speichert die vollen dicts {'id': 1, 'name': 'Admin', ...}

    def on_press(self, event):
        self.drag_start_index = self.listbox.nearest(event.y)

    def on_drag(self, event):
        if self.drag_start_index is None:
            return

        current_index = self.listbox.nearest(event.y)

        if current_index != self.drag_start_index:
            # Item im Listbox-Display verschieben
            item_text = self.listbox.get(self.drag_start_index)
            self.listbox.delete(self.drag_start_index)
            self.listbox.insert(current_index, item_text)

            # Zugehörige Daten in self.roles_data verschieben (wichtig!)
            data_item = self.roles_data.pop(self.drag_start_index)
            self.roles_data.insert(current_index, data_item)

            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(current_index)
            self.listbox.activate(current_index)
            self.drag_start_index = current_index

    def on_release(self, event):
        self.drag_start_index = None

    def populate(self, roles_data_list):
        """
        Füllt die Liste mit Rollen, sortiert nach 'hierarchy_level'.
        """
        self.listbox.delete(0, tk.END)

        # Sortiere die Daten nach 'hierarchy_level'
        # (Standard 99, falls 'hierarchy_level' fehlt)
        self.roles_data = sorted(
            roles_data_list,
            key=lambda r: r.get('hierarchy_level', 99)
        )

        for role in self.roles_data:
            self.listbox.insert(tk.END, role['name'])

    def get_selected_role_data(self):
        """
        Gibt das Daten-Dictionary der aktuell ausgewählten Rolle zurück.
        """
        try:
            selected_index = self.listbox.curselection()[0]
            return self.roles_data[selected_index]
        except IndexError:
            return None

    def get_ordered_data(self):
        """
        Gibt die Liste der Rollen-Daten in der aktuell angezeigten Reihenfolge zurück.
        """
        return self.roles_data

    def bind_selection_changed(self, callback):
        """Bindet ein Event an die Änderung der Listbox-Auswahl."""
        self.listbox.bind("<<ListboxSelect>>", callback)

    def set_selection(self, role_id):
        """Wählt eine Rolle anhand ihrer ID aus."""
        for i, role in enumerate(self.roles_data):
            if role['id'] == role_id:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.activate(i)
                self.listbox.see(i)
                break