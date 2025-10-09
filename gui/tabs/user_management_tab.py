# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_manager import get_all_users, delete_user, ROLE_HIERARCHY
from gui.user_edit_window import UserEditWindow


class UserManagementTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.selected_user_id = None
        self.setup_ui()
        self.load_users()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill='both')

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=5)
        ttk.Button(button_frame, text="Neuer Mitarbeiter", command=self.create_user).pack(side='left')
        ttk.Button(button_frame, text="Mitarbeiter bearbeiten", command=self.edit_user).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Mitarbeiter löschen", command=self.delete_selected_user).pack(side='left')

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(expand=True, fill='both')

        self.tree = ttk.Treeview(tree_frame, columns=('vorname', 'name', 'role', 'diensthund'), show='headings')
        self.tree.heading('vorname', text='Vorname')
        self.tree.heading('name', text='Nachname')
        self.tree.heading('role', text='Rolle')
        self.tree.heading('diensthund', text='Diensthund')
        self.tree.pack(side='left', expand=True, fill='both')

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

    def load_users(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        users_dict = get_all_users()
        for user_id, user_data in users_dict.items():
            self.tree.insert('', 'end', iid=user_id, values=(
                user_data['vorname'], user_data['name'], user_data['role'], user_data.get('diensthund', '')))

    def edit_user(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Mitarbeiter zum Bearbeiten aus.")
            return
        self.selected_user_id = selected_items[0]
        users = get_all_users()
        user_data = users.get(self.selected_user_id)
        if not user_data:
            messagebox.showerror("Fehler", "Benutzerdaten konnten nicht geladen werden.")
            return

        is_super_admin = self.app.user_data['role'] == "SuperAdmin"

        UserEditWindow(self, self.app, user_data, is_super_admin, self.app.get_allowed_roles(), self.refresh_data)

    def create_user(self):
        UserEditWindow(self, self.app, None, True, self.app.get_allowed_roles(), self.refresh_data)

    def delete_selected_user(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Mitarbeiter zum Löschen aus.")
            return

        user_to_delete_id = selected_items[0]
        users = get_all_users()
        user_to_delete_data = users.get(user_to_delete_id)

        if not user_to_delete_data:
            messagebox.showerror("Fehler", "Benutzer nicht gefunden.")
            return

        admin_level = ROLE_HIERARCHY.get(self.app.user_data['role'], 0)
        user_level = ROLE_HIERARCHY.get(user_to_delete_data['role'], 0)

        if admin_level <= user_level:
            messagebox.showerror("Keine Berechtigung",
                                 "Sie können keine Benutzer mit gleicher oder höherer Rolle löschen.")
            return

        if messagebox.askyesno("Löschen bestätigen",
                               f"Sind Sie sicher, dass Sie {user_to_delete_data['vorname']} {user_to_delete_data['name']} löschen möchten?"):
            if delete_user(user_to_delete_id):
                messagebox.showinfo("Erfolg", "Mitarbeiter erfolgreich gelöscht.")
                self.load_users()
            else:
                messagebox.showerror("Fehler", "Mitarbeiter konnte nicht gelöscht werden.")

    def refresh_data(self):
        self.load_users()
        if self.app and hasattr(self.app, 'refresh_all_tabs'):
            self.app.refresh_all_tabs()