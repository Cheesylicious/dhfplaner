# boot_loader.py
import runpy
import os
import sys
import traceback
import time

# Eine einfache Log-Funktion, die in eine Datei schreibt
def log_to_file(message):
    try:
        # Wir stellen sicher, dass der Log im Verzeichnis der EXE landet
        log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else '.'
        with open(os.path.join(log_dir, "debug.log"), "a", encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except:
        pass

log_to_file("--- Bootloader gestartet ---")

try:
    bundle_dir = '.'
    # Prüfen, ob wir als PyInstaller-Bundle laufen
    if getattr(sys, 'frozen', False):
        log_to_file("Anwendung läuft als PyInstaller-Bundle.")
        # Den Pfad zum Ordner der .exe ermitteln
        bundle_dir = os.path.dirname(sys.executable)
        log_to_file(f"Bundle-Verzeichnis: {bundle_dir}")

        # Das aktuelle Arbeitsverzeichnis auf diesen Ordner setzen
        os.chdir(bundle_dir)
        log_to_file(f"Arbeitsverzeichnis geändert auf: {os.getcwd()}")
    else:
        log_to_file("Anwendung läuft als normales Python-Skript.")

    # **DIE WICHTIGE ÄNDERUNG: Absoluten Pfad zu main.py erstellen**
    main_py_path = os.path.join(bundle_dir, "main.py")
    log_to_file(f"Absoluter Pfad zu main.py wird sein: {main_py_path}")

    if not os.path.exists(main_py_path):
        log_to_file("FEHLER: main.py wurde unter dem erwarteten Pfad nicht gefunden!")
        raise FileNotFoundError(f"main.py nicht gefunden unter: {main_py_path}")

    log_to_file(f"Versuche, '{main_py_path}' zu starten...")
    # Starte die EXTERNE main.py über ihren absoluten Pfad
    runpy.run_path(main_py_path, run_name="__main__")
    log_to_file("runpy.run_path('main.py') erfolgreich ausgeführt.")

except Exception as e:
    # JEDEN Fehler abfangen, in die Log-Datei schreiben und auf dem Bildschirm anzeigen
    error_message = f"FATALER FEHLER IM BOOTLOADER:\n{traceback.format_exc()}"
    print(error_message)
    log_to_file(error_message)
    # Gib dem Benutzer Zeit, den Fehler zu lesen
    print("\nFenster schließt sich in 15 Sekunden...")
    time.sleep(15)
    sys.exit(1)

log_to_file("--- Bootloader erfolgreich beendet ---")