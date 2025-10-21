# boot_loader.py
import runpy
import os
import sys

# Prüfen, ob wir als PyInstaller-Bundle laufen
if getattr(sys, 'frozen', False):
    # Den Pfad zum Ordner der .exe ermitteln
    bundle_dir = os.path.dirname(sys.executable)

    # Das aktuelle Arbeitsverzeichnis auf diesen Ordner setzen
    os.chdir(bundle_dir)

    # Den Ordner zum Python-Suchpfad hinzufügen, damit 'import gui' funktioniert
    if bundle_dir not in sys.path:
        sys.path.append(bundle_dir)

try:
    # Starte die EXTERNE main.py
    runpy.run_path("main.py", run_name="__main__")
except Exception:
    # Wir lassen die Konsole für den nächsten Test an, um Fehler zu sehen
    sys.exit(1)