# gui/request_lock_manager.py
from datetime import datetime
# Importiere db_core und nutze die bereits vorhandenen DB-Funktionen
from database import db_core

# Die Konstanten BASE_DIR und LOCK_FILE wurden entfernt.


class RequestLockManager:
    @staticmethod
    def is_month_locked(year, month):
        """Überprüft, ob ein bestimmter Monat für Anfragen gesperrt ist."""
        # --- ZUSÄTZLICHES DEBUGGING START ---
        print(f"\n--- PRÜFE SPERRSTATUS (DB) ---")
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
        """Lädt die Sperrkonfiguration aus der Datenbank."""
        # Lade die Konfiguration aus der Datenbank
        locks_data = db_core.load_config_json(db_core.REQUEST_LOCKS_CONFIG_KEY)
        # Stelle sicher, dass immer ein Wörterbuch zurückgegeben wird
        return locks_data if isinstance(locks_data, dict) else {}

    @staticmethod
    def save_locks(locks):
        """Speichert die Sperrkonfiguration in der Datenbank."""
        # Speichere die Konfiguration in der Datenbank
        return db_core.save_config_json(db_core.REQUEST_LOCKS_CONFIG_KEY, locks)