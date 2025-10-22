# gui/admin_menu_config_manager.py
# Entferne unnötige lokale Datei-Importe
from database import db_core  # Importiere db_core


# Die Konstanten json, os und CONFIG_FILE wurden entfernt.


class AdminMenuConfigManager:
    """Verwaltet die Konfiguration für das Schicht-Auswahlmenü des Admins."""

    @staticmethod
    def load_config(all_shift_abbrevs):
        """
        Lädt die Konfiguration aus der Datenbank. Stellt sicher, dass alle existierenden Schichtarten
        berücksichtigt werden (standardmäßig sichtbar).
        """
        # 1. Lade die Konfiguration aus der Datenbank
        config = db_core.load_config_json(db_core.ADMIN_MENU_CONFIG_KEY)
        if not isinstance(config, dict):
            config = {}

        # 2. Stelle sicher, dass jede bekannte Schichtart in der Konfiguration ist.
        # Neue Schichten werden standardmäßig als sichtbar (True) hinzugefügt.
        config_updated = False
        for abbrev in all_shift_abbrevs:
            if abbrev not in config:
                config[abbrev] = True
                config_updated = True

        # 3. Speichere die Konfiguration zurück, wenn neue Schichten hinzugefügt wurden (Datenmigration).
        if config_updated:
            success = db_core.save_config_json(db_core.ADMIN_MENU_CONFIG_KEY, config)
            if not success:
                print("WARNUNG: Konnte die aktualisierte Admin-Menü-Konfiguration nicht in der Datenbank speichern.")

        return config

    @staticmethod
    def save_config(config_data):
        """Speichert die Konfiguration in der Datenbank."""
        # Speichere die Konfiguration in der Datenbank
        success = db_core.save_config_json(db_core.ADMIN_MENU_CONFIG_KEY, config_data)

        if success:
            return True, "Einstellungen erfolgreich gespeichert."
        else:
            return False, "Fehler beim Speichern der Einstellungen in der Datenbank."