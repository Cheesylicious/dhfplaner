# database/db_schema.py
import mysql.connector

# KORREKTUR: Importiert die Helfer aus der neuen Datei
from .db_schema_helpers import _add_column_if_not_exists, _add_index_if_not_exists


# ==============================================================================
# --- SCHEMA-INITIALISIERUNG UND MIGRATION ---
# ==============================================================================
#
# (Die Definitionen von _add_column_if_not_exists und _add_index_if_not_exists
#  sind jetzt in db_schema_helpers.py)
#

def _run_initialize_db(conn, db_config):
    """
    Führt die eigentliche Schema-Initialisierung durch.
    Wird von create_connection() beim ersten Start aufgerufen.
    Nimmt eine *existierende* Verbindung und die DB_CONFIG entgegen.
    """
    if db_config is None:
        raise ConnectionError("DB-Init fehlgeschlagen: Konfiguration nicht geladen.")

    config_init = db_config.copy()
    db_name = config_init.pop('database')
    if not db_name:
        raise ValueError("Datenbank-Name nicht in DB_CONFIG gefunden.")

    # 1. DB-Erstellung (separater Connect ohne Pool)
    try:
        conn_server = mysql.connector.connect(**config_init)
        cursor_server = conn_server.cursor()
        cursor_server.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        print(f"Datenbank '{db_name}' wurde überprüft/erstellt.")
        cursor_server.close()
        conn_server.close()
    except mysql.connector.Error as e:
        if e.errno == 1007:
            print(f"Info: Datenbank '{db_name}' existiert bereits. (Fehler 1007 ignoriert)")
        else:
            print(f"KRITISCHER FEHLER: Konnte die Datenbank nicht erstellen: {e}")
            raise ConnectionError(f"DB konnte nicht erstellt werden: {e}")
    except Exception as e:
        print(f"KRITISCHER FEHLER: Verbindung zum DB-Server fehlgeschlagen: {e}")
        raise ConnectionError(f"DB-Server-Verbindung fehlgeschlagen: {e}")

    # 2. Tabellen-Erstellung (nutzt die übergebene Pool-Verbindung 'conn')
    if conn is None:
        print("Konnte die Datenbank-Tabellen nicht initialisieren.")
        raise ConnectionError("DB-Verbindung für Tabellen-Init fehlgeschlagen.")

    try:
        cursor = conn.cursor(dictionary=True)

        def execute_create_table_if_not_exists(create_statement):
            try:
                cursor.execute(create_statement)
            except mysql.connector.Error as e:
                if e.errno == 1050:  # Table already exists
                    # Versuche, den Tabellennamen aus dem Statement zu extrahieren
                    try:
                        table_name = create_statement.split("IF NOT EXISTS")[1].strip().split("(")[0].strip().replace(
                            '`', '')
                        print(f"Info: Tabelle '{table_name}' existiert bereits. (Fehler 1050 ignoriert)")
                    except Exception:
                        print("Info: Tabelle existiert bereits. (Fehler 1050 ignoriert)")
                else:
                    # Anderen Fehler weiter werfen
                    raise e

        # --- Tabellen erstellen ---
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `config_storage` (config_key VARCHAR(255) PRIMARY KEY, config_json TEXT NOT NULL);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `shift_frequency` (shift_abbrev VARCHAR(255) PRIMARY KEY, count INT NOT NULL DEFAULT 0);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `users` (id INT AUTO_INCREMENT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL, vorname TEXT NOT NULL, name TEXT NOT NULL, geburtstag TEXT, telefon TEXT, diensthund TEXT, urlaub_gesamt INT DEFAULT 30, urlaub_rest INT DEFAULT 30, entry_date TEXT, has_seen_tutorial TINYINT(1) DEFAULT 0, password_changed TINYINT(1) DEFAULT 0, last_ausbildung DATE DEFAULT NULL, last_schiessen DATE DEFAULT NULL, last_seen DATETIME DEFAULT NULL, is_approved TINYINT(1) DEFAULT 0, is_archived TINYINT(1) DEFAULT 0, archived_date DATETIME DEFAULT NULL, activation_date DATETIME NULL DEFAULT NULL, UNIQUE (vorname(255), name(255)));")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `chat_messages` (id INT AUTO_INCREMENT PRIMARY KEY, sender_id INT NOT NULL, recipient_id INT NOT NULL, message TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_read TINYINT(1) DEFAULT 0, FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE);")
        execute_create_table_if_not_exists("""
                                           CREATE TABLE IF NOT EXISTS `shift_types`
                                           (
                                               `id`
                                               INT
                                               NOT
                                               NULL
                                               AUTO_INCREMENT,
                                               `name`
                                               VARCHAR
                                           (
                                               255
                                           ) NOT NULL,
                                               `abbreviation` VARCHAR
                                           (
                                               10
                                           ) NOT NULL,
                                               `hours` DECIMAL
                                           (
                                               4,
                                               2
                                           ) DEFAULT NULL,
                                               `description` TEXT,
                                               `color` VARCHAR
                                           (
                                               7
                                           ) DEFAULT '#FFFFFF',
                                               `start_time` TIME DEFAULT NULL,
                                               `end_time` TIME DEFAULT NULL,
                                               `check_for_understaffing` TINYINT
                                           (
                                               1
                                           ) DEFAULT '0',
                                               PRIMARY KEY
                                           (
                                               `id`
                                           ),
                                               UNIQUE KEY `abbreviation`
                                           (
                                               `abbreviation`
                                           )
                                               );
                                           """)
        execute_create_table_if_not_exists("""
                                           CREATE TABLE IF NOT EXISTS `shift_order`
                                           (
                                               `abbreviation`
                                               VARCHAR
                                           (
                                               10
                                           ) NOT NULL,
                                               `sort_order` INT NOT NULL,
                                               `is_visible` TINYINT
                                           (
                                               1
                                           ) DEFAULT '1',
                                               PRIMARY KEY
                                           (
                                               `abbreviation`
                                           )
                                               );
                                           """)
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `shift_schedule` (user_id INT NOT NULL, shift_date DATE NOT NULL, shift_abbrev VARCHAR(10), PRIMARY KEY (user_id, shift_date));")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `activity_log` (id INT AUTO_INCREMENT PRIMARY KEY, timestamp DATETIME NOT NULL, user_id INT, action_type VARCHAR(255) NOT NULL, details TEXT);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `admin_notifications` (id INT AUTO_INCREMENT PRIMARY KEY, message TEXT NOT NULL, timestamp DATETIME NOT NULL, is_read TINYINT(1) DEFAULT 0);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `dogs` (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, breed VARCHAR(255), birthdate DATE, owner_id INT, status VARCHAR(50), notes TEXT);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `bug_reports` (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, title TEXT NOT NULL, description TEXT NOT NULL, status VARCHAR(50) DEFAULT 'Offen', admin_comment TEXT, user_feedback TEXT, feedback_requested TINYINT(1) DEFAULT 0, notified TINYINT(1) DEFAULT 0);")
        execute_create_table_if_not_exists("""
                                           CREATE TABLE IF NOT EXISTS `tasks`
                                           (
                                               `id`
                                               INT
                                               AUTO_INCREMENT
                                               PRIMARY
                                               KEY,
                                               `creator_admin_id`
                                               INT
                                               NOT
                                               NULL,
                                               `timestamp`
                                               DATETIME
                                               DEFAULT
                                               CURRENT_TIMESTAMP,
                                               `title`
                                               TEXT
                                               NOT
                                               NULL,
                                               `description`
                                               TEXT
                                               NOT
                                               NULL,
                                               `status`
                                               VARCHAR
                                           (
                                               50
                                           ) DEFAULT 'Neu',
                                               `category` VARCHAR
                                           (
                                               100
                                           ),
                                               `priority` VARCHAR
                                           (
                                               50
                                           ) DEFAULT 'Mittel',
                                               `admin_notes` TEXT,
                                               `archived` TINYINT
                                           (
                                               1
                                           ) DEFAULT 0,
                                               FOREIGN KEY
                                           (
                                               `creator_admin_id`
                                           ) REFERENCES `users`
                                           (
                                               `id`
                                           ) ON DELETE CASCADE
                                               );
                                           """)
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `password_reset_requests` (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL UNIQUE, token VARCHAR(255) NOT NULL UNIQUE, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `vacation_requests` (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL, days_requested INT NOT NULL, status VARCHAR(50) DEFAULT 'Ausstehend', submission_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, approval_timestamp DATETIME DEFAULT NULL, approved_by INT DEFAULT NULL, rejection_reason TEXT, notified TINYINT(1) DEFAULT 0, archived TINYINT(1) DEFAULT 0);")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `wunschfrei_requests` (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, request_date DATE NOT NULL, requested_shift VARCHAR(10) DEFAULT 'WF', status VARCHAR(50) DEFAULT 'Ausstehend', requested_by VARCHAR(50) DEFAULT 'User', submission_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, approval_timestamp DATETIME DEFAULT NULL, rejection_reason TEXT, notified TINYINT(1) DEFAULT 0, UNIQUE KEY `user_date_request` (`user_id`,`request_date`));")
        execute_create_table_if_not_exists(
            "CREATE TABLE IF NOT EXISTS `user_order` (user_id INT PRIMARY KEY, sort_order INT NOT NULL, is_visible TINYINT(1) DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);")
        execute_create_table_if_not_exists("""
                                           CREATE TABLE IF NOT EXISTS `shift_locks`
                                           (
                                               `user_id`
                                               INT
                                               NOT
                                               NULL,
                                               `shift_date`
                                               DATE
                                               NOT
                                               NULL,
                                               `shift_abbrev`
                                               VARCHAR
                                           (
                                               10
                                           ) NOT NULL,
                                               `secured_by_admin_id` INT DEFAULT NULL,
                                               `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
                                               PRIMARY KEY
                                           (
                                               `user_id`,
                                               `shift_date`
                                           ),
                                               FOREIGN KEY
                                           (
                                               `user_id`
                                           ) REFERENCES `users`
                                           (
                                               `id`
                                           ) ON DELETE CASCADE,
                                               FOREIGN KEY
                                           (
                                               `secured_by_admin_id`
                                           ) REFERENCES `users`
                                           (
                                               `id`
                                           )
                                             ON DELETE SET NULL
                                               );
                                           """)

        # 🐞 BUGFIX: Fehlende Tabelle 'special_appointments' hinzugefügt
        execute_create_table_if_not_exists("""
                                           CREATE TABLE IF NOT EXISTS `special_appointments`
                                           (
                                               `appointment_date`
                                               DATE
                                               NOT
                                               NULL,
                                               `appointment_type`
                                               VARCHAR
                                           (
                                               255
                                           ) NOT NULL,
                                               `description` TEXT,
                                               PRIMARY KEY
                                           (
                                               `appointment_date`,
                                               `appointment_type`
                                           )
                                               );
                                           """)

        # --- Index hinzufügen (ruft Helfer auf) ---
        _add_index_if_not_exists(cursor, "shift_schedule", "idx_shift_date_user", "`shift_date`, `user_id`")
        _add_index_if_not_exists(cursor, "tasks", "idx_tasks_creator", "`creator_admin_id`")
        _add_index_if_not_exists(cursor, "users", "idx_user_status",
                                 "`is_approved`, `is_archived`, `activation_date`, `archived_date`")
        _add_index_if_not_exists(cursor, "users", "idx_user_auth", "`vorname`(255), `name`(255), `password_hash`(255)")
        _add_index_if_not_exists(cursor, "chat_messages", "idx_chat_recipient_read", "`recipient_id`, `is_read`")

        # --- Spalten hinzufügen (ruft Helfer auf) ---
        _add_column_if_not_exists(cursor, db_name, "users", "entry_date", "DATE DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "last_seen", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "is_approved", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "users", "is_archived", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "users", "archived_date", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "activation_date", "DATETIME NULL DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "shift_types", "check_for_understaffing", "TINYINT(1) DEFAULT 0")

        conn.commit()
        print("Datenbank-Tabellen erfolgreich initialisiert/überprüft.")
    except mysql.connector.Error as e:
        print(f"Fehler bei der Initialisierung der Tabellen: {e}")
        conn.rollback()  # Rollback bei Fehlern
        raise  # Fehler weiterwerfen
    finally:
        if cursor:
            cursor.close()