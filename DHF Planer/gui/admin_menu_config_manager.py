# gui/admin_menu_config_manager.py
import json
import os

CONFIG_FILE = 'admin_menu_config.json'


class AdminMenuConfigManager:
    """Verwaltet die Konfiguration für das Schicht-Auswahlmenü des Admins."""

    @staticmethod
    def load_config(all_shift_abbrevs):
        """
        Lädt die Konfiguration. Stellt sicher, dass alle existierenden Schichtarten
        berücksichtigt werden (standardmäßig sichtbar).
        """
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                config = {}

        # Stelle sicher, dass jede bekannte Schichtart in der Konfiguration ist.
        # Neue Schichten werden standardmäßig als sichtbar (True) hinzugefügt.
        config_updated = False
        for abbrev in all_shift_abbrevs:
            if abbrev not in config:
                config[abbrev] = True
                config_updated = True

        # Speichere die Konfiguration zurück, wenn neue Schichten hinzugefügt wurden.
        if config_updated:
            AdminMenuConfigManager.save_config(config)

        return config

    @staticmethod
    def save_config(config_data):
        """Speichert die Konfiguration in der JSON-Datei."""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)
            return True, "Einstellungen erfolgreich gespeichert."
        except IOError as e:
            return False, f"Fehler beim Speichern der Einstellungen: {e}"