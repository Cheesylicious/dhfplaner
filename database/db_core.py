import mysql.connector
import hashlib
import json
from datetime import datetime
from collections import defaultdict  # Neu hinzugefügt für defaultdict Kompatibilität

# ==============================================================================
# 💥 HARTKODIERTE DATENBANK-KONFIGURATION (WICHTIG!) 💥
# ==============================================================================
DB_CONFIG = {
    "host": "100.118.148.97",
    "user": "planer_user",
    "password": "PlanerNeu-2025#",
    "database": "planer_db"
}
# ==============================================================================


# Die Rollen-Hierarchie bleibt unverändert
ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}


def hash_password(password):
    """Hashes the password using SHA256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def get_db_config():
    """Gibt die hartkodierte Datenbankkonfiguration zurück."""
    if all(key in DB_CONFIG for key in ["host", "user", "password", "database"]):
        return DB_CONFIG
    else:
        print("Fehler: Die hartkodierte DB_CONFIG ist unvollständig.")
        return None


def create_connection():
    """Erstellt eine Verbindung zur MySQL-Datenbank."""
    config = get_db_config()
    if config is None:
        return None

    try:
        conn = mysql.connector.connect(**config)
        return conn
    except mysql.connector.Error as e:
        print(f"Fehler bei der Verbindung zur MySQL-Datenbank: {e}")
        return None


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Fügt eine Spalte zu einer Tabelle hinzu, falls sie nicht existiert (MySQL-Version)."""
    current_config = DB_CONFIG.copy()
    db_name = current_config.get('database')

    cursor.execute(f"""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = '{table_name}' AND COLUMN_NAME = '{column_name}'
    """)
    if cursor.fetchone()[0] == 0:
        print(f"Füge Spalte '{column_name}' zur Tabelle '{table_name}' hinzu...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def initialize_db():
    """
    Initialisiert die Datenbank: Erstellt die DB (falls nötig) und dann die Tabellen.
    """
    config = DB_CONFIG.copy()
    if not config:
        print("Initialisierung abgebrochen: Konfiguration konnte nicht geladen werden.")
        return

    db_name = config.pop('database')

    try:
        conn_server = mysql.connector.connect(**config)
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

        # --- Tabellen erstellen (MySQL-Syntax) ---

        # Generische Tabelle für Konfigurationen
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS config_storage
                       (
                           config_key
                           VARCHAR
                       (
                           255
                       ) PRIMARY KEY,
                           config_json TEXT NOT NULL
                           );
                       """)

        # Tabelle für Schichthäufigkeitszähler
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS shift_frequency
                       (
                           shift_abbrev
                           VARCHAR
                       (
                           255
                       ) PRIMARY KEY,
                           count INT NOT NULL DEFAULT 0
                           );
                       """)

        # Tabelle für gemeinsame Sondertermine
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS special_appointments
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           appointment_date
                           TEXT
                           NOT
                           NULL,
                           appointment_type
                           VARCHAR
                       (
                           255
                       ) NOT NULL,
                           description TEXT,
                           UNIQUE
                       (
                           appointment_date
                       (
                           255
                       ), appointment_type)
                           );
                       """)

        # --- (Restliche Tabellen bleiben unverändert) ---
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS users
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           password_hash
                           TEXT
                           NOT
                           NULL,
                           role
                           TEXT
                           NOT
                           NULL,
                           vorname
                           TEXT
                           NOT
                           NULL,
                           name
                           TEXT
                           NOT
                           NULL,
                           geburtstag
                           TEXT,
                           telefon
                           TEXT,
                           diensthund
                           TEXT,
                           urlaub_gesamt
                           INT
                           DEFAULT
                           30,
                           urlaub_rest
                           INT
                           DEFAULT
                           30,
                           entry_date
                           TEXT,
                           has_seen_tutorial
                           INT
                           DEFAULT
                           0,
                           password_changed
                           INT
                           DEFAULT
                           0,
                           last_ausbildung
                           TEXT,
                           last_schiessen
                           TEXT,
                           UNIQUE (
                           vorname
                       (
                           255
                       ), name
                       (
                           255
                       ))
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS vacation_requests
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           user_id
                           INT
                           NOT
                           NULL,
                           start_date
                           TEXT
                           NOT
                           NULL,
                           end_date
                           TEXT
                           NOT
                           NULL,
                           status
                           TEXT
                           NOT
                           NULL,
                           request_date
                           TEXT
                           NOT
                           NULL,
                           archived
                           INT
                           DEFAULT
                           0,
                           user_notified
                           INT
                           DEFAULT
                           1,
                           FOREIGN
                           KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       )
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS wunschfrei_requests
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           user_id
                           INT
                           NOT
                           NULL,
                           request_date
                           TEXT
                           NOT
                           NULL,
                           status
                           VARCHAR
                       (
                           255
                       ) NOT NULL DEFAULT 'Ausstehend',
                           notified INT DEFAULT 0,
                           rejection_reason TEXT,
                           requested_shift TEXT,
                           requested_by VARCHAR
                       (
                           255
                       ) DEFAULT 'user',
                           UNIQUE
                       (
                           user_id,
                           request_date
                       (
                           255
                       )),
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS dogs
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           name
                           VARCHAR
                       (
                           255
                       ) UNIQUE NOT NULL,
                           breed TEXT,
                           birth_date TEXT,
                           chip_number VARCHAR
                       (
                           255
                       ) UNIQUE,
                           acquisition_date TEXT,
                           departure_date TEXT,
                           last_dpo_date TEXT,
                           vaccination_info TEXT
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS shift_types
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           name
                           TEXT
                           NOT
                           NULL,
                           abbreviation
                           VARCHAR
                       (
                           255
                       ) UNIQUE NOT NULL,
                           hours INT NOT NULL,
                           description TEXT,
                           color TEXT,
                           start_time TEXT,
                           end_time TEXT
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS shift_schedule
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           user_id
                           INT
                           NOT
                           NULL,
                           shift_date
                           TEXT
                           NOT
                           NULL,
                           shift_abbrev
                           VARCHAR
                       (
                           255
                       ) NOT NULL,
                           UNIQUE
                       (
                           user_id,
                           shift_date
                       (
                           255
                       )),
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ),
                           FOREIGN KEY
                       (
                           shift_abbrev
                       ) REFERENCES shift_types
                       (
                           abbreviation
                       )
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS user_order
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           user_id
                           INT
                           NOT
                           NULL
                           UNIQUE,
                           sort_order
                           INT
                           NOT
                           NULL,
                           is_visible
                           INT
                           DEFAULT
                           1,
                           FOREIGN
                           KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS shift_order
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           abbreviation
                           VARCHAR
                       (
                           255
                       ) NOT NULL UNIQUE,
                           sort_order INT NOT NULL,
                           is_visible INT DEFAULT 1,
                           check_for_understaffing INT DEFAULT 0
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS activity_log
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           timestamp
                           TEXT
                           NOT
                           NULL,
                           user_id
                           INT,
                           action_type
                           TEXT
                           NOT
                           NULL,
                           details
                           TEXT,
                           FOREIGN
                           KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE SET NULL
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS admin_notifications
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           message
                           TEXT
                           NOT
                           NULL,
                           is_read
                           INT
                           NOT
                           NULL
                           DEFAULT
                           0,
                           timestamp
                           TEXT
                           NOT
                           NULL
                       );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS bug_reports
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           user_id
                           INT
                           NOT
                           NULL,
                           title
                           TEXT
                           NOT
                           NULL,
                           description
                           TEXT
                           NOT
                           NULL,
                           timestamp
                           TEXT
                           NOT
                           NULL,
                           status
                           VARCHAR
                       (
                           255
                       ) NOT NULL DEFAULT 'Neu',
                           is_read INT NOT NULL DEFAULT 0,
                           user_notified INT NOT NULL DEFAULT 1,
                           archived INT NOT NULL DEFAULT 0,
                           admin_notes TEXT,
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS password_reset_requests
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           user_id
                           INT
                           NOT
                           NULL,
                           timestamp
                           TEXT
                           NOT
                           NULL,
                           status
                           VARCHAR
                       (
                           255
                       ) NOT NULL DEFAULT 'Ausstehend',
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE
                           );
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS locked_months
                       (
                           year
                           INT
                           NOT
                           NULL,
                           month
                           INT
                           NOT
                           NULL,
                           PRIMARY
                           KEY
                       (
                           year,
                           month
                       )
                           );
                       """)

        # --- Spalten-Checks ---
        cursor_check = conn.cursor()
        _add_column_if_not_exists(cursor_check, "users", "entry_date", "TEXT")
        _add_column_if_not_exists(cursor_check, "shift_types", "color", "TEXT DEFAULT '#FFFFFF'")
        _add_column_if_not_exists(cursor_check, "user_order", "is_visible", "INT DEFAULT 1")
        _add_column_if_not_exists(cursor_check, "shift_order", "is_visible", "INT DEFAULT 1")
        _add_column_if_not_exists(cursor_check, "shift_order", "check_for_understaffing", "INT DEFAULT 0")
        _add_column_if_not_exists(cursor_check, "wunschfrei_requests", "notified", "INT DEFAULT 0")
        _add_column_if_not_exists(cursor_check, "wunschfrei_requests", "rejection_reason", "TEXT")
        _add_column_if_not_exists(cursor_check, "wunschfrei_requests", "requested_shift", "TEXT")
        _add_column_if_not_exists(cursor_check, "wunschfrei_requests", "requested_by",
                                  "VARCHAR(255) DEFAULT 'user'")
        _add_column_if_not_exists(cursor_check, "shift_types", "start_time", "TEXT")
        _add_column_if_not_exists(cursor_check, "shift_types", "end_time", "TEXT")
        _add_column_if_not_exists(cursor_check, "bug_reports", "user_notified", "INT NOT NULL DEFAULT 1")
        _add_column_if_not_exists(cursor_check, "bug_reports", "archived", "INT NOT NULL DEFAULT 0")
        _add_column_if_not_exists(cursor_check, "bug_reports", "admin_notes", "TEXT")
        _add_column_if_not_exists(cursor_check, "users", "has_seen_tutorial", "INT DEFAULT 0")
        _add_column_if_not_exists(cursor_check, "vacation_requests", "archived", "INT DEFAULT 0")
        _add_column_if_not_exists(cursor_check, "vacation_requests", "user_notified", "INT DEFAULT 1")
        _add_column_if_not_exists(cursor_check, "users", "password_changed", "INT DEFAULT 0")
        _add_column_if_not_exists(cursor_check, "users", "last_ausbildung", "TEXT")
        _add_column_if_not_exists(cursor_check, "users", "last_schiessen", "TEXT")

        conn.commit()
        print("Datenbank und Tabellen erfolgreich initialisiert/überprüft.")
    except mysql.connector.Error as e:
        print(f"Fehler bei der Initialisierung der Tabellen: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- FUNKTIONEN FÜR ZENTRALE KONFIGURATIONEN (GENERAL) ---

def save_config_json(key, data_dict):
    """Speichert ein beliebiges Konfigurations-Dictionary unter einem Schlüssel."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        data_json = json.dumps(data_dict)
        query = """
                INSERT INTO config_storage (config_key, config_json)
                VALUES (%s, %s) ON DUPLICATE KEY \
                UPDATE config_json = \
                VALUES (config_json) \
                """
        cursor.execute(query, (key, data_json))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_config_json ({key}): {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def load_config_json(key):
    """Lädt ein beliebiges Konfigurations-Dictionary anhand seines Schlüssels."""
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT config_json FROM config_storage WHERE config_key = %s", (key,))
        result = cursor.fetchone()
        if result and result[0]:
            return json.loads(result[0])
        return None
    except mysql.connector.Error as e:
        print(f"DB Error on load_config_json ({key}): {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON Decode Error for key: {key}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- FUNKTIONEN FÜR SCHICHTHÄUFIGKEIT ---

def save_shift_frequency(frequency_dict):
    """Speichert die Schichthäufigkeit aller Schichten in der DB."""
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def load_shift_frequency():
    """Lädt die Schichthäufigkeit aus der DB."""
    conn = create_connection()
    if conn is None: return {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT shift_abbrev, count FROM shift_frequency")
        results = cursor.fetchall()
        return {row[0]: row[1] for row in results}
    except mysql.connector.Error as e:
        print(f"DB Error on load_shift_frequency: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def reset_shift_frequency():
    """Setzt den Zähler für die Schichthäufigkeit zurück."""
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- FUNKTIONEN FÜR ZENTRALE SONDERTERMINE ---

def save_special_appointment(date_str, appointment_type, description=""):
    """Speichert einen neuen Sondertermin in der Datenbank."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = """
                INSERT INTO special_appointments (appointment_date, appointment_type, description)
                VALUES (%s, %s, %s) ON DUPLICATE KEY \
                UPDATE description = \
                VALUES (description) \
                """
        cursor.execute(query, (date_str, appointment_type, description))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_special_appointment: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_special_appointment(date_str, appointment_type):
    """Löscht einen Sondertermin aus der Datenbank."""
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_special_appointments():
    """Holt alle Sondertermine aus der Datenbank."""
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def _log_activity(cursor, user_id, action_type, details):
    """Logs an activity to the activity_log table."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (%s, %s, %s, %s)",
        (timestamp, user_id, action_type, details)
    )


def _create_admin_notification(cursor, message):
    """Creates a notification for the admin."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO admin_notifications (message, timestamp) VALUES (%s, %s)",
        (message, timestamp)
    )