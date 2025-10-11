# gui/tab_lock_manager.py
import json
import os
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

LOCK_FILE = os.path.join(BASE_DIR, 'tab_locks.json')

class TabLockManager:
    @staticmethod
    def load_tab_locks():
        """Lädt die Konfiguration für gesperrte Tabs oder gibt ein leeres Dictionary zurück."""
        if not os.path.exists(LOCK_FILE):
            return {}
        try:
            with open(LOCK_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def save_tab_locks(locks_data):
        """Speichert die Konfiguration für gesperrte Tabs."""
        try:
            with open(LOCK_FILE, 'w', encoding='utf-8') as f:
                json.dump(locks_data, f, indent=4)
            return True
        except IOError:
            return False

    @staticmethod
    def is_tab_locked(tab_name):
        """Überprüft, ob ein bestimmter Reiter für Benutzer gesperrt ist."""
        locks = TabLockManager.load_tab_locks()
        # Wenn der Wert 'False' ist, ist der Tab gesperrt.
        # Standard ist 'True' (nicht gesperrt), falls der Schlüssel nicht existiert.
        return not locks.get(tab_name, True)