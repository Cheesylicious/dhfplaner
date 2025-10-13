# update_manager.py
import tkinter as tk
from tkinter import messagebox
import urllib.request
import os
import sys
import zipfile
import shutil

class UpdateManager:
    def __init__(self, master, current_version="1.0.0"):
        self.master = master
        self.CURRENT_VERSION = current_version
        # Passe diese URL an dein Repository an!
        self.BASE_URL = "https://raw.githubusercontent.com/Cheesylicious/dhfplaner/main/DHF%20Planer/"

    def _fetch_remote_version(self):
        """Holt die Versionsnummer vom Server."""
        try:
            response = urllib.request.urlopen(self.BASE_URL + "version.txt")
            remote_version = response.read().decode('utf-8').strip()
            return remote_version
        except Exception as e:
            print(f"Fehler beim Abrufen der Remote-Version: {e}")
            return None

    def check_for_update(self, silent=False):
        """Prüft, ob ein Update verfügbar ist."""
        remote_version = self._fetch_remote_version()
        if remote_version and remote_version > self.CURRENT_VERSION:
            if messagebox.askyesno("Update verfügbar", f"Version {remote_version} ist verfügbar. Ihre Version ist {self.CURRENT_VERSION}.\n\nMöchten Sie das Update jetzt installieren? Das Programm wird danach neu gestartet."):
                self.install_update(remote_version)
        elif not silent:
            messagebox.showinfo("Update", "Ihre Version ist aktuell.", parent=self.master)

    def install_update(self, version):
        """Lädt die ZIP-Datei herunter und installiert sie."""
        try:
            download_url = f"https://github.com/Cheesylicious/dhfplaner/archive/refs/tags/v{version}.zip"
            temp_zip_path = os.path.join(os.path.dirname(sys.executable), f"update_{version}.zip")
            extract_dir = os.path.join(os.path.dirname(sys.executable), "temp_update_dir")

            print(f"Lade Update von {download_url} herunter...")
            urllib.request.urlretrieve(download_url, temp_zip_path)

            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            os.makedirs(extract_dir)

            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            os.remove(temp_zip_path)

            # Annahme: Der Inhalt des ZIPs ist in einem Ordner wie "dhfplaner-1.0.1"
            extracted_folder = os.path.join(extract_dir, os.listdir(extract_dir)[0])
            for item in os.listdir(extracted_folder):
                s = os.path.join(extracted_folder, item)
                d = os.path.join(os.path.dirname(sys.executable), item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

            shutil.rmtree(extract_dir)

            messagebox.showinfo("Erfolg", "Update installiert. Das Programm wird neu gestartet.", parent=self.master)
            os.execl(sys.executable, sys.executable, *sys.argv)

        except Exception as e:
            messagebox.showerror("Update Fehler", f"Fehler bei der Installation von Update {version}: {e}", parent=self.master)