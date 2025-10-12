# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from gui.user_edit_window import UserEditWindow
from database.db_users import get_all_users, delete_user
from database.db_admin import get_pending_password_resets_count
from .password_reset_requests_window import PasswordResetRequestsWindow


class UserManagementTab(ttk.Frame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.create_widgets()
        self.load_users()

    def create_widgets(self):
        self.pack(expand=True, fill="both", padx=10, pady=10)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", pady=5)

        self.add_user_button = ttk.Button(button_frame, text="Mitarbeiter hinzufügen", command=self.add_user)
        self.add_user_button.pack(side="left")

        self.edit_user_button = ttk.Button(button_frame, text="Mitarbeiter bearbeiten", command=self.edit_user)
        self.edit_user_button.pack(side="left", padx=5)

        self.delete_user_button = ttk.Button(button_frame, text="Mitarbeiter löschen", command=self.delete_user)
        self.delete_user_button.pack(side="left")

        self.password_reset_button = ttk.Button(button_frame, text="Passwort-Resets", command=self.open_password_resets)
        self.password_reset_button.pack(side="right")
        self.update_password_reset_button()

        self.tree = ttk.Treeview(self, columns=("Vorname", "Name", "Rolle"), show="headings")
        self.tree.heading("Vorname", text="Vorname")
        self.tree.heading("Name", text="Nachname")
        self.tree.heading("Rolle", text="Rolle")
        self.tree.pack(expand=True, fill="both", pady=5)

    def load_users(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.users = get_all_users()
        for user_id, user_data in self.users.items():
            self.tree.insert("", "end", iid=user_id, values=(user_data['vorname'], user_data['name'], user_data['role']))

    def add_user(self):
        allowed_roles = self.controller.get_allowed_roles()
        UserEditWindow(self, user_id=None, user_data=None, callback=self.load_users, is_new=True, allowed_roles=allowed_roles)

    def edit_user(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Fehler", "Bitte wählen Sie einen Mitarbeiter aus.")
            return
        user_id = selected_item[0]
        user_data = self.users[str(user_id)]
        allowed_roles = self.controller.get_allowed_roles()
        UserEditWindow(self, user_id=user_id, user_data=user_data, callback=self.load_users, is_new=False, allowed_roles=allowed_roles)

    def delete_user(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Fehler", "Bitte wählen Sie einen Mitarbeiter aus.")
            return
        user_id = selected_item[0]
        if messagebox.askyesno("Bestätigen", "Möchten Sie diesen Mitarbeiter wirklich löschen?"):
            if delete_user(user_id):
                self.load_users()
            else:
                messagebox.showerror("Fehler", "Fehler beim Löschen des Mitarbeiters.")

    def open_password_resets(self):
        PasswordResetRequestsWindow(self, self.update_password_reset_button)

    def update_password_reset_button(self):
        count = get_pending_password_resets_count()
        if count > 0:
            self.password_reset_button.config(text=f"Passwort-Resets ({count})")
        else:
            self.password_reset_button.config(text="Passwort-Resets")