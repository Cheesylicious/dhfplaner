# gui/tabs/shift_types_tab.py
import tkinter as tk
from tkinter import ttk, messagebox

from database.db_manager import get_all_shift_types, add_shift_type, update_shift_type, delete_shift_type
from gui.dialogs.shift_type_dialog import ShiftTypeDialog


class ShiftTypesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True)
        ttk.Label(main_frame, text="Hier können Sie alle verfügbaren Schichtarten definieren.",
                  font=("Segoe UI", 12, "italic")).pack(pady=(10, 20), anchor="w")

        columns = ("id", "name", "abbreviation", "hours", "start_time", "end_time", "description", "color")
        self.shift_tree = ttk.Treeview(main_frame, columns=columns, show="headings")
        self.shift_tree.column("id", width=0, stretch=tk.NO)
        self.shift_tree.heading("name", text="Art")
        self.shift_tree.heading("abbreviation", text="Abkürzung")
        self.shift_tree.heading("hours", text="Std.")
        self.shift_tree.heading("start_time", text="Start")
        self.shift_tree.heading("end_time", text="Ende")
        self.shift_tree.heading("description", text="Beschreibung")
        self.shift_tree.heading("color", text="Farbe (Hex)")

        self.shift_tree.column("name", width=150, anchor="w")
        self.shift_tree.column("abbreviation", width=80, anchor="center")
        self.shift_tree.column("hours", width=60, anchor="center")
        self.shift_tree.column("start_time", width=70, anchor="center")
        self.shift_tree.column("end_time", width=70, anchor="center")
        self.shift_tree.column("description", width=250, anchor="w")
        self.shift_tree.column("color", width=100, anchor="center")
        self.shift_tree.pack(fill="both", expand=True, pady=(0, 10))
        self.shift_tree.bind('<Double-1>', self.edit_selected_shift_type)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(button_frame, text="+ Hinzufügen", command=self.add_new_shift_type).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Bearbeiten", command=self.edit_selected_shift_type).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Löschen", command=self.delete_selected_shift_type).pack(side="left", padx=5)

        self.refresh_shift_type_tree()

    def refresh_shift_type_tree(self):
        for item in self.shift_tree.get_children():
            self.shift_tree.delete(item)
        shift_types = get_all_shift_types()
        for st in shift_types:
            values = (
                st['id'], st['name'], st['abbreviation'], st['hours'],
                st.get('start_time', ''), st.get('end_time', ''),
                st['description'], st['color']
            )
            self.shift_tree.insert("", tk.END, iid=str(st['id']), values=values, tags=(st['color'],))
            self.shift_tree.tag_configure(st['color'], background=st['color'],
                                          foreground=self.app.get_contrast_color(st['color']))

    def handle_shift_type_dialog_result(self, data, shift_type_id=None):
        if not data: return
        if shift_type_id is None:
            success, message = add_shift_type(data)
        else:
            success, message = update_shift_type(shift_type_id, data)

        if success:
            action = "hinzugefügt" if shift_type_id is None else "aktualisiert"
            messagebox.showinfo("Erfolg", f"Schichtart erfolgreich {action}.", parent=self.app)
            self.app.load_shift_types()  # Lädt neu und aktualisiert alle abhängigen Tabs
            self.refresh_shift_type_tree()
        else:
            messagebox.showerror("Fehler", message, parent=self.app)

    def add_new_shift_type(self):
        ShiftTypeDialog(self.app, self.handle_shift_type_dialog_result, is_new=True)

    def edit_selected_shift_type(self, event=None):
        selection = self.shift_tree.selection()
        if not selection:
            if event: return
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Bearbeiten aus.",
                                   parent=self.app)
            return
        shift_type_id = int(selection[0])

        shift_abbrev = self.shift_tree.item(shift_type_id, 'values')[2]
        initial_data = self.app.shift_types_data.get(shift_abbrev)
        if not initial_data:
            messagebox.showerror("Fehler", "Daten für diese Schichtart konnten nicht geladen werden.", parent=self.app)
            return
        initial_data['id'] = shift_type_id

        ShiftTypeDialog(self.app, self.handle_shift_type_dialog_result, is_new=False, initial_data=initial_data)

    def delete_selected_shift_type(self):
        selection = self.shift_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Löschen aus.",
                                   parent=self.app)
            return
        shift_type_id = int(selection[0])
        name = self.shift_tree.item(shift_type_id, 'values')[1]
        if messagebox.askyesno("Bestätigen", f"Möchten Sie die Schichtart '{name}' wirklich löschen?", parent=self.app,
                               icon='warning'):
            success, message = delete_shift_type(shift_type_id)
            if success:
                self.app.load_shift_types()
                self.refresh_shift_type_tree()
            else:
                messagebox.showerror("Fehler", message, parent=self.app)