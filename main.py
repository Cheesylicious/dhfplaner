# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox
import os
import sys
import importlib.util


# Helper-Funktion, um Module dynamisch aus dem Dateisystem zu laden.
# Dies zwingt Python, die externen Ordner zu verwenden, und bricht PyInstallers Analyse.
def dynamic_import(module_path, file_name):
    """Lädt ein Modul aus dem Dateisystem, basierend auf dem externen Ordner."""
    # Der Dateipfad ist relativ zum Verzeichnis der .exe, das von app_launcher.py hinzugefügt wird.
    file_path = os.path.join(module_path, file_name + '.py')

    if not os.path.exists(file_path):
        # Wenn die Datei nicht existiert, ist dies der BEWEIS für die erfolgreiche Exklusion!
        raise ModuleNotFoundError(
            f"Das externe Modul '{module_path}.{file_name}' wurde nicht gefunden. Bitte stellen Sie sicher, dass der '{module_path}' Ordner vorhanden ist.")

    # Modul dynamisch laden und in sys.modules eintragen
    spec = importlib.util.spec_from_file_location(module_path + '.' + file_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_path + '.' + file_name] = module
    spec.loader.exec_module(module)
    return module


# Dynamische Imports der Hauptkomponenten
# Diese ersetzen die ursprünglichen statischen Imports:
try:
    db_core_module = dynamic_import('database', 'db_core')
    LoginWindow = dynamic_import('gui', 'login_window').LoginWindow
    MainAdminWindow = dynamic_import('gui', 'main_admin_window').MainAdminWindow
    MainUserWindow = dynamic_import('gui', 'main_user_window').MainUserWindow
    PasswordChangeWindow = dynamic_import('gui', 'password_change_window').PasswordChangeWindow
    # Die Funktion muss auch dynamisch zugewiesen werden
    initialize_db = db_core_module.initialize_db

except ModuleNotFoundError as e:
    # Dies ist der Fehler, den wir sehen wollen, wenn die Ordner fehlen.
    print(
        f"FATALER FEHLER: Programm kann nicht gestartet werden, da externe Moduldatei fehlt oder die Ordnerstruktur beschädigt ist: {e}")
    # Versuche, ein Tkinter-Fenster mit dem Fehler zu zeigen, falls Tkinter geladen wurde
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Startfehler (Update-Struktur)", str(e))
    except:
        pass
    sys.exit(1)


# FERTIGSTELLUNG DES HAUPTSKRIPTS
class App:
    def __init__(self):
        print("[DEBUG] App.__init__: Anwendung wird initialisiert.")
        # initialize_db wird jetzt korrekt über das dynamisch geladene Modul aufgerufen.
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
        # Verwendet die dynamisch geladene Klasse
        LoginWindow(self.root, self)

    def on_login_success(self, calling_window, user_data):
        print(f"[DEBUG] App.on_login_success: Login erfolgreich für {user_data.get('name')}.")
        calling_window.destroy()

        if user_data.get('password_changed') == 0:
            print("[DEBUG] App.on_login_success: Passwort muss geändert werden.")
            self.show_password_change_window(user_data)
        else:
            print("[DEBUG] App.on_login_success: Zeige Hauptfenster.")
            self.show_main_window(user_data)

    def show_password_change_window(self, user_data):
        print("[DEBUG] App.show_password_change_window: Zeige Fenster zur Passwortänderung.")
        # Verwendet die dynamisch geladene Klasse
        PasswordChangeWindow(self.root, user_data, self)

    def on_password_changed(self, calling_window, user_data):
        print("[DEBUG] App.on_password_changed: Passwort geändert, zeige Hauptfenster.")
        calling_window.destroy()
        self.show_main_window(user_data)

    def show_main_window(self, user_data):
        role = user_data.get('role')
        # Verwendet die dynamisch geladenen Klassen
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