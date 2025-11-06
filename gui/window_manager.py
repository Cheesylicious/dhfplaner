# gui/window_manager.py
# (Regel 4: Neue Datei zur Vermeidung von Monolithen und zur Zentralisierung)

"""
Single Source of Truth (Zentrale Wahrheitsquelle) für die Konfiguration der Hauptfenster.

(NEU - V2): Dieses Modul lädt die Konfiguration jetzt aus der 'app_config'-Datenbanktabelle.
Es ist verantwortlich für das Laden, Caching und Speichern dieser Konfiguration.
"""

# (Regel 4) Import der DB-Funktionen
from database.db_core import load_config_json, save_config_json

# Der Schlüssel, unter dem die Konfiguration in der 'app_config' Tabelle gespeichert wird
WINDOW_CONFIG_KEY = "main_window_configuration"

# (Regel 1) Dies ist jetzt der Standard-Fallback, falls nichts in der DB gefunden wird.
DEFAULT_WINDOW_CONFIG = {
    "main_user_window": {
        "display_name": "Benutzer-Fenster",
        "allow_registration": True,  # Dürfen Benutzer sich hierfür registrieren?
        "default_role": "Mitarbeiter"  # Welche Rolle bekommen sie?
    },
    "main_admin_window": {
        "display_name": "Admin-Fenster",
        "allow_registration": False,  # Admins können sich nicht selbst registrieren
        "default_role": None
    },
    "main_zuteilung_window": {
        "display_name": "Zuteilungs-Fenster",
        "allow_registration": True,  # Ja, hier "parken" wir sie
        "default_role": "Guest"  # (Passt zu db_schema.py)
    }
}

# (Regel 2: Performance) Cache, um ständige DB-Aufrufe zu vermeiden.
_config_cache = None


def _load_and_cache_config(force_reload=False):
    """
    Lädt die Konfiguration aus der DB oder dem Cache.
    Wenn in der DB nichts vorhanden ist, wird die Standardkonfiguration
    verwendet UND in die DB gespeichert (Regel 1: Selbstheilung).
    """
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache

    # Lade aus der DB
    config_from_db = load_config_json(WINDOW_CONFIG_KEY)

    if config_from_db is None:
        # (Regel 1) Nichts in der DB gefunden.
        print(f"[WindowManager] Keine Fenster-Konfiguration in der DB gefunden. Erstelle Standard...")
        _config_cache = DEFAULT_WINDOW_CONFIG
        # Speichere den Standardwert in der DB für die Zukunft
        save_config_json(WINDOW_CONFIG_KEY, _config_cache)
        return _config_cache

    # (Regel 1) Stelle sicher, dass die DB-Konfiguration alle Schlüssel enthält,
    # die der Code erwartet (z.B. nach einem Update).
    config_migrated = False
    for db_key, default_settings in DEFAULT_WINDOW_CONFIG.items():
        if db_key not in config_from_db:
            # Neuer Fenstertyp (z.B. 'main_zuteilung_window') wurde im Code hinzugefügt
            config_from_db[db_key] = default_settings
            config_migrated = True

    if config_migrated:
        print(f"[WindowManager] Fenster-Konfiguration migriert (neue Schlüssel hinzugefügt). Speichere...")
        save_config_json(WINDOW_CONFIG_KEY, config_from_db)

    _config_cache = config_from_db
    return _config_cache


def clear_window_config_cache():
    """Setzt den Cache zurück, wenn ein Admin die Einstellungen speichert."""
    global _config_cache
    _config_cache = None


def get_window_config(force_reload=False):
    """
    Gibt das vollständige Konfigurations-Dictionary zurück.
    (Wird vom neuen Einstellungs-Tab benötigt)
    """
    return _load_and_cache_config(force_reload)


def save_window_config(new_config_data):
    """
    Speichert die Konfiguration in der DB und leert den Cache.
    (Wird vom neuen Einstellungs-Tab benötigt)
    """
    if save_config_json(WINDOW_CONFIG_KEY, new_config_data):
        clear_window_config_cache()
        return True
    return False


def get_window_options_for_roles():
    """
    Gibt das Dictionary für den Rollen-Management-Dialog (role_management_dialog.py) zurück.
    (Lädt jetzt dynamisch)
    """
    config_data = _load_and_cache_config()
    return {
        config["display_name"]: db_key
        for db_key, config in config_data.items()
    }


def get_window_options_for_registration():
    """
    Gibt eine Liste von Tupeln für das Registrierungs-Fenster (registration_window.py) zurück.
    (Lädt jetzt dynamisch)
    """
    config_data = _load_and_cache_config()
    return [
        (config["display_name"], db_key)
        for db_key, config in config_data.items()
        if config.get("allow_registration", False)
    ]


def get_default_role_for_window(db_window_key):
    """
    Gibt die Standard-Rolle (z.B. 'Guest') für einen
    ausgewählten Fensternamen (z.B. 'main_zuteilung_window') zurück.
    (Lädt jetzt dynamisch)
    """
    config_data = _load_and_cache_config()
    config = config_data.get(db_window_key)

    if config:
        return config.get("default_role", "Guest")

    return "Guest"