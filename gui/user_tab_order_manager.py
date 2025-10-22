# gui/user_tab_order_manager.py
from database.db_core import load_config_json, save_config_json, USER_TAB_ORDER_CONFIG_KEY


class UserTabOrderManager:
    """Verwaltet die Reihenfolge und Sichtbarkeit der Tabs für den Standard-Benutzer (DB-gesteuert)."""

    CONFIG_KEY = USER_TAB_ORDER_CONFIG_KEY

    # Standardreihenfolge der Tabs. Namen müssen mit denen in MainUserWindow übereinstimmen.
    DEFAULT_ORDER = [
        "Schichtplan",
        "Chat",
        "Meine Anfragen",
        "Mein Urlaub",
        "Bug-Reports",
        "Teilnahmen"
    ]

    @staticmethod
    def load_order():
        """Lädt die Tab-Reihenfolge aus der Datenbank."""
        # Config wird als {'order': [Tab1, Tab2, ...]} gespeichert
        config = load_config_json(UserTabOrderManager.CONFIG_KEY)

        if config is None or not isinstance(config, dict) or 'order' not in config:
            # Gib die Standardreihenfolge zurück, falls keine Konfiguration gefunden wird.
            return UserTabOrderManager.DEFAULT_ORDER.copy()

        loaded_order = config.get('order', [])

        # Erstelle die finale Liste basierend auf der gespeicherten Reihenfolge,
        # filtere dabei veraltete/entfernte Tabs heraus.
        final_order = [tab for tab in loaded_order if tab in UserTabOrderManager.DEFAULT_ORDER]

        # Füge alle fehlenden Standard-Tabs am Ende hinzu, um Kompatibilität zu gewährleisten.
        for default_tab in UserTabOrderManager.DEFAULT_ORDER:
            if default_tab not in final_order:
                final_order.append(default_tab)

        return final_order

    @staticmethod
    def save_order(tab_list):
        """Speichert die Tab-Reihenfolge in der Datenbank."""
        data = {'order': tab_list}
        return save_config_json(UserTabOrderManager.CONFIG_KEY, data)