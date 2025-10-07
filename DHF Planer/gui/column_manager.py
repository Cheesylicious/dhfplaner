# gui/column_manager.py
import json
import os

CONFIG_FILE = 'user_columns_config.json'


class ColumnManager:
    CORE_COLUMNS = {
        "vorname": "Vorname",
        "name": "Name",
        "role": "Rolle",
    }

    DEFAULT_COLUMNS = {
        "vorname": "Vorname",
        "name": "Name",
        "role": "Rolle",
        "entry_date": "Eintrittsdatum",
        "telefon": "Telefonnummer",
        "diensthund": "Diensthund",
        "urlaub_gesamt": "Urlaubstage (Gesamt)",  # DIESE ZEILE IST ENTSCHEIDEND
        "urlaub_rest": "Resturlaub",
        "geburtstag": "Geburtstag"
    }

    DEFAULT_VISIBLE = ["vorname", "name", "role", "entry_date", "telefon", "urlaub_rest"]

    @staticmethod
    def load_config():
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                config = {}

        config_changed = False
        if 'all_columns' not in config or not config['all_columns']:
            config['all_columns'] = ColumnManager.DEFAULT_COLUMNS
            config_changed = True

        if 'visible' not in config:
            config['visible'] = ColumnManager.DEFAULT_VISIBLE
            config_changed = True

        if config_changed or not os.path.exists(CONFIG_FILE):
            ColumnManager.save_config(config['all_columns'], config['visible'])

        return config

    @staticmethod
    def save_config(all_columns, visible_columns):
        config = {'all_columns': all_columns, 'visible': visible_columns}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)

    @staticmethod
    def add_column(display_name):
        config = ColumnManager.load_config()
        technical_key = "custom_" + display_name.lower().replace(" ", "_")
        if technical_key in config['all_columns']:
            return False, "Eine Spalte mit diesem technischen Namen existiert bereits."

        config['all_columns'][technical_key] = display_name
        if technical_key not in config['visible']:
            config['visible'].append(technical_key)

        ColumnManager.save_config(config['all_columns'], config['visible'])
        return True, "Spalte erfolgreich hinzugefügt."

    @staticmethod
    def delete_column(key_to_delete):
        config = ColumnManager.load_config()
        if key_to_delete in ColumnManager.CORE_COLUMNS:
            return False, "Kern-Spalten wie 'Name' oder 'Rolle' können nicht gelöscht werden."
        if not key_to_delete.startswith("custom_"):
            return False, "Nur selbst erstellte Spalten können gelöscht werden."
        if key_to_delete in config['all_columns']:
            del config['all_columns'][key_to_delete]
        if key_to_delete in config['visible']:
            config['visible'].remove(key_to_delete)

        ColumnManager.save_config(config['all_columns'], config['visible'])
        return True, "Spalte wurde erfolgreich gelöscht."