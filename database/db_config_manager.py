# database/db_config_manager.py
import json
import mysql.connector
# KORREKTUR: Import von der neuen Verbindungsdatei
from .db_connection import create_connection

# --- INNOVATION 2: Cache für Konfigurationen ---
_config_cache = {}
# ---------------------------------------------

def save_config_json(key, data_dict):
    """
    Speichert eine Konfiguration (JSON) in der Datenbank.
    Nutzt 'config_storage' und leert den Cache.
    """
    global _config_cache
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        data_json = json.dumps(data_dict)
        query = "INSERT INTO config_storage (config_key, config_json) VALUES (%s, %s) ON DUPLICATE KEY UPDATE config_json = VALUES(config_json)"
        cursor.execute(query, (key, data_json))
        conn.commit()

        # Cache leeren
        if key in _config_cache:
            del _config_cache[key]

        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_config_json ({key}): {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def load_config_json(key):
    """
    Lädt eine Konfiguration (JSON) aus der Datenbank.
    Nutzt 'config_storage' und Caching.
    """
    global _config_cache
    # 1. Prüfe den Cache
    if key in _config_cache:
        print(f"[DEBUG] Lade '{key}' aus dem Cache.")
        return _config_cache[key]

    # 2. Lade aus DB
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_json FROM config_storage WHERE config_key = %s", (key,))
        result = cursor.fetchone()
        if result and result['config_json']:
            data = json.loads(result['config_json'])
            # 3. Speichere im Cache
            _config_cache[key] = data
            return data
        return None
    except mysql.connector.Error as e:
        print(f"DB Error on load_config_json ({key}): {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON Decode Error for key: {key}")
        return None
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def clear_config_cache(config_key=None):
    """
    Leert den Konfigurations-Cache.
    Wenn config_key None ist, wird der gesamte Cache geleert.
    """
    global _config_cache
    if config_key:
        if config_key in _config_cache:
            del _config_cache[config_key]
            print(f"[DEBUG] Cache für '{config_key}' (extern) geleert.")
    else:
        _config_cache.clear()
        print("[DEBUG] Gesamter Konfig-Cache (extern) geleert.")