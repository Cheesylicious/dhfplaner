# main.py
import tkinter as tk
from tkinter import messagebox
from database.db_core import initialize_db
from gui.login_window import LoginWindow
from gui.main_admin_window import MainAdminWindow
from gui.main_user_window import MainUserWindow
from gui.password_change_window import PasswordChangeWindow

class App:
    def __init__(self):
        print("[DEBUG] App.__init__: Anwendung wird initialisiert.")
        initialize_db()
        self.root = tk.Tk()
        self.root.withdraw()

    def run(self):
        print("[DEBUG] App.run: Starte Anwendung.")
        self.show_login_window()
        self.root.mainloop()
        print("[DEBUG] App.run: Anwendung wird beendet.")

    def show_login_window(self):
        print("[DEBUG] App.show_login_window: Zeige Login-Fenster an.")
        LoginWindow(self.root, self)

    def on_login_success(self, calling_window, user_data):
        print(f"[DEBUG] App.on_login_success: Login erfolgreich für {user_data['name']}.")
        calling_window.destroy()

        if user_data.get('password_changed') == 0:
            print("[DEBUG] App.on_login_success: Passwort muss geändert werden.")
            self.show_password_change_window(user_data)
        else:
            print("[DEBUG] App.on_login_success: Zeige Hauptfenster.")
            self.show_main_window(user_data)

    def show_password_change_window(self, user_data):
        print("[DEBUG] App.show_password_change_window: Zeige Fenster zur Passwortänderung.")
        PasswordChangeWindow(self.root, user_data, self)

    def on_password_changed(self, calling_window, user_data):
        print("[DEBUG] App.on_password_changed: Passwort geändert, zeige Hauptfenster.")
        calling_window.destroy()
        self.show_main_window(user_data)

    def show_main_window(self, user_data):
        role = user_data.get('role')
        if role in ["Admin", "SuperAdmin"]:
            MainAdminWindow(self.root, user_data, self)
        else:
            MainUserWindow(self.root, user_data, self)

    def on_logout(self, calling_window):
        print("[DEBUG] App.on_logout: Logout empfangen.")
        calling_window.destroy()
        self.show_login_window()

    def on_app_close(self):
        print("[DEBUG] App.on_app_close: Schließe die Anwendung.")
        if messagebox.askokcancel("Beenden", "Möchten Sie das Programm wirklich beenden?"):
            self.root.destroy()

if __name__ == "__main__":
    app = App()
    app.run()