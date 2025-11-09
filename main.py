# main.py
import tkinter as tk
from tkinter import messagebox
import sv_ttk
import sys
import os
import threading  # Neu: Für das parallele Laden

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

# --- NEUE IMPORTE ---
from gui.splash_screen import SplashScreen
from boot_loader import Application

# --------------------

# Konstante für die minimale Anzeigezeit des Splash-Screens (in Millisekunden)
MIN_SPLASH_TIME_MS = 5000


def main():
    """
    Haupt-Startroutine der Anwendung.
    Erstellt das root-Fenster, zeigt den Splash-Screen, startet das
    parallele Vorladen der Daten und zeigt nach einer festen Zeit
    das Login-Fenster an.
    """
    root = None  # Definieren, damit es im except-Block verfügbar ist
    splash = None

    try:
        # 1. Erstelle das Hauptfenster (root) und verstecke es sofort.
        #    Das root-Fenster ist unsichtbar, dient aber als Master für alle
        #    folgenden Fenster (Splash und Login).
        root = tk.Tk()
        root.withdraw()
        print("[DEBUG] main.py: Hauptfenster (root) erstellt und versteckt.")

        # 2. Setze das moderne Theme (sv_ttk)
        try:
            sv_ttk.set_theme("dark")
            print("[DEBUG] sv_ttk Theme 'dark' erfolgreich gesetzt.")
        except Exception as e:
            print(f"[WARNUNG] sv_ttk Theme konnte nicht gesetzt werden: {e}")

        # 3. Zeige den Splash-Screen an
        #    Wir müssen root.update() aufrufen, damit das Fenster existiert,
        #    bevor der Splash-Screen es als Master verwendet.
        root.update_idletasks()
        splash = SplashScreen(root)
        print("[DEBUG] main.py: Splash-Screen wird angezeigt.")
        root.update()  # Erzwingt das sofortige Zeichnen des Splash-Screens

        # 4. Initialisiere die Hauptanwendung (Application-Klasse)
        #    WICHTIG: Wir übergeben 'root' an die Application-Klasse.
        #    Die __init__ von Application muss angepasst werden, um 'root'
        #    entgegenzunehmen und darf NICHTS langsames tun (kein Preloading).
        print("[DEBUG] main.py: Erstelle Application(root)...")
        app = Application(root)
        print("[DEBUG] main.py: Application-Instanz erstellt.")

        # 5. Starte das Daten-Vorladen in einem separaten Thread (Regel 2)
        #    Wir rufen eine (neue) Methode in 'Application' auf,
        #    die den Lade-Thread startet.
        print("[DEBUG] main.py: Starte Preloading-Thread...")
        # (Diese Methode muss in boot_loader.py implementiert werden)
        app.start_data_preloading_thread()
        print("[DEBUG] main.py: Preloading-Thread gestartet.")

        # 6. Definiere die Funktion, die nach dem Timer ausgeführt wird
        def show_app_after_delay():
            """
            Wird nach MIN_SPLASH_TIME_MS aufgerufen.
            Schließt den Splash-Screen und zeigt das Login-Fenster.
            """
            print(f"[DEBUG] main.py: {MIN_SPLASH_TIME_MS}ms Timer abgelaufen.")

            if splash:
                splash.close_splash()
                print("[DEBUG] main.py: Splash-Screen geschlossen.")

            # Zeige das Login-Fenster.
            # (Diese Methode muss in boot_loader.py implementiert werden)
            app.show_login_window()
            print("[DEBUG] main.py: Login-Fenster angezeigt.")

        # 7. Starte den Timer
        #    Nach 3000ms wird show_app_after_delay() im Haupt-Thread
        #    ausgeführt, garantiert.
        root.after(MIN_SPLASH_TIME_MS, show_app_after_delay)

        # 8. Starte die Haupt-Event-Schleife (mainloop)
        #    Diese blockiert nun und wartet auf Events (wie den Timer).
        print("[DEBUG] main.py: Starte root.mainloop()...")
        root.mainloop()

    except Exception as e:
        print(f"KRITISCHER FEHLER BEIM START: {e}")
        # Fallback-Nachricht, falls die App crasht
        try:
            if splash:
                splash.destroy()  # Sicherstellen, dass der Splash weg ist
            if root is None:
                root = tk.Tk()
                root.withdraw()
            messagebox.showerror("Kritischer Startfehler",
                                 f"Ein unerwarteter Fehler ist aufgetreten:\n{e}\n"
                                 "Die Anwendung wird beendet.")
            if root:
                root.destroy()
        except:
            pass  # Wenn selbst das fehlschlägt
        sys.exit(1)


if __name__ == "__main__":
    main()