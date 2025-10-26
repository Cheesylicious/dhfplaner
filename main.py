# main.py
import tkinter as tk
from tkinter import messagebox
# Importe hier entfernt (nach innen verschoben)
import sys
import os

# WICHTIG: Stellt sicher, dass das Arbeitsverzeichnis das Verzeichnis dieser Datei ist.
# Das behebt Probleme mit relativen Pfaden (wie 'gui/assets/...')
try:
    # PyInstaller erstellt einen temporären Ordner und speichert den Pfad in _MEIPASS
    base_path = sys._MEIPASS
except Exception:
    # Im normalen Entwicklungsmodus
    base_path = os.path.abspath(os.path.dirname(__file__))

# Ändere das Arbeitsverzeichnis
try:
    os.chdir(base_path)
    print(f"[DEBUG] Arbeitsverzeichnis geändert zu: {base_path}")
except Exception as e:
    print(f"[DEBUG] Konnte Arbeitsverzeichnis nicht ändern: {e}")


def main():
    try:
        # --- KORREKTUR: Importe hierher verschoben ---
        # Importiert die Haupt-Anwendungsklasse
        from boot_loader import Application
        # -------------------------------------------

        # 1. Erstelle die Anwendungs-Instanz
        #    Die Application-Klasse (im boot_loader) erstellt jetzt das 'root'-Fenster
        print("[DEBUG] main.py: Erstelle Application()...")
        app = Application()

        # 2. Starte die Anwendung.
        #    app.run() kümmert sich um alles (DB-Check, Login-Fenster, Mainloop)
        print("[DEBUG] main.py: Starte app.run()...")
        app.run()

    except Exception as e:
        print(f"KRITISCHER FEHLER BEIM START: {e}")
        # Fallback-Nachricht, falls die App crasht, bevor TK läuft
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Kritischer Startfehler",
                                 f"Ein unerwarteter Fehler ist aufgetreten:\n{e}\n"
                                 "Die Anwendung wird beendet.")
            root.destroy()
        except:
            pass  # Wenn selbst das fehlschlägt, ist alles verloren
        sys.exit(1)


if __name__ == "__main__":
    main()