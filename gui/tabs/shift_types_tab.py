# gui/tabs/shift_types_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_shifts import get_all_shift_types, add_shift_type, update_shift_type, delete_shift_type
from gui.dialogs.shift_type_dialog import ShiftTypeDialog


class ShiftTypesTab(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.app = master
        self.callback = callback
        self.title("Schichtarten verwalten")
        self.geometry("1000x600")

        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill='both', padx=10, pady=10)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=5)

        ttk.Button(button_frame, text="Neue Schichtart", command=self.add_new_shift_type).pack(side='left')
        ttk.Button(button_frame, text="Schichtart bearbeiten", command=self.edit_shift_type).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Schichtart löschen", command=self.delete_shift_type).pack(side='left')

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(expand=True, fill='both')

        self.tree = ttk.Treeview(tree_frame, columns=(
        'name', 'abbreviation', 'start_time', 'end_time', 'hours', 'color', 'check_understaffing'), show='headings')
        self.tree.heading('name', text='Name')
        self.tree.heading('abbreviation', text='Abkürzung')
        self.tree.heading('start_time', text='Startzeit')
        self.tree.heading('end_time', text='Endzeit')
        self.tree.heading('hours', text='Stunden')
        self.tree.heading('color', text='Farbe')
        self.tree.heading('check_understaffing', text='Prüfen auf Unterbesetzung')

        self.tree.column('name', width=200)
        self.tree.column('abbreviation', width=100)
        self.tree.column('start_time', width=100)
        self.tree.column('end_time', width=100)
        self.tree.column('hours', width=80)
        self.tree.column('color', width=100)
        self.tree.column('check_understaffing', width=180)

        self.tree.pack(expand=True, fill='both')
        self.load_shift_types()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.callback()
        self.destroy()

    def load_shift_types(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        shift_types = get_all_shift_types()
        for st in shift_types:
            check_understaffing_text = "Ja" if st.get('check_for_understaffing') else "Nein"
            self.tree.insert('', 'end', values=(
            st['name'], st['abbreviation'], st['start_time'], st['end_time'], st['hours'], st['color'],
            check_understaffing_text), iid=st['id'])

    def add_new_shift_type(self):
        dialog = ShiftTypeDialog(self, self.app, is_new=True)
        self.wait_window(dialog)
        if dialog.result:
            add_shift_type(dialog.result)
            self.load_shift_types()
            self.app.load_shift_types()

    def edit_shift_type(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Bearbeiten aus.", parent=self)
            return

        shift_id = selected_item[0]
        item_values = self.tree.item(shift_id)['values']

        check_understaffing = True if item_values[6] == "Ja" else False

        shift_data = {
            'id': shift_id,
            'name': item_values[0],
            'abbreviation': item_values[1],
            'start_time': item_values[2],
            'end_time': item_values[3],
            'hours': item_values[4],
            'color': item_values[5],
            'check_for_understaffing': check_understaffing
        }

        dialog = ShiftTypeDialog(self, self.app, is_new=False, initial_data=shift_data)
        self.wait_window(dialog)

        if dialog.result:
            shift_id_to_update = dialog.result.pop('id')
            update_shift_type(shift_id_to_update, dialog.result)
            self.load_shift_types()
            self.app.load_shift_types()

    def delete_shift_type(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Löschen aus.", parent=self)
            return
        shift_id = selected_item[0]
        if messagebox.askyesno("Löschen bestätigen", "Sind Sie sicher, dass Sie diese Schichtart löschen möchten?",
                               parent=self):
            delete_shift_type(shift_id)
            self.load_shift_types()
            self.app.load_shift_types()