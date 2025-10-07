# main.py
import tkinter as tk
from tkinter import messagebox
import locale  # NEU: Import für Spracheinstellungen

# NEU: Setze die Sprache für Zeitformate auf Deutsch
# Das sorgt dafür, dass die Monatsnamen korrekt angezeigt werden.
try:
    locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'German')
    except locale.Error:
        print("Deutsche Lokale konnte nicht gesetzt werden. Monatsnamen könnten auf Englisch sein.")

# Prüfen, ob tkcalendar installiert ist
try:
    from tkcalendar import DateEntry
except ImportError:
    messagebox.showerror(
        "Fehlende Bibliothek",
        "Die Bibliothek 'tkcalendar' wird benötigt.\n\nBitte installieren Sie sie mit dem Befehl:\n\npip install tkcalendar"
    )
    exit()

from gui.login_window import LoginWindow
from gui.main_user_window import MainUserWindow
from gui.main_admin_window import MainAdminWindow
from database.db_manager import initialize_db


class Application(tk.Tk):
    """Die Hauptklasse, die die Anwendung steuert."""

    def __init__(self):
        super().__init__()
        initialize_db()

        self.withdraw()
        self.login_window = LoginWindow(self, self.on_login_success)
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def on_login_success(self, user_data):
        """Wird aufgerufen, wenn der Login erfolgreich war."""
        if self.login_window:
            self.login_window.destroy()
            self.login_window = None

        if user_data["role"] == "SuperAdmin":
            MainAdminWindow(self, user_data)
        else:
            MainUserWindow(self, user_data)

    def on_app_close(self):
        """Beendet die Anwendung sauber."""
        if messagebox.askokcancel("Beenden", "Möchten Sie das Programm wirklich beenden?"):
            self.destroy()


if __name__ == "__main__":
    app = Application()
    app.mainloop()