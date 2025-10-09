# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from database.db_manager import (
    get_all_users, update_user, create_user_by_admin, delete_user, ROLE_HIERARCHY
)
from gui.column_manager import ColumnManager
from gui.column_settings_window import ColumnSettingsWindow
from gui.user_edit_window import UserEditWindow


class UserManagementTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app  # Referenz auf die MainAdminWindow

        self.column_config = ColumnManager.load_config()
        visible_columns = self.column_config.get('visible', ColumnManager.DEFAULT_VISIBLE)
        all_columns_dict = self.column_config.get('all_columns', {})

        self.user_tree = ttk.Treeview(self, columns=list(all_columns_dict.keys()), show="headings")
        self.user_tree["columns"] = list(all_columns_dict.keys())
        for col_key, col_text in all_columns_dict.items():
            self.user_tree.heading(col_key, text=col_text)
            self.user_tree.column(col_key, width=120, anchor="w")
        self.user_tree["displaycolumns"] = tuple(visible_columns)
        self.user_tree.pack(fill="both", expand=True, side="left")

        user_buttons_frame = ttk.Frame(self, padding="10")
        user_buttons_frame.pack(side="left", fill="y", padx=10)

        ttk.Button(user_buttons_frame, text="Benutzer anlegen...", command=self.create_user).pack(fill="x", pady=5)
        ttk.Button(user_buttons_frame, text="Benutzer bearbeiten...", command=self.edit_user).pack(fill="x", pady=5)
        ttk.Button(user_buttons_frame, text="Benutzer löschen", command=self.delete_selected_user).pack(fill="x",
                                                                                                        pady=5)
        ttk.Separator(user_buttons_frame).pack(fill="x", pady=10)
        ttk.Button(user_buttons_frame, text="Spalten anpassen...", command=self.open_column_settings).pack(fill="x",
                                                                                                           pady=5)

        self.refresh_user_tree()

    def refresh_user_tree(self):
        for item in self.user_tree.get_children():
            self.user_tree.delete(item)

        self.app.user_data_store = get_all_users()
        all_columns = self.user_tree["columns"]
        for user_id, data in self.app.user_data_store.items():
            values_for_all_columns = []
            for col_key in all_columns:
                value = data.get(col_key, "")
                if col_key == 'entry_date' and value:
                    try:
                        value = datetime.strptime(value, '%Y-%m-%d').strftime('%d.%m.%Y')
                    except (ValueError, TypeError):
                        pass
                values_for_all_columns.append(value)
            self.user_tree.insert("", tk.END, values=values_for_all_columns, iid=user_id)

    def refresh_column_display(self):
        """Aktualisiert nur die sichtbaren Spalten, ohne die Daten neu zu laden."""
        self.column_config = ColumnManager.load_config()
        visible_columns = self.column_config.get('visible', ColumnManager.DEFAULT_VISIBLE)
        self.user_tree["displaycolumns"] = tuple(visible_columns)

    def open_column_settings(self):
        # Als master wird die Haupt-App (Toplevel) übergeben, als callback dieser Tab
        ColumnSettingsWindow(self.app, self)

    def edit_user(self):
        if not self.user_tree.selection():
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Benutzer aus.", parent=self.app)
            return
        selected_id = self.user_tree.selection()[0]
        user_data_to_edit = self.app.user_data_store.get(selected_id)

        is_super_admin = self.app.logged_in_user['role'] == "SuperAdmin"
        if not is_super_admin:
            if str(self.app.logged_in_user['id']) == selected_id:
                messagebox.showerror("Zugriff verweigert",
                                     "Sie können Ihr eigenes Konto nicht über diese Maske bearbeiten.", parent=self.app)
                return
            admin_level = ROLE_HIERARCHY.get(self.app.logged_in_user['role'], 0)
            target_level = ROLE_HIERARCHY.get(user_data_to_edit['role'], 0)
            if admin_level <= target_level:
                messagebox.showerror("Zugriff verweigert",
                                     "Sie können nur Benutzer mit einer niedrigeren Rolle bearbeiten.", parent=self.app)
                return

        if user_data_to_edit:
            UserEditWindow(self.app, selected_id, user_data_to_edit, self.update_user_data, is_new=False,
                           allowed_roles=self.app.get_allowed_roles())
        else:
            messagebox.showerror("Fehler", "Benutzerdaten konnten nicht gefunden werden.", parent=self.app)

    def update_user_data(self, user_id, new_data):
        update_user(user_id, new_data)
        self.app.refresh_all_tabs()

    def create_user(self):
        today_str = datetime.today().strftime('%Y-%m-%d')
        empty_data = {"vorname": "", "name": "", "geburtstag": "", "telefon": "", "diensthund": "", "urlaub_gesamt": 30,
                      "role": "Benutzer", "entry_date": today_str}
        UserEditWindow(self.app, None, empty_data, self.add_new_user, is_new=True,
                       allowed_roles=self.app.get_allowed_roles())

    def add_new_user(self, user_id, new_data):
        success = create_user_by_admin(new_data)
        if success:
            messagebox.showinfo("Erfolg", "Benutzer wurde erfolgreich angelegt.", parent=self.app)
            self.app.refresh_all_tabs()
        else:
            messagebox.showerror("Fehler", "Ein Benutzer mit diesem Namen existiert bereits.", parent=self.app)

    def delete_selected_user(self):
        if not self.user_tree.selection():
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Benutzer aus.", parent=self.app)
            return
        selected_id = self.user_tree.selection()[0]
        user_to_delete = self.app.user_data_store.get(selected_id)

        admin_level = ROLE_HIERARCHY.get(self.app.logged_in_user['role'], 0)
        target_level = ROLE_HIERARCHY.get(user_to_delete['role'], 0)

        if admin_level <= target_level:
            messagebox.showerror("Zugriff verweigert",
                                 "Sie können keine Benutzer mit gleicher oder höherer Rolle löschen.", parent=self.app)
            return

        full_name = f"{user_to_delete['vorname']} {user_to_delete['name']}"
        if messagebox.askyesno("Bestätigen", f"Möchten Sie den Benutzer {full_name} wirklich endgültig löschen?",
                               parent=self.app):
            if delete_user(selected_id):
                messagebox.showinfo("Erfolg", "Benutzer wurde gelöscht.", parent=self.app)
                self.app.refresh_all_tabs()
            else:
                messagebox.showerror("Fehler", "Der Benutzer konnte nicht gelöscht werden.", parent=self.app)