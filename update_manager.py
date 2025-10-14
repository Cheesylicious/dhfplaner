# update_manager.py
import tkinter as tk
from tkinter import messagebox
import urllib.request
import urllib.error
import os
import sys
import zipfile
import shutil
import time

# Konstante für den User-Agent (wichtig für externe Anfragen)
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36 DHFPlanerClient/1.0'


# --- HILFSFUNKTIONEN FÜR ROBUSTE VERSIONSVERARBEITUNG ---
def _version_to_tuple(version_str):
    version_str = version_str.strip()
    try:
        return tuple(map(int, version_str.split('.')))
    except ValueError:
        return (0,)


def _increment_version(version_str):
    try:
        parts = list(map(int, version_str.split('.')))
        if not parts:
            return "1.0.0"

        last_index = len(parts) - 1
        parts[last_index] += 1
        return ".".join(map(str, parts))
    except Exception:
        return version_str


def load_local_version(path="version.txt"):
    """
    Liest die Versionsnummer aus der version.txt Datei.
    PRIORISIERUNG: 1. Permanenter Ordner (neue Version) 2. PyInstaller Cache.
    """
    try:
        # 1. VERSUCH: Lese aus dem permanenten Installationspfad (wo die update.bat die Datei hinkopiert hat)
        permanent_path = os.path.dirname(sys.executable)
        version_path_perm = os.path.join(permanent_path, path)

        if os.path.exists(version_path_perm):
            with open(version_path_perm, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version

        # 2. FALLBACK: Lese aus dem PyInstaller Temp-Pfad (sys._MEIPASS)
        base_path = getattr(sys, '_MEIPASS', permanent_path)
        version_path_temp = os.path.join(base_path, path)

        with open(version_path_temp, 'r', encoding='utf-8') as f:
            return f.read().strip()

    except Exception as e:
        return "0.0.0"


# --- ENDE HILFSFUNKTIONEN ---

LOCAL_VERSION = load_local_version()


class UpdateManager:
    def __init__(self, master, current_version=LOCAL_VERSION):
        self.master = master
        self.CURRENT_VERSION = current_version
        self.TAG_URL = "https://github.com/Cheesylicious/dhfplaner/releases/tag/"

    def _find_latest_remote_version(self):
        current_version = self.CURRENT_VERSION
        latest_version = current_version
        next_version = _increment_version(current_version)

        while True:
            url_to_check = f"{self.TAG_URL}v{next_version}"
            req = urllib.request.Request(url_to_check, headers={'User-Agent': USER_AGENT})

            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.getcode() == 200:
                        latest_version = next_version
                        next_version = _increment_version(next_version)
                    else:
                        break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    break
                else:
                    break
            except Exception as e:
                break
        return latest_version

    def get_update_status(self):
        remote_version = self._find_latest_remote_version()

        update_available = False
        if remote_version and remote_version != self.CURRENT_VERSION:
            local_v_tuple = _version_to_tuple(self.CURRENT_VERSION)
            remote_v_tuple = _version_to_tuple(remote_version)
            update_available = remote_v_tuple > local_v_tuple

        return self.CURRENT_VERSION, remote_version, update_available

    def check_for_update(self, silent=False):
        current_version, remote_version, update_available = self.get_update_status()

        if update_available:
            if messagebox.askyesno("Update verfügbar",
                                   f"Version {remote_version} ist verfügbar. Ihre Version ist {current_version}.\n\nMöchten Sie das Update jetzt installieren? Das Programm wird danach neu gestartet."):
                self.install_update(remote_version)
        elif not silent:
            messagebox.showinfo("Update", "Ihre Version ist aktuell.", parent=self.master)

    def install_update(self, version):
        """Lädt die ZIP-Datei herunter und startet den externen Update-Prozess."""
        try:
            # 1. SETUP: Pfade definieren
            download_url = f"https://github.com/Cheesylicious/dhfplaner/archive/refs/tags/v{version}.zip"
            base_dir = os.path.dirname(sys.executable)
            temp_dir = os.path.join(base_dir, "temp_update_dir")
            temp_zip_path = os.path.join(base_dir, f"update_{version}.zip")

            updater_bat_path = os.path.join(base_dir, "dhf_updater_temp.bat")

            main_exe_name = os.path.basename(sys.executable)

            # 2. DOWNLOAD & EXTRAKTION
            req = urllib.request.Request(download_url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req) as response, open(temp_zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)

            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            os.remove(temp_zip_path)

            # 3. VORBEREITUNG DER DATEIEN (Inhalt verschieben und version.txt schreiben)
            extracted_folder = os.path.join(temp_dir, os.listdir(temp_dir)[0])
            for item in os.listdir(extracted_folder):
                shutil.move(os.path.join(extracted_folder, item), temp_dir)
            shutil.rmtree(extracted_folder)

            # Schreibe die neue version.txt in den Temp-Ordner
            version_path = os.path.join(temp_dir, "version.txt")
            with open(version_path, 'w', encoding='utf-8') as f:
                f.write(version)

            # 4. ERSTELLEN DES UPDATER-SCRIPTS (Silent Batch Script mit robustem xcopy)

            # WICHTIG: Erhöhung der Wartezeit für Dateisperren
            batch_content = f"""
@echo off
timeout /t 5 /nobreak > nul
:WAIT
tasklist /FI "IMAGENAME eq {main_exe_name}" | find /I "{main_exe_name}" > nul
IF %ERRORLEVEL% EQU 0 (
    timeout /t 1 /nobreak > nul
    GOTO WAIT
)

:: Kopiervorgang (ersetzt nur, wenn die Datei im TEMP-Ordner neuer ist, was immer der Fall ist)
xcopy /s /e /y /q "{temp_dir}\\*" "{base_dir}\\"

IF %ERRORLEVEL% NEQ 0 (
    :: Wenn xcopy fehlschlägt, wird eine Logdatei erstellt.
    ECHO Das Update ist fehlgeschlagen (Errorcode %ERRORLEVEL%). Bitte als Administrator ausführen. > update_error.log
    EXIT /B %ERRORLEVEL%
)

:: Finale Sicherheitspause, um sicherzustellen, dass die Dateien physikalisch geschrieben wurden
timeout /t 1 /nobreak > nul 

:: Cleanup und Neustart
rmdir /s /q "{temp_dir}"
start "" "{os.path.join(base_dir, main_exe_name)}"

:: Lösche dieses Batch-Script
del "%~f0"
"""

            with open(updater_bat_path, 'w') as f:
                f.write(batch_content)

            # 5. NEUSTART: Das Hauptprogramm beenden und den Updater starten
            messagebox.showinfo("Update wird angewandt",
                                "Das Programm wird beendet und das Update wird installiert. Es startet danach automatisch neu.",
                                parent=self.master)

            os.startfile(updater_bat_path)

            sys.exit(0)

        except Exception as e:
            messagebox.showerror("Update Fehler", f"Fehler bei der Update-Vorbereitung {version}: {e}",
                                 parent=self.master)