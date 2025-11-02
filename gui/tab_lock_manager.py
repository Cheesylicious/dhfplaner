# gui/tab_lock_manager.py
from database.db_core import load_config_json, save_config_json


class TabLockManager:
    """Verwaltet die Sichtbarkeit von Tabs für Nicht-Admin-Benutzer (DB-gesteuert)."""

    CONFIG_KEY = 'TAB_LOCKS'
    # Default: Alle Reiter sind NICHT gesperrt (False bedeutet sichtbar)
    DEFAULT_CONFIG = {
        "Schichtplan": False,
        "Meine Anfragen": False,
        "Mein Urlaub": False,
        "Bug-Reports": False,
        "Teilnahmen": False
    }

    @staticmethod
    def load_locks():
        """Lädt die Sperrkonfiguration aus der Datenbank."""
        locks = load_config_json(TabLockManager.CONFIG_KEY)

        # Kombiniere mit Default-Werten, falls DB-Eintrag fehlt
        if locks is None:
            return TabLockManager.DEFAULT_CONFIG.copy()

        # Füge eventuell fehlende Schlüssel aus dem Default hinzu (für zukünftige Updates)
        return {**TabLockManager.DEFAULT_CONFIG, **locks}

    @staticmethod
    def save_locks(locks_data):
        """Speichert die Sperrkonfiguration in der Datenbank."""
        return save_config_json(TabLockManager.CONFIG_KEY, locks_data)

    @staticmethod
    def is_tab_locked(tab_name):
        """Prüft, ob ein bestimmter Reiter für Nicht-Admins gesperrt ist."""
        locks = TabLockManager.load_locks()
        # Gibt True zurück, wenn der Wert für den Tab-Namen in der Konfiguration True ist.
        return locks.get(tab_name, False)