# gui/request_config_manager.py
from database.db_core import load_config_json, save_config_json


class RequestConfigManager:
    """Verwaltet zentrale Einstellungen für Wunschanfragen und Urlaub (DB-gesteuert)."""

    CONFIG_KEY = 'REQUEST_CONFIG'
    DEFAULT_CONFIG = {
        "max_wunschfrei_days": 3,
        "wunschfrei_advance_months": 2,
        "max_vacation_advance_months": 12
    }

    @staticmethod
    def load_config():
        """Lädt die Konfiguration aus der Datenbank."""
        config = load_config_json(RequestConfigManager.CONFIG_KEY)

        # Kombiniere mit Default-Werten, falls DB-Eintrag fehlt
        if config is None:
            return RequestConfigManager.DEFAULT_CONFIG.copy()

        return {**RequestConfigManager.DEFAULT_CONFIG, **config}

    @staticmethod
    def save_config(config_data):
        """Speichert die Konfiguration in der Datenbank."""
        return save_config_json(RequestConfigManager.CONFIG_KEY, config_data)