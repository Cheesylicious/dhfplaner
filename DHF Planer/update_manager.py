# update_manager.py
import urllib.request
import os
import zipfile
import shutil
import sys
from tkinter import messagebox

# --- KONFIGURATION ---
# Die aktuelle Version, die im Code enthalten ist. MUSST du nach jedem Update inkrementieren.
CURRENT_VERSION = "1.0.1"

# URL, unter der die Updates und die versions.txt liegen
BASE_URL = "https://raw.githubusercontent.com/Cheesylicious/dhfplaner/refs/heads/main/DHF%20Planer/"


# --- ENDE KONFIGURATION ---


class UpdateManager:
    """Verwaltet die Versionsprüfung, den Download und die Installation von Updates."""

    def __init__(self, master):
        self.master = master
        self.local_version = CURRENT_VERSION

    def _fetch_remote_version(self):
        """Holt die Versionsnummer vom Server."""
        try:
            with urllib.request.urlopen(BASE_URL + "version.txt") as response:
                remote_version = response.read().decode('utf-8').strip()
            return remote_version
        except Exception as e:
            print(f"Fehler beim Abrufen der Remote-Version: {e}")
            return None

    def check_for_update(self, silent=True):
        """Prüft, ob ein Update verfügbar ist."""
        remote_version = self._fetch_remote_version()

        if remote_version is None:
            if not silent:
                messagebox.showerror("Fehler", "Konnte keine Verbindung zum Update-Server herstellen.",
                                     parent=self.master)
            return False

        if remote_version > self.local_version:
            if not silent:
                if messagebox.askyesno("Update verfügbar",
                                       f"Version {remote_version} ist verfügbar. Ihre Version ist {self.local_version}.\n\nMöchten Sie das Update jetzt installieren? Das Programm wird danach neu gestartet.",
                                       parent=self.master):
                    return self.install_update(remote_version)
            else:
                return True  # Update verfügbar (für automatischen Check)

        elif not silent:
            messagebox.showinfo("Update", "Ihre Version ist aktuell.", parent=self.master)

        return False

    def install_update(self, remote_version):
        """Lädt die ZIP-Datei herunter und installiert sie."""
        download_url = BASE_URL + f"update_{remote_version}.zip"
        temp_zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"update_{remote_version}.zip")
        extract_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_update_dir")

        try:
            # 1. Download
            messagebox.showinfo("Download", f"Lade Update {remote_version} herunter...", parent=self.master)
            urllib.request.urlretrieve(download_url, temp_zip_path)

            # 2. Entpacken
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # 3. Dateien ersetzen (Achtung: Dies ist der kritische Teil!)
            # Wir gehen davon aus, dass die ZIP-Datei direkt den Projektordner-Inhalt enthält.
            for root, _, files in os.walk(extract_dir):
                relative_path = os.path.relpath(root, extract_dir)
                target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

                os.makedirs(target_dir, exist_ok=True)

                for file in files:
                    source_file = os.path.join(root, file)
                    target_file = os.path.join(target_dir, file)
                    shutil.move(source_file, target_file)

            # 4. Aufräumen
            shutil.rmtree(extract_dir)
            os.remove(temp_zip_path)

            messagebox.showinfo("Erfolg", "Update installiert. Das Programm wird neu gestartet.", parent=self.master)

            # 5. Neustart des Programms (wichtig, um die neuen PYC-Dateien zu laden)
            os.execl(sys.executable, sys.executable, *sys.argv)

            return True

        except Exception as e:
            # Aufräumen bei Fehler
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)

            messagebox.showerror("Update Fehler", f"Fehler bei der Installation von Update {remote_version}: {e}",
                                 parent=self.master)
            return False