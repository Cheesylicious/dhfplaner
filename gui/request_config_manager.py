# gui/request_config_manager.py
import json
import os

CONFIG_FILE = 'request_config.json'

# Standardkonfiguration, falls die Datei nicht existiert.
# Alle Anfragetypen sind standardmäßig aktiviert.
DEFAULT_CONFIG = {
    "WF": True,   # Wunschfrei
    "T.": True,   # Tagdienst
    "N.": True,   # Nachtdienst
    "6": True,    # 6-Stunden-Dienst
    "24": True    # 24-Stunden-Dienst
}


class RequestConfigManager:
    """Verwaltet die Konfiguration für global verfügbare Benutzeranfragen."""

    @staticmethod
    def load_config():
        """Lädt die Konfiguration aus der JSON-Datei oder gibt die Standardwerte zurück."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                # Bei Fehlern die Standardkonfiguration zurückgeben
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    @staticmethod
    def save_config(config_data):
        """Speichert die Konfiguration in der JSON-Datei."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)
            return True, "Einstellungen erfolgreich gespeichert."
        except IOError as e:
            return False, f"Fehler beim Speichern der Einstellungen: {e}"