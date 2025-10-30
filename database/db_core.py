# database/db_core.py
import mysql.connector
from mysql.connector import pooling
import hashlib
import json
from datetime import datetime, date  # 'date' hinzugefügt
from collections import defaultdict
import sys
import os
import threading  # NEU: Importiert für Thread-sichere Initialisierung

# ==============================================================================
# 💥 DATENBANK-KONFIGURATION WIRD JETZT AUS 'db_config.json' GELADEN 💥
# ==============================================================================

CONFIG_FILE_NAME = "db_config.json"


def load_db_config():
    """Lädt die DB-Konfiguration aus einer externen JSON-Datei."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))

    if not hasattr(sys, '_MEIPASS'):
        base_path = os.path.dirname(base_path)

    config_path = os.path.join(base_path, CONFIG_FILE_NAME)

    default_config = {
        "host": "IHRE_SERVER_IP_HIER",
        "user": "planer_user",
        "password": "IhrPasswortHier",
        "database": "planer_db",
        "raise_on_warnings": False,  # Bleibt False
        "auth_plugin": "mysql_native_password"
    }

    if not os.path.exists(config_path):
        print(f"FEHLER: Konfigurationsdatei nicht gefunden.")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            msg = (f"Eine Standard-Konfigurationsdatei wurde erstellt: {config_path}\n\n"
                   "BITTE BEARBEITEN SIE DIESE DATEI mit Ihren Datenbank-Zugangsdaten und starten Sie das Programm neu.")
            print(msg)
            raise ConnectionError(msg)
        except Exception as e:
            msg = f"Konnte keine Standard-Konfigurationsdatei erstellen: {e}\nBitte erstellen Sie die Datei 'db_config.json' manuell im Programmverzeichnis."
            print(msg)
            raise ConnectionError(msg)

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        config["raise_on_warnings"] = False

        if config["host"] == "IHRE_SERVER_IP_HIER" or config["password"] == "IhrPasswortHier":
            msg = f"BITTE BEARBEITEN SIE 'db_config.json' mit Ihren Datenbank-Zugangsdaten."
            print(msg)
            raise ConnectionError(msg)

        return config
    except json.JSONDecodeError:
        msg = f"FEHLER: Die Datei '{config_path}' enthält ungültiges JSON."
        print(msg)
        raise ConnectionError(msg)
    except KeyError:
        msg = f"FEHLER: Die Datei '{config_path}' ist unvollständig. Stellen Sie sicher, dass alle Schlüssel vorhanden sind."
        print(msg)
        raise ConnectionError(msg)
    except Exception as e:
        msg = f"Ein unerwarteter Fehler beim Lesen der Konfiguration ist aufgetreten: {e}"
        print(msg)
        raise ConnectionError(msg)


try:
    DB_CONFIG = load_db_config()
except Exception as e:
    DB_CONFIG = None
    raise

# --- INNOVATION: Lazy-Loading des Connection-Pools ---

# Global-Variablen für den Pool und ein Lock
db_pool = None
_pool_init_lock = threading.Lock()
_db_initialized = False  # NEU: Flag, um initialize_db() nur einmal auszuführen

# --- INNOVATION 2: Cache für Konfigurationen ---
_config_cache = {}
# ---------------------------------------------

# ==============================================================================
# --- HILFSFUNKTIONEN (AN DEN ANFANG VERSCHOBEN, UM IMPORTFEHLER ZU BEHEBEN) ---
# ==============================================================================

ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}
MIN_STAFFING_RULES_CONFIG_KEY = "MIN_STAFFING_RULES"
REQUEST_LOCKS_CONFIG_KEY = "REQUEST_LOCKS"
ADMIN_MENU_CONFIG_KEY = "ADMIN_MENU_CONFIG"
USER_TAB_ORDER_CONFIG_KEY = "USER_TAB_ORDER"
ADMIN_TAB_ORDER_CONFIG_KEY = "ADMIN_TAB_ORDER"
VACATION_RULES_CONFIG_KEY = "VACATION_RULES"


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def _log_activity(cursor, user_id, action_type, details):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (%s, %s, %s, %s)",
                   (timestamp, user_id, action_type, details))


def _create_admin_notification(cursor, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO admin_notifications (message, timestamp) VALUES (%s, %s)", (message, timestamp))


def get_vacation_days_for_tenure(entry_date_obj, default_days=30):
    """
    Berechnet den Urlaubsanspruch basierend auf der Betriebszugehörigkeit.
    Nutzt (jetzt gecachtes) load_config_json.
    """
    if not entry_date_obj:
        return default_days
    if isinstance(entry_date_obj, str):
        try:
            entry_date_obj = datetime.strptime(entry_date_obj, '%Y-%m-%d').date()
        except ValueError:
            print(f"Warnung: Ungültiges entry_date-Format: {entry_date_obj}. Verwende Standard-Urlaubstage.")
            return default_days
    elif isinstance(entry_date_obj, datetime):
        entry_date_obj = entry_date_obj.date()
    elif not isinstance(entry_date_obj, date):
        print(f"Warnung: Ungültiger entry_date-Typ: {type(entry_date_obj)}. Verwende Standard-Urlaubstage.")
        return default_days

    # Nutzt die gecachte Ladefunktion
    rules_config = load_config_json(VACATION_RULES_CONFIG_KEY)
    if not rules_config or not isinstance(rules_config, list):
        return default_days

    try:
        rules = sorted(
            [{"years": int(r["years"]), "days": int(r["days"])} for r in rules_config],
            key=lambda x: x["years"],
            reverse=True
        )
    except (ValueError, KeyError, TypeError) as e:
        print(f"Fehler beim Parsen der Urlaubsregeln: {e}. Verwende Standard-Urlaubstage.")
        return default_days

    today = date.today()
    tenure_years = today.year - entry_date_obj.year
    if (today.month, today.day) < (entry_date_obj.month, entry_date_obj.day):
        tenure_years -= 1

    for rule in rules:
        if tenure_years >= rule["years"]:
            return rule["days"]

    return default_days


# ==============================================================================
# --- POOL- UND VERBINDUNGS-LOGIK (LAZY LOADING) ---
# ==============================================================================

def create_connection():
    """
    Stellt eine Verbindung aus dem Pool her.
    Initialisiert den Pool "lazy" (erst bei der ersten Anfrage),
    um den Programmstart zu beschleunigen.
    Initialisiert das DB-Schema (Tabellen) einmalig nach Pool-Erstellung.
    """
    global db_pool, _db_initialized

    # 1. Schnelle Prüfung (ohne Lock), ob der Pool bereits existiert.
    if db_pool is not None:
        try:
            return db_pool.get_connection()
        except mysql.connector.Error as err:
            print(f"❌ Fehler beim Abrufen einer Verbindung aus dem Pool: {err}")
            return None
        except Exception as e:
            # Fängt seltene Fälle ab, z.B. wenn der Pool geschlossen wurde
            print(f"❌ Unerwarteter Fehler beim Abrufen der Verbindung: {e}")
            db_pool = None  # Pool zurücksetzen, um Neuerstellung zu erzwingen
            return None

    # 2. Pool existiert nicht. Wir müssen ihn erstellen (Thread-sicher).
    with _pool_init_lock:
        # 3. Erneute Prüfung (Double-Checked Locking)
        # Falls ein anderer Thread den Pool erstellt hat, während wir auf das Lock gewartet haben.
        if db_pool is not None:
            try:
                return db_pool.get_connection()
            except mysql.connector.Error as err:
                print(f"❌ Fehler beim Abrufen einer Verbindung aus dem Pool (nach Lock): {err}")
                return None

        # 4. Der Pool muss jetzt wirklich erstellt werden.
        try:
            print("Versuche, den Datenbank-Connection-Pool (lazy) zu erstellen...")
            if DB_CONFIG is None:
                raise ConnectionError("DB_CONFIG wurde aufgrund eines Fehlers nicht geladen.")

            # (Wir verwenden pool_size=10, wie in der letzten Optimierung)
            db_pool = pooling.MySQLConnectionPool(pool_name="dhf_pool",
                                                  pool_size=10,
                                                  **DB_CONFIG)
            print("✅ Datenbank-Connection-Pool erfolgreich erstellt.")

            # 5. NEU: Datenbank-Schema (Tabellen) initialisieren
            #    Wir tun dies hier, da dies der erste garantierte Punkt ist,
            #    an dem der Pool existiert.
            if not _db_initialized:
                print("[DB Core] Führe erstmalige Schema-Initialisierung (initialize_db) durch...")
                conn = None
                try:
                    # Wir müssen eine temporäre Verbindung für initialize_db holen
                    conn = db_pool.get_connection()
                    # initialize_db() benötigt eine *offene* Verbindung
                    _run_initialize_db(conn)  # (Verschobene Logik)
                    _db_initialized = True
                    print("✅ Schema-Initialisierung abgeschlossen.")
                except Exception as init_e:
                    # Wenn das Schema fehlschlägt, ist die DB unbrauchbar.
                    print(f"❌ KRITISCHER FEHLER bei initialize_db: {init_e}")
                    db_pool = None  # Pool bei Fehler wieder zerstören
                    raise init_e  # Fehler weiterwerfen
                finally:
                    if conn and conn.is_connected():
                        conn.close()

            # 6. Finale Verbindung zurückgeben
            return db_pool.get_connection()

        except mysql.connector.Error as err:
            print(f"❌ KRITISCHER FEHLER beim Erstellen des Connection-Pools: {err}")
            print("Überprüfen Sie Ihre 'db_config.json' und die Erreichbarkeit der Datenbank.")
            db_pool = None  # Sicherstellen, dass es None bleibt bei Fehler
            raise ConnectionError(f"Fehler beim Erstellen des DB-Pools: {err}")
        except Exception as e:
            print(f"❌ KRITISCHER FEHLER (Allgemein) beim Initialisieren von db_core: {e}")
            db_pool = None
            raise


def prewarm_connection_pool():
    """
    Ruft create_connection() einmal auf, um den Pool und das Schema im Hintergrund
    zu initialisieren, während der Benutzer im Login-Fenster ist.
    """
    global _db_initialized
    if db_pool is not None and _db_initialized:
        print("[DB Core] Pre-Warming übersprungen (Pool & Schema bereits initialisiert).")
        return

    print("[DB Core] Starte Pre-Warming des Connection-Pools im Hintergrund...")
    conn = None
    try:
        conn = create_connection()
        if conn:
            print("[DB Core] Pre-Warming erfolgreich. Pool und Schema sind jetzt initialisiert.")
        else:
            print("[DB Core] Pre-Warming fehlgeschlagen (create_connection gab None zurück).")
    except Exception as e:
        # Fängt Fehler ab, wenn z.B. die DB nicht erreichbar ist.
        # Der Haupt-Login-Versuch wird den Fehler dann erneut (korrekt) anzeigen.
        print(f"[DB Core] Pre-Warming THREAD FEHLER: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()  # Wichtig: Verbindung sofort zurück in den Pool geben.


def close_pool():
    print("Der Datenbank-Connection-Pool wird bei Programmende verwaltet.")


# ==============================================================================
# --- SCHEMA-INITIALISIERUNG UND MIGRATION ---
# ==============================================================================

def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    if DB_CONFIG is None:
        raise ConnectionError("Datenbank-Konfiguration nicht geladen.")
    db_name = DB_CONFIG.get('database')
    if not db_name:
        raise ValueError("Datenbank-Name nicht in DB_CONFIG gefunden.")

    cursor.execute(f"""
        SELECT COUNT(*) AS count_result FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (db_name, table_name, column_name))

    result_dict = cursor.fetchone()

    if result_dict and result_dict['count_result'] == 0:
        print(f"Füge Spalte '{column_name}' zur Tabelle '{table_name}' hinzu...")
        # Backticks um Tabellen- und Spaltennamen für Sicherheit
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_type}")


def _add_index_if_not_exists(cursor, table_name, index_name, columns):
    cursor.execute(f"""
        SELECT COUNT(*) AS count_result FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}' AND INDEX_NAME = '{index_name}'
    """)

    result_dict = cursor.fetchone()

    if result_dict and result_dict['count_result'] == 0:
        print(f"Füge Index '{index_name}' zur Tabelle '{table_name}' hinzu...")
        # Backticks um Index- und Tabellennamen
        cursor.execute(f"CREATE INDEX `{index_name}` ON `{table_name}` ({columns})")


def _run_initialize_db(conn):
    """
    Führt die eigentliche Schema-Initialisierung durch.
    Wird jetzt von create_connection() beim ersten Start aufgerufen.
    Nimmt eine *existierende* Verbindung entgegen.
    """
    if DB_CONFIG is None:
        raise ConnectionError("DB-Init fehlgeschlagen: Konfiguration nicht geladen.")

    config_init = DB_CONFIG.copy()
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
                    raise e  # Wichtig: Nur `raise` verwenden, um den ursprünglichen Traceback zu behalten

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
                                               int
                                               NOT
                                               NULL
                                               AUTO_INCREMENT,
                                               `name`
                                               varchar
                                           (
                                               255
                                           ) NOT NULL,
                                               `abbreviation` varchar
                                           (
                                               10
                                           ) NOT NULL,
                                               `hours` decimal
                                           (
                                               4,
                                               2
                                           ) DEFAULT NULL,
                                               `description` text,
                                               `color` varchar
                                           (
                                               7
                                           ) DEFAULT '#FFFFFF',
                                               `start_time` time DEFAULT NULL,
                                               `end_time` time DEFAULT NULL,
                                               `check_for_understaffing` tinyint
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
                                               varchar
                                           (
                                               10
                                           ) NOT NULL,
                                               `sort_order` int NOT NULL,
                                               `is_visible` tinyint
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

        # --- Index hinzufügen ---
        _add_index_if_not_exists(cursor, "shift_schedule", "idx_shift_date_user", "`shift_date`, `user_id`")
        _add_index_if_not_exists(cursor, "tasks", "idx_tasks_creator", "`creator_admin_id`")
        _add_index_if_not_exists(cursor, "users", "idx_user_status",
                                 "`is_approved`, `is_archived`, `activation_date`, `archived_date`")
        _add_index_if_not_exists(cursor, "users", "idx_user_auth", "`vorname`(255), `name`(255), `password_hash`(255)")
        _add_index_if_not_exists(cursor, "chat_messages", "idx_chat_recipient_read", "`recipient_id`, `is_read`")

        # --- Spalten hinzufügen (Migrationslogik) ---
        _add_column_if_not_exists(cursor, "users", "entry_date", "DATE DEFAULT NULL")
        _add_column_if_not_exists(cursor, "users", "last_seen", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, "users", "is_approved", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, "users", "is_archived", "TINYINT(1) DEFAULT 0")
        _add_column_if_not_exists(cursor, "users", "archived_date", "DATETIME DEFAULT NULL")
        _add_column_if_not_exists(cursor, "users", "activation_date", "DATETIME NULL DEFAULT NULL")
        _add_column_if_not_exists(cursor, "shift_types", "check_for_understaffing", "TINYINT(1) DEFAULT 0")

        conn.commit()
        print("Datenbank-Tabellen erfolgreich initialisiert/überprüft.")
    except mysql.connector.Error as e:
        print(f"Fehler bei der Initialisierung der Tabellen: {e}")
        conn.rollback()  # Rollback bei Fehlern
        raise  # Fehler weiterwerfen
    finally:
        if cursor:
            cursor.close()


def initialize_db():
    """
    Öffentlicher Wrapper, der sicherstellt, dass die Initialisierung
    über den 'create_connection'-Mechanismus läuft.
    """
    print("Starte öffentliche initialize_db()...")
    conn = create_connection()
    if conn:
        print("DB-Verbindung für initialize_db() erhalten, Schema sollte bereits initialisiert sein.")
        conn.close()
    else:
        print("Fehler beim Abrufen der DB-Verbindung für initialize_db().")
        raise ConnectionError("DB-Initialisierung fehlgeschlagen.")


# ==============================================================================
# --- KONFIGURATIONS- UND FREQUENZ-FUNKTIONEN (ANGEPASST MIT CACHING) ---
# ==============================================================================

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


def save_shift_frequency(frequency_dict):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_frequency")
        if frequency_dict:
            query = "INSERT INTO shift_frequency (shift_abbrev, count) VALUES (%s, %s)"
            data_to_insert = list(frequency_dict.items())
            cursor.executemany(query, data_to_insert)
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_shift_frequency: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def load_shift_frequency():
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
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_frequency")
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on reset_shift_frequency: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def save_special_appointment(date_str, appointment_type, description=""):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = "INSERT INTO special_appointments (appointment_date, appointment_type, description) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE appointment_type=VALUES(appointment_type), description=VALUES(description)"
        cursor.execute(query, (date_str, appointment_type, description))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        if e.errno == 1146:
            print("FEHLER: Tabelle 'special_appointments' existiert nicht. Bitte in initialize_db() hinzufügen.")
        else:
            print(f"DB Error on save_special_appointment: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def delete_special_appointment(date_str, appointment_type):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = "DELETE FROM special_appointments WHERE appointment_date = %s AND appointment_type = %s"
        cursor.execute(query, (date_str, appointment_type))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        if e.errno == 1146:
            print("FEHLER: Tabelle 'special_appointments' existiert nicht.")
        else:
            print(f"DB Error on delete_special_appointment: {e}")
        conn.rollback();
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_special_appointments():
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM special_appointments")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        if e.errno == 1146:
            print("FEHLER: Tabelle 'special_appointments' existiert nicht.")
            return []
        print(f"DB Error on get_special_appointments: {e}");
        return []
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


# ==============================================================================
# --- DB-FIX-FUNKTIONEN (unverändert) ---
# ==============================================================================

def run_db_fix_approve_all_users():
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_approved = 1 WHERE is_approved = 0")
        updated_rows = cursor.rowcount
        conn.commit()
        return True, f"{updated_rows} bestehende Benutzer wurden erfolgreich freigeschaltet."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Ein Datenbankfehler ist aufgetreten: {e}"
    except Exception as e:
        conn.rollback();
        return False, f"Ein unerwarteter Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_is_approved():
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        _add_column_if_not_exists(cursor, "users", "is_approved", "TINYINT(1) DEFAULT 0")
        conn.commit()
        return True, "DB-Update (is_approved Spalte) erfolgreich."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Ein Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_v1():
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        _add_column_if_not_exists(cursor, "users", "last_seen", "DATETIME DEFAULT NULL")
        conn.commit()
        return True, "DB-Update für Chat erfolgreich."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Ein Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_add_is_archived():
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        _add_column_if_not_exists(cursor, "users", "is_archived", "TINYINT(1) DEFAULT 0")
        conn.commit()
        return True, "DB-Update (is_archived Spalte) erfolgreich."
    except Exception as e:
        conn.rollback();
        print(f"Fehler: {e}");
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_add_archived_date():
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        _add_column_if_not_exists(cursor, "users", "archived_date", "DATETIME DEFAULT NULL")
        conn.commit()
        return True, "DB-Update (archived_date Spalte) erfolgreich."
    except Exception as e:
        conn.rollback();
        print(f"Fehler: {e}");
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_activation_date():
    """
    Fügt die Spalte 'activation_date' zur 'users'-Tabelle hinzu,
    um zukünftige Aktivierungen zu steuern.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE users ADD activation_date DATETIME NULL DEFAULT NULL AFTER entry_date")
        conn.commit()
        return True, "Datenbank-Update für 'activation_date' erfolgreich durchgeführt."
    except mysql.connector.Error as e:
        conn.rollback()
        if e.errno == 1060:  # Duplicate column name
            return True, "Spalte 'activation_date' existiert bereits. Keine Aktion erforderlich."
        print(f"Fehler beim Hinzufügen von activation_date: {e}")
        return False, f"Fehler beim Update: {e}"
    except Exception as e:
        conn.rollback()
        print(f"Allgemeiner Fehler beim Hinzufügen von activation_date: {e}")
        return False, f"Allgemeiner Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()