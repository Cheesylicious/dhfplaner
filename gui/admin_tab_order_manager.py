# gui/admin_tab_order_manager.py
from database.db_core import load_config_json, save_config_json, ADMIN_TAB_ORDER_CONFIG_KEY


class AdminTabOrderManager:
    """Verwaltet die Reihenfolge der Reiter im Admin-Fenster (DB-gesteuert)."""

    CONFIG_KEY = ADMIN_TAB_ORDER_CONFIG_KEY

    # Standardreihenfolge der Admin-Tabs
    DEFAULT_ORDER = [
        "Schichtplan", "Offene Anfragen", "Urlaubsanträge",
        "Benutzerverwaltung", "Diensthunde", "Schichtarten", "Protokoll",
        "Reiter-Sperrung", "Einstellungen"  # (Annahme: diese sind vollständig)
    ]

    @staticmethod
    def load_order():
        """Lädt die Tab-Reihenfolge aus der Datenbank."""
        config = load_config_json(AdminTabOrderManager.CONFIG_KEY)

        if config is None or not isinstance(config, dict) or 'order' not in config:
            return AdminTabOrderManager.DEFAULT_ORDER.copy()

        loaded_order = config.get('order', [])

        # Bereinigung und Hinzufügen neuer Standard-Tabs
        final_order = [tab for tab in loaded_order if tab in AdminTabOrderManager.DEFAULT_ORDER]

        for default_tab in AdminTabOrderManager.DEFAULT_ORDER:
            if default_tab not in final_order:
                final_order.append(default_tab)

        return final_order

    @staticmethod
    def save_order(tab_list):
        """Speichert die Tab-Reihenfolge in der Datenbank."""
        data = {'order': tab_list}
        return save_config_json(AdminTabOrderManager.CONFIG_KEY, data)