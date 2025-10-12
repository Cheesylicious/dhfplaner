# main.py
import tkinter as tk
from tkinter import messagebox
from gui.login_window import LoginWindow
from gui.main_admin_window import MainAdminWindow
from gui.main_user_window import MainUserWindow
from database.db_core import initialize_db
from database.db_users import set_user_tutorial_seen

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        initialize_db()

        self.login_window = LoginWindow(self, self.on_login_success)
        self.current_main_window = None
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def on_login_success(self, user_data):
        self.login_window.withdraw()

        if self.current_main_window:
            self.current_main_window.destroy()

        if user_data['role'] in ["Admin", "SuperAdmin"]:
            self.current_main_window = MainAdminWindow(self, user_data)
        else:
            self.current_main_window = MainUserWindow(self, user_data)

        if user_data.get('has_seen_tutorial', 0) == 0 and 'show_tutorial' in dir(self.current_main_window):
            self.current_main_window.show_tutorial()
            set_user_tutorial_seen(user_data['id'])
            self.current_main_window.user_data['has_seen_tutorial'] = 1

    def on_app_close(self):
        if messagebox.askokcancel("Beenden", "Möchten Sie die Anwendung wirklich beenden?"):
            self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()