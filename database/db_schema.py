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
        cursor_server.execute(
            f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"Datenbank '{db_name}' sichergestellt.")
    except mysql.connector.Error as e:
        print(f"FEHLER: Datenbank '{db_name}' konnte nicht erstellt werden: {e}")
        raise
    finally:
        if 'cursor_server' in locals(): cursor_server.close()
        if 'conn_server' in locals() and conn_server.is_connected(): conn_server.close()

    # 2. Tabellen-Erstellung und Migration (im Connection-Pool)
    try:
        # --- KORREKTUR (Regel 1): TypeError (tuple indices...) behoben ---
        # Der Cursor MUSS Dictionaries zurückgeben, damit db_schema_helpers.py funktioniert.
        cursor = conn.cursor(dictionary=True)
        # --- ENDE KORREKTUR ---

        cursor.execute(f"USE {db_name}")

        # --- Tabellen-Definitionen (inkl. Hinzufügungen) ---

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS users
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           username
                           VARCHAR
                       (
                           255
                       ) NOT NULL UNIQUE,
                           password_hash VARCHAR
                       (
                           255
                       ) NOT NULL,
                           role ENUM
                       (
                           'Mitarbeiter',
                           'Admin',
                           'Guest'
                       ) NOT NULL DEFAULT 'Guest',
                           vorname VARCHAR
                       (
                           255
                       ),
                           name VARCHAR
                       (
                           255
                       ),
                           email VARCHAR
                       (
                           255
                       ) UNIQUE,
                           telefon VARCHAR
                       (
                           255
                       ),
                           geburtstag DATE,
                           diensthund VARCHAR
                       (
                           255
                       ),
                           urlaub_gesamt INT DEFAULT 0,
                           urlaub_rest INT DEFAULT 0,
                           last_ausbildung DATE,
                           last_schiessen DATE,
                           reset_token VARCHAR
                       (
                           255
                       ) DEFAULT NULL,
                           reset_token_expiry DATETIME DEFAULT NULL,
                           entry_date DATE DEFAULT NULL,
                           last_seen DATETIME DEFAULT NULL,
                           is_approved TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           is_archived TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           archived_date DATETIME DEFAULT NULL,
                           activation_date DATETIME NULL DEFAULT NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
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
                       ) NOT NULL UNIQUE,
                           breed VARCHAR
                       (
                           255
                       ),
                           birth_date DATE,
                           chip_number VARCHAR
                       (
                           255
                       ) UNIQUE,
                           acquisition_date DATE,
                           departure_date DATE,
                           last_dpo_date DATE,
                           vaccination_info TEXT,
                           image_blob MEDIUMBLOB DEFAULT NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS shifts
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
                           datum
                           DATE
                           NOT
                           NULL,
                           schicht
                           VARCHAR
                       (
                           255
                       ),
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        # (Andere Tabellen-Definitionen bleiben unverändert...)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS shift_types
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
                       ) NOT NULL UNIQUE,
                           abbreviation VARCHAR
                       (
                           10
                       ) NOT NULL UNIQUE,
                           color VARCHAR
                       (
                           7
                       ) DEFAULT '#FFFFFF',
                           category ENUM
                       (
                           'Dienst',
                           'Frei',
                           'Krank',
                           'Urlaub',
                           'Sonstiges'
                       ) DEFAULT 'Dienst',
                           is_default TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           is_changeable TINYINT
                       (
                           1
                       ) DEFAULT 1,
                           affects_vacation TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           counts_as_work TINYINT
                       (
                           1
                       ) DEFAULT 1
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS requests
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
                           DATE
                           NOT
                           NULL,
                           requested_shift
                           VARCHAR
                       (
                           50
                       ),
                           reason TEXT,
                           status ENUM
                       (
                           'Ausstehend',
                           'Genehmigt',
                           'Abgelehnt'
                       ) DEFAULT 'Ausstehend',
                           admin_id INT DEFAULT NULL,
                           rejection_reason TEXT,
                           created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE,
                           FOREIGN KEY
                       (
                           admin_id
                       ) REFERENCES users
                       (
                           id
                       )
                         ON DELETE SET NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
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
                           DATE
                           NOT
                           NULL,
                           end_date
                           DATE
                           NOT
                           NULL,
                           days_requested
                           INT
                           NOT
                           NULL,
                           status
                           ENUM
                       (
                           'Ausstehend',
                           'Genehmigt',
                           'Abgelehnt',
                           'Storniert'
                       ) DEFAULT 'Ausstehend',
                           admin_id INT DEFAULT NULL,
                           created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                           archived TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE,
                           FOREIGN KEY
                       (
                           admin_id
                       ) REFERENCES users
                       (
                           id
                       )
                         ON DELETE SET NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
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
                           timestamp
                           DATETIME
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           title
                           VARCHAR
                       (
                           255
                       ) NOT NULL,
                           description TEXT NOT NULL,
                           category VARCHAR
                       (
                           100
                       ),
                           status VARCHAR
                       (
                           50
                       ) DEFAULT 'Neu',
                           admin_notes TEXT,
                           user_notes TEXT,
                           archived TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS request_locks
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           year
                           INT
                           NOT
                           NULL,
                           month
                           INT
                           NOT
                           NULL,
                           day
                           INT
                           NOT
                           NULL,
                           reason
                           VARCHAR
                       (
                           255
                       ),
                           created_by_id INT,
                           created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                           UNIQUE KEY
                       (
                           year,
                           month,
                           day
                       ),
                           FOREIGN KEY
                       (
                           created_by_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE SET NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS app_config
                       (
                           config_key
                           VARCHAR
                       (
                           255
                       ) PRIMARY KEY,
                           config_value JSON,
                           last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS admin_logs
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           timestamp
                           DATETIME
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           user_id
                           INT,
                           action
                           VARCHAR
                       (
                           255
                       ) NOT NULL,
                           target_type VARCHAR
                       (
                           50
                       ),
                           target_id INT,
                           details TEXT,
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE SET NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS chat_messages
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           sender_id
                           INT
                           NOT
                           NULL,
                           recipient_id
                           INT
                           NOT
                           NULL,
                           message
                           TEXT
                           NOT
                           NULL,
                           timestamp
                           DATETIME
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           is_read
                           TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           FOREIGN KEY
                       (
                           sender_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE,
                           FOREIGN KEY
                       (
                           recipient_id
                       ) REFERENCES users
                       (
                           id
                       )
                         ON DELETE CASCADE
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS participation
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
                           event_type
                           VARCHAR
                       (
                           100
                       ) NOT NULL,
                           event_date DATE NOT NULL,
                           hours DECIMAL
                       (
                           5,
                           2
                       ),
                           description TEXT,
                           created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                           created_by_id INT,
                           FOREIGN KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE CASCADE,
                           FOREIGN KEY
                       (
                           created_by_id
                       ) REFERENCES users
                       (
                           id
                       )
                         ON DELETE SET NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS tasks
                       (
                           id
                           INT
                           AUTO_INCREMENT
                           PRIMARY
                           KEY,
                           creator_admin_id
                           INT,
                           title
                           VARCHAR
                       (
                           255
                       ) NOT NULL,
                           description TEXT,
                           category VARCHAR
                       (
                           100
                       ),
                           priority VARCHAR
                       (
                           50
                       ) DEFAULT 'Mittel',
                           status VARCHAR
                       (
                           50
                       ) DEFAULT 'Offen',
                           timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                           admin_notes TEXT,
                           archived TINYINT
                       (
                           1
                       ) DEFAULT 0,
                           FOREIGN KEY
                       (
                           creator_admin_id
                       ) REFERENCES users
                       (
                           id
                       ) ON DELETE SET NULL
                           ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE =utf8mb4_unicode_ci;
                       """)

        print("Alle Tabellen sichergestellt.")

        # --- Migration: Indizes hinzufügen (ruft Helfer auf) ---
        _add_index_if_not_exists(cursor, "shifts", "idx_user_datum", "`user_id`, `datum`")

        # --- KORREKTUR (Regel 1): Längenangabe (50) für ENUM (als VARCHAR behandelt) hinzugefügt ---
        _add_index_if_not_exists(cursor, "requests", "idx_user_status_date", "`user_id`, `status`(50), `request_date`")
        _add_index_if_not_exists(cursor, "vacation_requests", "idx_user_status_archived",
                                 "`user_id`, `status`(50), `archived`")
        # --- ENDE KORREKTUR ---

        # --- KORREKTUR (Regel 1): Fehler 1170 behoben durch Hinzufügen einer Längenangabe (50) ---
        _add_index_if_not_exists(cursor, "bug_reports", "idx_status_archived", "`status`(50), `archived`")
        # --- ENDE KORREKTUR ---

        _add_index_if_not_exists(cursor, "users", "idx_user_status",
                                 "`is_approved`, `is_archived`, `activation_date`, `archived_date`")
        _add_index_if_not_exists(cursor, "users", "idx_user_auth", "`vorname`(255), `name`(255), `password_hash`(255)")
        _add_index_if_not_exists(cursor, "chat_messages", "idx_chat_recipient_read", "`recipient_id`, `is_read`")

        # --- Migration: Spalten hinzufügen (ruft Helfer auf) ---
        _add_column_if_not_exists(cursor, db_name, "users", "entry_date", "DATE DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "last_seen", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "is_approved", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "users", "is_archived", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "users", "archived_date", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "activation_date", "DATETIME NULL DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "reset_token", "VARCHAR(255) DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "users", "reset_token_expiry", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, db_name, "vacation_requests", "archived", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "bug_reports", "user_notes", "TEXT")
        _add_column_if_not_exists(cursor, db_name, "bug_reports", "archived", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "shift_types", "is_changeable", "TINYINT(1) DEFAULT 1")
        _add_column_if_not_exists(cursor, db_name, "shift_types", "affects_vacation", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, db_name, "shift_types", "counts_as_work", "TINYINT(1) DEFAULT 1")
        _add_column_if_not_exists(cursor, db_name, "app_config", "last_modified",
                                  "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
        _add_column_if_not_exists(cursor, db_name, "requests", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

        # --- NEU (Regel 1): Spalte für Hundebilder hinzufügen ---
        _add_column_if_not_exists(cursor, db_name, "dogs", "image_blob", "MEDIUMBLOB DEFAULT NULL")

        print("Datenbank-Migrationen abgeschlossen.")

    except mysql.connector.Error as e:
        print(f"FEHLER bei DB-Initialisierung/Migration (Tabelle/Spalte/Index): {e}")
        # conn.rollback() # Nicht nötig, da DDL oft impliziten Commit auslöst
        raise
    except Exception as e:
        print(f"Allgemeiner FEHLER bei _run_initialize_db: {e}")
        raise
    finally:
        if 'cursor' in locals(): cursor.close()
        # Die Verbindung wird in create_connection() geschlossen