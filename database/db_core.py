# database/db_core.py
import mysql.connector
from mysql.connector import pooling
import hashlib
import json
from datetime import datetime
from collections import defaultdict

# ==============================================================================
# 💥 HARTKODIERTE DATENBANK-KONFIGURATION (WICHTIG!) 💥
# ==============================================================================
DB_CONFIG = {
    "host": "100.118.148.97",
    "user": "planer_user",
    "password": "PlanerNeu-2025#",
    "database": "planer_db",
    "raise_on_warnings": True,
    # HIER IST DIE LÖSUNG: Erzwinge die alte Authentifizierungsmethode
    "auth_plugin": "mysql_native_password"
}
# ==============================================================================

try:
    print("Versuche, den Datenbank-Connection-Pool zu erstellen...")
    db_pool = pooling.MySQLConnectionPool(pool_name="dhf_pool",
                                          pool_size=5,
                                          **DB_CONFIG)
    print("✅ Datenbank-Connection-Pool erfolgreich erstellt.")
except mysql.connector.Error as err:
    print(f"❌ KRITISCHER FEHLER beim Erstellen des Connection-Pools: {err}")
    db_pool = None


def create_connection():
    if db_pool is None:
        print("❌ Fehler: Der Connection-Pool ist nicht verfügbar.")
        return None
    try:
        return db_pool.get_connection()
    except mysql.connector.Error as err:
        print(f"❌ Fehler beim Abrufen einer Verbindung aus dem Pool: {err}")
        return None


def close_pool():
    print("Der Datenbank-Connection-Pool wird bei Programmende verwaltet.")


# --- Wichtige Konstanten ---
ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}
MIN_STAFFING_RULES_CONFIG_KEY = "MIN_STAFFING_RULES"
# --- KONSTANTEN FÜR DATEI-MIGRATION ---
REQUEST_LOCKS_CONFIG_KEY = "REQUEST_LOCKS"
ADMIN_MENU_CONFIG_KEY = "ADMIN_MENU_CONFIG"
USER_TAB_ORDER_CONFIG_KEY = "USER_TAB_ORDER"
ADMIN_TAB_ORDER_CONFIG_KEY = "ADMIN_TAB_ORDER"


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    db_name = DB_CONFIG.get('database')
    cursor.execute(f"""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = '{table_name}' AND COLUMN_NAME = '{column_name}'
    """)
    if cursor.fetchone()[0] == 0:
        print(f"Füge Spalte '{column_name}' zur Tabelle '{table_name}' hinzu...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _add_index_if_not_exists(cursor, table_name, index_name, columns):
    """Fügt einen Index hinzu, falls er noch nicht existiert."""
    # Verwenden Sie DATABASE() anstelle von TABLE_SCHEMA = 'db_name' für Flexibilität
    cursor.execute(f"""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}' AND INDEX_NAME = '{index_name}'
    """)
    if cursor.fetchone()[0] == 0:
        print(f"Füge Index '{index_name}' zur Tabelle '{table_name}' hinzu...")
        cursor.execute(f"CREATE INDEX {index_name} ON {table_name} ({columns})")


def initialize_db():
    config_init = DB_CONFIG.copy()
    db_name = config_init.pop('database')

    try:
        conn_server = mysql.connector.connect(**config_init)
        cursor_server = conn_server.cursor()
        cursor_server.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        print(f"Datenbank '{db_name}' wurde überprüft/erstellt.")
        cursor_server.close()
        conn_server.close()
    except mysql.connector.Error as e:
        print(f"KRITISCHER FEHLER: Konnte die Datenbank nicht erstellen: {e}")
        return

    conn = create_connection()
    if conn is None:
        print("Konnte die Datenbank-Tabellen nicht initialisieren.")
        return

    try:
        cursor = conn.cursor(dictionary=True)
        # --- Tabellen erstellen --- (Gekürzt für Lesbarkeit)
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS config_storage (config_key VARCHAR(255) PRIMARY KEY, config_json TEXT NOT NULL);")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS shift_frequency (shift_abbrev VARCHAR(255) PRIMARY KEY, count INT NOT NULL DEFAULT 0);")
        # ... (andere CREATE TABLE Anweisungen bleiben unverändert) ...
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, vorname TEXT NOT NULL, name TEXT NOT NULL, geburtstag TEXT, telefon TEXT, diensthund TEXT, urlaub_gesamt INT DEFAULT 30, urlaub_rest INT DEFAULT 30, entry_date TEXT, has_seen_tutorial INT DEFAULT 0, password_changed INT DEFAULT 0, last_ausbildung TEXT, last_schiessen TEXT, UNIQUE (vorname(255), name(255)));")
        # ... (restliche CREATE TABLE Anweisungen) ...
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS chat_messages (id INT AUTO_INCREMENT PRIMARY KEY, sender_id INT NOT NULL, recipient_id INT NOT NULL, message TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_read INT DEFAULT 0, FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE);")


        # --- Index hinzufügen ---
        _add_index_if_not_exists(cursor, "shift_schedule", "idx_shift_date_user", "shift_date(255), user_id")

        # --- Spalten hinzufügen (Migrationslogik) ---
        # ... (andere _add_column_if_not_exists Aufrufe bleiben unverändert) ...
        _add_column_if_not_exists(cursor, "users", "entry_date", "TEXT")
        _add_column_if_not_exists(cursor, "users", "last_seen", "DATETIME")

        # --- NEU FÜR FREISCHALTUNG ---
        _add_column_if_not_exists(cursor, "users", "is_approved", "INT DEFAULT 0")

        # --- NEU FÜR ARCHIVIERUNG ---
        _add_column_if_not_exists(cursor, "users", "is_archived", "TINYINT NOT NULL DEFAULT 0 AFTER is_approved")

        # --- NEU: DATUM FÜR ARCHIVIERUNG ---
        _add_column_if_not_exists(cursor, "users", "archived_date", "DATETIME NULL DEFAULT NULL AFTER is_archived")


        conn.commit()
        print("Datenbank und Tabellen erfolgreich initialisiert/überprüft.")
    except mysql.connector.Error as e:
        print(f"Fehler bei der Initialisierung der Tabellen: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- Restliche Hilfsfunktionen (save_config_json bis _create_admin_notification) bleiben unverändert ---

def save_config_json(key, data_dict):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        data_json = json.dumps(data_dict)
        query = "INSERT INTO config_storage (config_key, config_json) VALUES (%s, %s) AS new_value ON DUPLICATE KEY UPDATE config_json = new_value.config_json"
        cursor.execute(query, (key, data_json))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_config_json ({key}): {e}")
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def load_config_json(key):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT config_json FROM config_storage WHERE config_key = %s", (key,))
        result = cursor.fetchone()
        if result and result['config_json']:
            return json.loads(result['config_json'])
        return None
    except mysql.connector.Error as e:
        print(f"DB Error on load_config_json ({key}): {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON Decode Error for key: {key}")
        return None
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def save_shift_frequency(frequency_dict):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_frequency")
        for abbrev, count in frequency_dict.items():
            query = "INSERT INTO shift_frequency (shift_abbrev, count) VALUES (%s, %s)"
            cursor.execute(query, (abbrev, count))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_shift_frequency: {e}")
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def load_shift_frequency():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return defaultdict(int)
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT shift_abbrev, count FROM shift_frequency")
        results = cursor.fetchall()
        return defaultdict(int, {row['shift_abbrev']: row['count'] for row in results})
    except mysql.connector.Error as e:
        print(f"DB Error on load_shift_frequency: {e}")
        return defaultdict(int)
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def reset_shift_frequency():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_frequency")
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on reset_shift_frequency: {e}")
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def save_special_appointment(date_str, appointment_type, description=""):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = "INSERT INTO special_appointments (appointment_date, appointment_type, description) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE appointment_type=VALUES(appointment_type), description=VALUES(description)"
        cursor.execute(query, (date_str, appointment_type, description))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_special_appointment: {e}")
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def delete_special_appointment(date_str, appointment_type):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = "DELETE FROM special_appointments WHERE appointment_date = %s AND appointment_type = %s"
        cursor.execute(query, (date_str, appointment_type))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on delete_special_appointment: {e}")
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def get_special_appointments():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM special_appointments")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"DB Error on get_special_appointments: {e}")
        return []
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def _log_activity(cursor, user_id, action_type, details):
    # ... (unverändert) ...
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (%s, %s, %s, %s)",
        (timestamp, user_id, action_type, details)
    )

def _create_admin_notification(cursor, message):
    # ... (unverändert) ...
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO admin_notifications (message, timestamp) VALUES (%s, %s)",
        (message, timestamp)
    )

# --- DB Update/Fix Funktionen ---

def run_db_fix_approve_all_users():
    # ... (unverändert) ...
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_approved = 1 WHERE is_approved = 0")
        updated_rows = cursor.rowcount
        conn.commit()
        return True, f"{updated_rows} bestehende Benutzer wurden erfolgreich freigeschaltet. Bitte loggen Sie sich nun mit Ihren normalen Zugangsdaten neu ein."
    except mysql.connector.Error as e:
        return False, f"Ein Datenbankfehler ist aufgetreten: {e}"
    except Exception as e:
        return False, f"Ein unerwarteter Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def run_db_update_is_approved():
    # ... (unverändert) ...
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        _add_column_if_not_exists(cursor, "users", "is_approved", "INT DEFAULT 0")
        conn.commit()
        return True, "Datenbank-Update (is_approved Spalte) erfolgreich ausgeführt! Registrierungen sollten jetzt funktionieren."
    except mysql.connector.Error as e:
        return False, f"Ein Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def run_db_update_v1():
    # ... (unverändert) ...
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        _add_column_if_not_exists(cursor, "users", "last_seen", "DATETIME")
        conn.commit()
        print("Überprüfe/Erstelle Tabelle 'chat_messages'...")
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS chat_messages(...);
                       """) # Gekürzt
        conn.commit()
        print("Tabelle 'chat_messages' erfolgreich überprüft/erstellt.")
        return True, "Datenbank-Update für Chat-Funktion erfolgreich ausgeführt! Bitte starte die Anwendung neu."
    except mysql.connector.Error as e:
        return False, f"Ein Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def run_db_update_add_is_archived():
    # ... (unverändert, verwendet jetzt korrekte TINYINT Syntax) ...
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        _add_column_if_not_exists(cursor, "users", "is_archived", "TINYINT NOT NULL DEFAULT 0 AFTER is_approved")
        conn.commit()
        print("[DB Update] Spalte 'is_archived' erfolgreich zur 'users'-Tabelle hinzugefügt/überprüft.")
        return True, "Datenbank-Update für 'is_archived' erfolgreich durchgeführt."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Hinzufügen von 'is_archived': {e}")
        return False, f"Fehler beim Hinzufügen von 'is_archived': {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

# --- NEUE FUNKTION FÜR ARCHIVIERUNGSDATUM ---
def run_db_update_add_archived_date():
    """Fügt die Spalte 'archived_date' zur 'users'-Tabelle hinzu."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        # Fügen Sie die Spalte hinzu (die Hilfsfunktion prüft, ob sie bereits existiert)
        _add_column_if_not_exists(cursor, "users", "archived_date", "DATETIME NULL DEFAULT NULL AFTER is_archived")

        conn.commit()
        print("[DB Update] Spalte 'archived_date' erfolgreich zur 'users'-Tabelle hinzugefügt/überprüft.")
        return True, "Datenbank-Update für 'archived_date' erfolgreich durchgeführt."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Hinzufügen von 'archived_date': {e}")
        return False, f"Fehler beim Hinzufügen von 'archived_date': {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()