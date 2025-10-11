# gui/request_lock_manager.py
import json
import os
import sys
from datetime import datetime

# Stellt sicher, dass der Pfad zur Sperrdatei immer korrekt ist,
# egal ob das Skript direkt oder als kompilierte Anwendung ausgeführt wird.
if getattr(sys, 'frozen', False):
    # Anwendung wird als .exe ausgeführt
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Anwendung wird als Python-Skript ausgeführt
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

LOCK_FILE = os.path.join(BASE_DIR, 'request_locks.json')


class RequestLockManager:
    @staticmethod
    def is_month_locked(year, month):
        """Überprüft, ob ein bestimmter Monat für Anfragen gesperrt ist."""
        # --- ZUSÄTZLICHES DEBUGGING START ---
        print(f"\n--- PRÜFE SPERRSTATUS ---")
        print(f"Angefragtes Jahr: {year}, Monat: {month}")
        # --- ZUSÄTZLICHES DEBUGGING END ---

        locks = RequestLockManager.load_locks()
        lock_key = f"{year}-{month:02d}"

        # --- ZUSÄTZLICHES DEBUGGING START ---
        print(f"Generierter Schlüssel: '{lock_key}'")
        is_locked = locks.get(lock_key, False)
        print(f"Schlüssel im Wörterbuch gefunden: {lock_key in locks}")
        print(f"Ergebnis der Prüfung (is_locked): {is_locked}")
        print(f"--- PRÜFUNG ABGESCHLOSSEN ---\n")
        # --- ZUSÄTZLICHES DEBUGGING END ---

        return is_locked

    @staticmethod
    def load_locks():
        """Lädt die Sperrkonfiguration aus der JSON-Datei."""
        # print(f"DEBUG: Lade Sperrdatei von: {os.path.abspath(LOCK_FILE)}") # Kann bei Bedarf wieder aktiviert werden

        if not os.path.exists(LOCK_FILE):
            return {}
        try:
            with open(LOCK_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    return {}

                locks_data = json.loads(content)
                # print(f"DEBUG: Inhalt der Datei: {locks_data}") # Kann bei Bedarf wieder aktiviert werden
                return locks_data
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def save_locks(locks):
        """Speichert die Sperrkonfiguration in der JSON-Datei."""
        try:
            with open(LOCK_FILE, 'w', encoding='utf-8') as f:
                json.dump(locks, f, indent=4)
            return True
        except IOError:
            return False