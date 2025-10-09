# database/db_manager.py (MySQL Version - Datetime Konvertierung behoben)
import mysql.connector
from mysql.connector import errorcode
# importiere KEINEN CursorDict hier, um Versionsprobleme zu vermeiden
import hashlib
from datetime import date, datetime
import calendar

# --- MySQL CONNECTION PARAMETERS ---
DB_HOST = "127.0.0.1"
DB_USER = "rebi"
DB_PASS = "Qwe456ola!"
DATABASE_NAME = 'dhfplaner_db'  # Datenbankname zur besseren Unterscheidung von SQLite

# --- Authentifizierungs-Plugin für ältere MySQL-Installationen fixiert ---
AUTH_PLUGIN = 'caching_sha2_password'

ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}

# Globale Verbindungsvariablen
_CONNECTION = None


# _CURSOR_FACTORY wird nicht mehr benötigt

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_connection():
    """Stellt die Verbindung zur MySQL-Datenbank her."""
    global _CONNECTION
    try:
        if _CONNECTION and _CONNECTION.is_connected():
            return _CONNECTION

        # Explizites Setzen des Plugins, um Fehler 2059 zu umgehen
        _CONNECTION = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DATABASE_NAME,
            auth_plugin=AUTH_PLUGIN  # NEU HINZUGEFÜGT
        )
        return _CONNECTION
    except mysql.connector.Error as err:
        print(f"❌ MySQL-Verbindungsfehler: {err}")
        return None


def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """
    Führt eine SQL-Abfrage aus. Verwendet %s als Platzhalter. (Funktion in der MySQL-Version nicht mehr primär genutzt,
    aber als Fallback beibehalten. Die meisten Funktionen nutzen explizite Cursors.)
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    cursor = None
    try:
        # Hier wird der Standard-Cursor verwendet, der Tupel zurückgibt.
        cursor = conn.cursor()
        cursor.execute(query, params or ())

        if commit:
            conn.commit()

        if fetch_one:
            return True, cursor.fetchone()
        elif fetch_all:
            return True, cursor.fetchall()

        return True, cursor.rowcount

    except mysql.connector.Error as err:
        if conn and conn.is_connected():
            conn.rollback()
        return False, f"MySQL-Fehler: {err}"
    finally:
        if cursor:
            cursor.close()


def _create_database_if_not_exists():
    """Versucht, die Datenbank zu erstellen, falls sie nicht existiert."""
    try:
        # Auch für die temporäre Verbindung muss das Plugin gesetzt werden!
        temp_conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            auth_plugin=AUTH_PLUGIN  # NEU HINZUGEFÜGT
        )
        temp_cursor = temp_conn.cursor()
        # Erstellt die Datenbank, falls sie nicht existiert
        temp_cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        temp_conn.close()
        return True
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("❌ Fehler: Benutzername oder Passwort für MySQL ist falsch.")
        else:
            print(f"❌ Fehler bei der Datenbankerstellung: {err}")
        return False


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """(DEAKTIVIERT FÜR MYSQL) Die Spaltendefinitionen sind nun in initialize_db enthalten."""
    pass


def initialize_db():
    """Initialisiert die MySQL-Datenbank und erstellt alle Tabellen."""
    if not _create_database_if_not_exists():
        return

    conn = create_connection()
    if conn is None:
        print("Initialisierung fehlgeschlagen: Keine Verbindung zur Datenbank.")
        return

    try:
        cursor = conn.cursor()

        # Alle CREATE TABLE Statements in MySQL-Dialekt konvertiert
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(255) NOT NULL,
                vorname VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                geburtstag DATE,
                telefon VARCHAR(255),
                diensthund VARCHAR(255),
                urlaub_gesamt INT DEFAULT 30,
                urlaub_rest INT DEFAULT 30,
                entry_date DATE,
                has_seen_tutorial TINYINT DEFAULT 0,
                UNIQUE KEY unique_user (vorname, name)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacation_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(255) NOT NULL,
                request_date DATE NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wunschfrei_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                request_date DATE NOT NULL,
                status VARCHAR(255) NOT NULL DEFAULT 'Ausstehend',
                notified TINYINT DEFAULT 0,
                rejection_reason TEXT,
                requested_shift VARCHAR(10),
                UNIQUE KEY unique_request (user_id, request_date),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dogs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                breed VARCHAR(255),
                birth_date DATE,
                chip_number VARCHAR(255) UNIQUE,
                acquisition_date DATE,
                departure_date DATE,
                last_dpo_date DATE,
                vaccination_info TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_types (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                abbreviation VARCHAR(10) UNIQUE NOT NULL,
                hours DECIMAL(4, 2) NOT NULL,
                description TEXT,
                color VARCHAR(7) DEFAULT '#FFFFFF',
                start_time TIME,
                end_time TIME
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_schedule (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                shift_date DATE NOT NULL,
                shift_abbrev VARCHAR(10) NOT NULL,
                UNIQUE KEY unique_shift (user_id, shift_date),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (shift_abbrev) REFERENCES shift_types (abbreviation) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_order (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                sort_order INT NOT NULL,
                is_visible TINYINT DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_order (
                id INT AUTO_INCREMENT PRIMARY KEY,
                abbreviation VARCHAR(10) NOT NULL UNIQUE,
                sort_order INT NOT NULL,
                is_visible TINYINT DEFAULT 1,
                check_for_understaffing TINYINT DEFAULT 0
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                user_id INT,
                action_type VARCHAR(255) NOT NULL,
                details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message TEXT NOT NULL,
                is_read TINYINT NOT NULL DEFAULT 0,
                timestamp DATETIME NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bug_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                status VARCHAR(255) NOT NULL DEFAULT 'Neu',
                is_read TINYINT NOT NULL DEFAULT 0,
                user_notified TINYINT NOT NULL DEFAULT 1,
                archived TINYINT NOT NULL DEFAULT 0,
                admin_notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)

        conn.commit()
    except mysql.connector.Error as e:
        print(f"Initialisierungsfehler bei CREATE TABLE: {e}")
    finally:
        cursor.close()


# -------------------- ACTIVITY LOG & NOTIFICATIONS (MySQL implementation) --------------------

def _log_activity(cursor, user_id, action_type, details):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (%s, %s, %s, %s)",
        (timestamp, user_id, action_type, details)
    )


def _create_admin_notification(cursor, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO admin_notifications (message, timestamp) VALUES (%s, %s)",
        (message, timestamp)
    )


def get_unread_admin_notifications():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, message FROM admin_notifications WHERE is_read = 0 ORDER BY timestamp ASC")
        return cursor.fetchall()
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def mark_admin_notifications_as_read(notification_ids):
    if not notification_ids:
        return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(notification_ids)
        placeholders = ', '.join(['%s'] * len(ids_tuple))
        query = f"UPDATE admin_notifications SET is_read = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Markieren von Admin-Benachrichtigungen: {e}")
    finally:
        cursor.close()


def get_all_logs_formatted():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        # MySQL CONCAT für die Namenszusammenführung
        cursor.execute("""
            SELECT
                a.timestamp,
                CONCAT(u.vorname, ' ', u.name) as user_name,
                a.action_type,
                a.details
            FROM activity_log a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC
        """)
        results = cursor.fetchall()

        # FIX: Konvertiere das MySQL datetime.datetime Objekt in einen String (wie von der GUI erwartet)
        for row in results:
            if row['timestamp']:
                row['timestamp'] = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen von Logs: {e}")
        return []
    finally:
        cursor.close()


# -------------------- BUG REPORTS (MySQL implementation) --------------------

def submit_bug_report(user_id, title, description):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO bug_reports (user_id, title, description, timestamp, user_notified) VALUES (%s, %s, %s, %s, 1)",
            (user_id, title, description, timestamp)
        )

        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user_role = cursor.fetchone()

        if user_role and user_role.get('role') not in ["Admin", "SuperAdmin"]:
            # Erstelle einen neuen Standard-Cursor für die Log-Funktion, falls benötigt
            _create_admin_notification(conn.cursor(), "Ein neuer Bug-Report wurde eingereicht.")

        conn.commit()
        return True, "Bug-Report erfolgreich übermittelt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def get_open_bug_reports_count():
    """Zählt alle nicht erledigten und nicht archivierten Bug-Reports."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bug_reports WHERE status != 'Erledigt' AND archived = 0")
        return cursor.fetchone()[0]
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen offener Bug-Reports: {e}")
        return 0
    finally:
        cursor.close()


def get_all_bug_reports():
    """Holt alle Bug-Reports inklusive des Archivierungsstatus."""
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.id, u.vorname, u.name, b.timestamp, b.title, b.description, b.status, b.archived, b.admin_notes
            FROM bug_reports b
            JOIN users u ON b.user_id = u.id
            ORDER BY b.archived ASC, b.timestamp DESC
        """)
        results = cursor.fetchall()

        # FIX: Konvertiere das MySQL datetime.datetime Objekt in einen String (wie von der GUI erwartet)
        for row in results:
            if row['timestamp']:
                row['timestamp'] = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen aller Bug-Reports: {e}")
        return []
    finally:
        cursor.close()


def get_visible_bug_reports():
    """Holt alle nicht-archivierten Bug-Reports für die Benutzeransicht."""
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.id, b.timestamp, b.title, b.description, b.status, b.admin_notes
            FROM bug_reports b
            WHERE b.archived = 0
            ORDER BY b.timestamp DESC
        """)
        results = cursor.fetchall()

        # FIX: Konvertiere das MySQL datetime.datetime Objekt in einen String (wie von der GUI erwartet)
        for row in results:
            if row['timestamp']:
                row['timestamp'] = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen sichtbarer Bug-Reports: {e}")
        return []
    finally:
        cursor.close()


def update_bug_report_status(bug_id, new_status):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET status = %s, user_notified = 0 WHERE id = %s",
            (new_status, bug_id)
        )
        conn.commit()
        return True, "Status aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def update_bug_report_notes(bug_id, notes):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET admin_notes = %s WHERE id = %s",
            (notes, bug_id)
        )
        conn.commit()
        return True, "Notizen gespeichert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def archive_bug_report(bug_id):
    """Setzt den 'archived' Status für einen Bug-Report auf 1."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET archived = 1 WHERE id = %s",
            (bug_id,)
        )
        conn.commit()
        return True, "Bug-Report wurde archiviert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def unarchive_bug_report(bug_id):
    """Setzt den 'archived' Status für einen Bug-Report auf 0 zurück."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET archived = 0 WHERE id = %s",
            (bug_id,)
        )
        conn.commit()
        return True, "Bug-Report wurde wiederhergestellt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def delete_bug_reports(report_ids):
    """Löscht einen oder mehrere Bug-Reports endgültig aus der Datenbank."""
    if not report_ids:
        return False, "Keine IDs zum Löschen übergeben."

    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        placeholders = ', '.join(['%s'] * len(report_ids))
        query = f"DELETE FROM bug_reports WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(report_ids))
        conn.commit()

        if cursor.rowcount > 0:
            return True, f"{cursor.rowcount} Bug-Report(s) endgültig gelöscht."
        else:
            return False, "Keine passenden Bug-Reports zum Löschen gefunden."

    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def get_unnotified_bug_reports_for_user(user_id):
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, title, status FROM bug_reports WHERE user_id = %s AND user_notified = 0",
            (user_id,)
        )
        return cursor.fetchall()
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def mark_bug_reports_as_notified(report_ids):
    if not report_ids:
        return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(report_ids)
        placeholders = ', '.join(['%s'] * len(ids_tuple))
        query = f"UPDATE bug_reports SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Markieren von Bug-Reports als benachrichtigt: {e}")
    finally:
        cursor.close()


# -------------------- WUNSCHFREI & REQUESTS (MySQL implementation) --------------------

def submit_user_request(user_id, request_date_str, requested_shift=None):
    """Speichert oder aktualisiert eine Benutzeranfrage (Wunschfrei oder Schichtpräferenz)."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        shift_to_store = "WF" if requested_shift is None else requested_shift

        # MySQL ON DUPLICATE KEY UPDATE für atomares UPDATE/INSERT
        cursor.execute("""
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, notified, rejection_reason)
            VALUES (%s, %s, %s, 'Ausstehend', 0, NULL)
            ON DUPLICATE KEY UPDATE
                requested_shift = VALUES(requested_shift),
                status = 'Ausstehend',
                notified = 0,
                rejection_reason = NULL;
        """, (user_id, request_date_str, shift_to_store))

        conn.commit()
        return True, "Anfrage erfolgreich gestellt oder aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def withdraw_wunschfrei_request(request_id, user_id):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM wunschfrei_requests WHERE id = %s AND user_id = %s", (request_id, user_id))
        request_data = cursor.fetchone()

        if not request_data:
            conn.rollback()
            return False, "Antrag nicht gefunden oder gehört nicht Ihnen."

        status = request_data['status']
        request_date = request_data['request_date'].strftime('%Y-%m-%d')

        if status not in ['Ausstehend', 'Genehmigt', 'Abgelehnt']:
            conn.rollback()
            return False, "Nur ausstehende, genehmigte oder abgelehnte Anträge können zurückgezogen werden."

        # Delete the request
        cursor.execute("DELETE FROM wunschfrei_requests WHERE id = %s", (request_id,))

        # Get user info for logging
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        user_name = f"{user['vorname']} {user['name']}" if user else "Unbekannter Benutzer"

        date_formatted = datetime.strptime(request_date, '%Y-%m-%d').strftime('%d.%m.%Y')

        # Logging based on status
        if status == 'Genehmigt':
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s",
                           (user_id, request_date))
            details = f"Benutzer '{user_name}' hat genehmigten Antrag für {date_formatted} zurückgezogen."
            # Hier muss ein Standard-Cursor verwendet werden, da _log_activity dies erwartet
            _log_activity(conn.cursor(), user_id, "ANTRAG_GENEHMIGT_ZURÜCKGEZOGEN", details)
            _create_admin_notification(conn.cursor(), details)
            msg = "Genehmigter Antrag wurde zurückgezogen."
        elif status == 'Ausstehend':
            details = f"Benutzer '{user_name}' hat ausstehenden Antrag für {date_formatted} zurückgezogen."
            _log_activity(conn.cursor(), user_id, "ANTRAG_AUSSTEHEND_ZURÜCKGEZOGEN", details)
            msg = "Ausstehender Antrag wurde zurückgezogen."
        elif status == 'Abgelehnt':
            details = f"Benutzer '{user_name}' hat abgelehnten Antrag für {date_formatted} gelöscht."
            _log_activity(conn.cursor(), user_id, "ANTRAG_ABGELEHNT_GELÖSCHT", details)
            msg = "Abgelehnter Antrag wurde gelöscht."

        conn.commit()
        return True, msg
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def get_wunschfrei_requests_by_user_for_month(user_id, year, month):
    """Zählt die 'Wunschfrei'-Anfragen eines Benutzers für einen Monat, die NICHT abgelehnt wurden."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = %s AND request_date BETWEEN %s AND %s AND status != 'Abgelehnt' AND requested_shift = 'WF'",
            (user_id, start_date, end_date)
        )
        return cursor.fetchone()[0]
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der Wunschfrei-Anfragen: {e}")
        return 0
    finally:
        cursor.close()


def get_pending_wunschfrei_requests():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT wr.id, u.vorname, u.name, wr.request_date, wr.user_id, wr.requested_shift
            FROM wunschfrei_requests wr
            JOIN users u ON wr.user_id = u.id
            WHERE wr.status = 'Ausstehend'
            ORDER BY wr.request_date ASC
        """)
        # Konvertiere MySQL Date-Objekte in Strings
        results = cursor.fetchall()
        for row in results:
            if row['request_date']:
                row['request_date'] = row['request_date'].strftime('%Y-%m-%d')
        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen ausstehender Wunschfrei-Anfragen: {e}")
        return []
    finally:
        cursor.close()


def get_wunschfrei_request_by_user_and_date(user_id, request_date_str):
    """Holt eine spezifische 'Wunschfrei'-Anfrage anhand von Benutzer und Datum."""
    conn = create_connection()
    if conn is None: return None
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, request_date, status, requested_shift FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s",
            (user_id, request_date_str)
        )
        row = cursor.fetchone()
        if row and row['request_date']:
            row['request_date'] = row['request_date'].strftime('%Y-%m-%d')
        return row
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen einer spezifischen Wunschfrei-Anfrage: {e}")
        return None
    finally:
        cursor.close()


def get_wunschfrei_requests_for_month(year, month):
    conn = create_connection()
    if conn is None: return {}
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (start_date, end_date)
        )
        requests = {}
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            if user_id_str not in requests:
                requests[user_id_str] = {}
            # Konvertiere MySQL Date-Objekte in Strings
            date_str = row['request_date'].strftime('%Y-%m-%d') if row['request_date'] else None
            requests[user_id_str][date_str] = (row['status'], row['requested_shift'])
        return requests
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen von Wunschfrei-Anfragen für den Monat: {e}")
        return {}
    finally:
        cursor.close()


def update_wunschfrei_status(request_id, new_status, reason=None):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE wunschfrei_requests SET status = %s, notified = 0, rejection_reason = %s WHERE id = %s",
            (new_status, reason, request_id)
        )
        conn.commit()
        return True, "Status erfolgreich aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def get_all_requests_by_user(user_id):
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason, requested_shift FROM wunschfrei_requests WHERE user_id = %s ORDER BY request_date DESC",
            (user_id,)
        )
        results = cursor.fetchall()
        for row in results:
            if row['request_date']:
                row['request_date'] = row['request_date'].strftime('%Y-%m-%d')
        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen aller Anfragen eines Benutzers: {e}")
        return []
    finally:
        cursor.close()


def get_unnotified_requests(user_id):
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason FROM wunschfrei_requests WHERE user_id = %s AND notified = 0 AND status != 'Ausstehend'",
            (user_id,)
        )
        results = cursor.fetchall()
        for row in results:
            if row['request_date']:
                row['request_date'] = row['request_date'].strftime('%Y-%m-%d')
        return results
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def mark_requests_as_notified(request_ids):
    if not request_ids:
        return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(request_ids)
        placeholders = ', '.join(['%s'] * len(ids_tuple))
        query = f"UPDATE wunschfrei_requests SET notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Markieren von Anfragen als benachrichtigt: {e}")
    finally:
        cursor.close()


# -------------------- SHIFT SCHEDULE (MySQL implementation) --------------------

def save_shift_entry(user_id, shift_date_str, shift_abbrev):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        if shift_abbrev in ["", "FREI"]:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s",
                           (user_id, shift_date_str))
        else:
            # MySQL ON DUPLICATE KEY UPDATE für atomares UPDATE/INSERT
            cursor.execute("""
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    shift_abbrev = VALUES(shift_abbrev);
            """, (user_id, shift_date_str, shift_abbrev))

        # Lösche zugehörige wunschfrei_requests, wenn es kein temporärer 'X' Override ist
        if shift_abbrev != 'X':
            cursor.execute("DELETE FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s",
                           (user_id, shift_date_str))

        conn.commit()
        return True, "Schicht gespeichert."

    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schicht: {e}"
    finally:
        cursor.close()


def get_shifts_for_month(year, month):
    conn = create_connection()
    if conn is None: return {}
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT user_id, shift_date, shift_abbrev
            FROM shift_schedule
            WHERE shift_date BETWEEN %s AND %s
        """, (start_date, end_date))

        shifts = {}
        for row in cursor.fetchall():
            user_id = str(row['user_id'])
            if user_id not in shifts:
                shifts[user_id] = {}

            # Konvertiere MySQL Date-Objekte in Strings
            date_str = row['shift_date'].strftime('%Y-%m-%d') if row['shift_date'] else None
            shifts[user_id][date_str] = row['shift_abbrev']

        return shifts

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen des Schichtplans: {e}")
        return {}
    finally:
        cursor.close()


def get_daily_shift_counts_for_month(year, month):
    conn = create_connection()
    if conn is None: return {}
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                shift_date,
                shift_abbrev,
                COUNT(shift_abbrev) as count
            FROM shift_schedule
            WHERE shift_date BETWEEN %s AND %s
            GROUP BY shift_date, shift_abbrev
        """, (start_date, end_date))

        daily_counts = {}
        for row in cursor.fetchall():
            # Konvertiere MySQL Date-Objekte in Strings
            shift_date = row['shift_date'].strftime('%Y-%m-%d') if row['shift_date'] else None
            if shift_date not in daily_counts:
                daily_counts[shift_date] = {}
            daily_counts[shift_date][row['shift_abbrev']] = row['count']

        return daily_counts

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}")
        return {}
    finally:
        cursor.close()


# -------------------- SHIFT TYPES (MySQL implementation) --------------------

def get_all_shift_types():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, abbreviation, hours, description, color, start_time, end_time FROM shift_types ORDER BY abbreviation")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtarten: {e}")
        return []
    finally:
        cursor.close()


def add_shift_type(data):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO shift_types
               (name, abbreviation, hours, description, color, start_time, end_time)
               VALUES (%(name)s, %(abbreviation)s, %(hours)s, %(description)s, %(color)s, %(start_time)s, %(end_time)s)""",
            data)
        conn.commit()
        return True, "Schichtart erfolgreich hinzugefügt."
    except mysql.connector.IntegrityError:
        return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def update_shift_type(shift_type_id, data):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        sql = """ UPDATE shift_types
                  SET name = %(name)s,
                      abbreviation = %(abbreviation)s,
                      hours = %(hours)s,
                      description = %(description)s,
                      color = %(color)s,
                      start_time = %(start_time)s,
                      end_time = %(end_time)s
                  WHERE id = %(id)s """

        data['id'] = shift_type_id

        cursor.execute(sql, data)
        conn.commit()
        return True, "Schichtart erfolgreich aktualisiert."
    except mysql.connector.IntegrityError:
        return False, "Die neue Abkürzung wird bereits von einer anderen Schichtart verwendet."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def delete_shift_type(shift_type_id):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT abbreviation FROM shift_types WHERE id = %s", (shift_type_id,))
        abbrev = cursor.fetchone()

        cursor.execute("DELETE FROM shift_types WHERE id = %s", (shift_type_id,))

        if abbrev:
            # Hier muss ein Standard-Cursor verwendet werden, also neuen Cursor erstellen
            order_cursor = conn.cursor()
            order_cursor.execute("DELETE FROM shift_order WHERE abbreviation = %s", (abbrev['abbreviation'],))
            order_cursor.close()

        conn.commit()
        return True, "Schichtart erfolgreich gelöscht."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def get_ordered_shift_abbrevs(include_hidden=False):
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM shift_types")
        shift_types_data = {st['abbreviation']: dict(st) for st in cursor.fetchall()}

        cursor.execute("SELECT abbreviation, sort_order, is_visible, check_for_understaffing FROM shift_order")
        order_map = {row['abbreviation']: dict(row) for row in cursor.fetchall()}

        ordered_list = []
        all_relevant_abbrevs = set(shift_types_data.keys()) | {'T.', '6', 'N.', '24'}

        for abbrev in sorted(list(all_relevant_abbrevs)):
            if abbrev in shift_types_data:
                item = shift_types_data[abbrev]
            else:
                item = {'abbreviation': abbrev,
                        'name': f"({abbrev} - Regel)" if abbrev not in ['T.', '6', 'N.', '24'] else abbrev,
                        'hours': 0,
                        'description': f"Harte Regel für {abbrev}.",
                        'color': '#FFFFFF'}

            order_data = order_map.get(abbrev, {'sort_order': 999999, 'is_visible': 1, 'check_for_understaffing': 0})
            item['sort_order'] = order_data['sort_order']
            item['is_visible'] = order_data['is_visible']
            item['check_for_understaffing'] = order_data['check_for_understaffing']

            if include_hidden or item['is_visible'] == 1:
                ordered_list.append(item)

        ordered_list.sort(key=lambda x: x['sort_order'])
        return ordered_list
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtreihenfolge: {e}")
        return []
    finally:
        cursor.close()


def save_shift_order(order_data_list):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM shift_order")
        cursor.executemany(
            "INSERT INTO shift_order (abbreviation, sort_order, is_visible, check_for_understaffing) VALUES (%s, %s, %s, %s)",
            order_data_list)
        conn.commit()
        return True, "Schichtreihenfolge erfolgreich gespeichert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schichtreihenfolge: {e}"
    finally:
        cursor.close()


# -------------------- DOGS (MySQL implementation) --------------------

def get_all_dogs():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM dogs ORDER BY name")
        return cursor.fetchall()
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def add_dog(data):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dogs (name, breed, birth_date, chip_number, acquisition_date, departure_date, last_dpo_date, vaccination_info) VALUES (%(name)s, %(breed)s, %(birth_date)s, %(chip_number)s, %(acquisition_date)s, %(departure_date)s, %(last_dpo_date)s, %(vaccination_info)s)",
            data)
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False
    except mysql.connector.Error:
        conn.rollback()
        return False
    finally:
        cursor.close()


def update_dog(dog_id, data):
    data['id'] = dog_id
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dogs SET name = %(name)s, breed = %(breed)s, birth_date = %(birth_date)s, chip_number = %(chip_number)s, acquisition_date = %(acquisition_date)s, departure_date = %(departure_date)s, last_dpo_date = %(last_dpo_date)s, vaccination_info = %(vaccination_info)s WHERE id = %(id)s",
            data)
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False
    except mysql.connector.Error:
        conn.rollback()
        return False
    finally:
        cursor.close()


def delete_dog(dog_id):
    conn = create_connection()
    if conn is None: return False
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT name FROM dogs WHERE id = %s", (dog_id,))
        dog_name_row = cursor.fetchone()

        if dog_name_row:
            dog_name = dog_name_row['name']
            # Hier muss ein Standard-Cursor verwendet werden, also neuen Cursor erstellen
            user_cursor = conn.cursor()
            user_cursor.execute("UPDATE users SET diensthund = '' WHERE diensthund = %s", (dog_name,))
            user_cursor.close()

        cursor.execute("DELETE FROM dogs WHERE id = %s", (dog_id,))
        conn.commit()
        return True
    except mysql.connector.Error:
        conn.rollback()
        return False
    finally:
        cursor.close()


def get_dog_handlers(dog_name):
    if not dog_name: return []
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, vorname, name FROM users WHERE diensthund = %s", (dog_name,))
        return cursor.fetchall()
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def get_dog_assignment_count(dog_name):
    if not dog_name or dog_name == "Kein": return 0
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE diensthund = %s", (dog_name,))
        return cursor.fetchone()[0]
    except mysql.connector.Error:
        return 0
    finally:
        cursor.close()


def get_available_dogs():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT d.name FROM dogs d
            LEFT JOIN (
                SELECT diensthund, COUNT(*) as assignment_count
                FROM users
                WHERE diensthund IS NOT NULL AND diensthund != ''
                GROUP BY diensthund
            ) AS assignments ON d.name = assignments.diensthund
            WHERE assignments.assignment_count < 2 OR assignments.assignment_count IS NULL
        """)
        return [row['name'] for row in cursor.fetchall()]
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def assign_dog(dog_name, user_id):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET diensthund = %s WHERE id = %s", (dog_name, user_id))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler bei der Zuweisung: {e}")
        return False
    finally:
        cursor.close()


# -------------------- USERS (MySQL implementation) --------------------

def get_user_count():
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]
    except mysql.connector.Error:
        return 0
    finally:
        cursor.close()


def add_user(vorname, name, password):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        user_count = get_user_count()
        role = "SuperAdmin" if user_count == 0 else "Benutzer"
        if not vorname or not name: return False, "Bitte Vor- und Nachnamen angeben."
        cursor.execute("INSERT INTO users (password_hash, role, vorname, name) VALUES (%s, %s, %s, %s)",
                       (hash_password(password), role, vorname, name))
        conn.commit()
        return True, "Registrierung erfolgreich."
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, "Ein Benutzer mit diesem Namen existiert bereits."
    finally:
        cursor.close()


def check_login(vorname, name, password):
    conn = create_connection()
    if conn is None: return None
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        # MySQL LOWER() für case-insensitive comparison
        cursor.execute("SELECT * FROM users WHERE LOWER(vorname) = LOWER(%s) AND LOWER(name) = LOWER(%s)",
                       (vorname, name))
        user = cursor.fetchone()
        if user and user['password_hash'] == hash_password(password):
            return user
        return None
    except mysql.connector.Error as e:
        print(f"Fehler beim Login-Check: {e}")
        return None
    finally:
        cursor.close()


def get_all_users():
    conn = create_connection()
    if conn is None: return {}
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users ORDER BY name")
        users = cursor.fetchall()
        return {str(user['id']): user for user in users}
    except mysql.connector.Error:
        return {}
    finally:
        cursor.close()


def get_ordered_users_for_schedule(include_hidden=False):
    conn = create_connection()
    if conn is None: return []
    try:
        query = """
            SELECT u.*, COALESCE(uo.sort_order, 999999) AS sort_order, COALESCE(uo.is_visible, 1) AS is_visible 
            FROM users u LEFT JOIN user_order uo ON u.id = uo.user_id
        """
        if not include_hidden:
            query += " WHERE COALESCE(uo.is_visible, 1) = 1"
        query += " ORDER BY sort_order ASC, u.name ASC"

        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)

        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der geordneten Benutzer: {e}")
        return []
    finally:
        cursor.close()


def save_user_order(order_data_list):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM user_order")
        cursor.executemany("INSERT INTO user_order (user_id, sort_order, is_visible) VALUES (%s, %s, %s)",
                           order_data_list)
        conn.commit()
        return True, "Reihenfolge und Sichtbarkeit erfolgreich gespeichert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Reihenfolge und Sichtbarkeit: {e}"
    finally:
        cursor.close()


def update_user(user_id, data):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        data['urlaub_rest'] = data.get('urlaub_gesamt', 30)

        cursor.execute(
            "UPDATE users SET vorname = %s, name = %s, geburtstag = %s, telefon = %s, diensthund = %s, urlaub_gesamt = %s, urlaub_rest = %s, role = %s, entry_date = %s WHERE id = %s",
            (data['vorname'], data['name'], data['geburtstag'], data['telefon'], data['diensthund'],
             data['urlaub_gesamt'], data['urlaub_rest'], data['role'], data['entry_date'], user_id))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Aktualisieren des Benutzers: {e}")
        return False
    finally:
        cursor.close()


def create_user_by_admin(data):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, geburtstag, telefon, diensthund, urlaub_gesamt, urlaub_rest, entry_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (data['vorname'], data['name'], hash_password(data['password']), data['role'], data['geburtstag'],
             data['telefon'], data['diensthund'], data['urlaub_gesamt'], data['urlaub_gesamt'], data['entry_date']))
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False
    finally:
        cursor.close()


def delete_user(user_id):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()

        # MySQL's ON DELETE CASCADE sollte die zugehörigen Einträge löschen
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))

        conn.commit()
        return True
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Löschen des Benutzers: {e}")
        return False
    finally:
        cursor.close()


# -------------------- VACATION REQUESTS (MySQL implementation) --------------------

def add_vacation_request(user_id, start_date, end_date):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO vacation_requests (user_id, start_date, end_date, status, request_date) VALUES (%s, %s, %s, %s, %s)",
            (user_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "Ausstehend",
             date.today().strftime('%Y-%m-%d')))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Hinzufügen des Urlaubsantrags: {e}")
        return False
    finally:
        cursor.close()


def get_requests_by_user(user_id):
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM vacation_requests WHERE user_id = %s ORDER BY start_date DESC", (user_id,))
        results = cursor.fetchall()
        for row in results:
            if row['start_date']:
                row['start_date'] = row['start_date'].strftime('%Y-%m-%d')
            if row['end_date']:
                row['end_date'] = row['end_date'].strftime('%Y-%m-%d')
            if row['request_date']:
                row['request_date'] = row['request_date'].strftime('%Y-%m-%d')
        return results
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def get_pending_vacation_requests():
    conn = create_connection()
    if conn is None: return []
    try:
        # Cursor mit dictionary=True anfordern
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT vr.id, u.vorname, u.name, vr.start_date, vr.end_date, vr.status 
               FROM vacation_requests vr 
               JOIN users u ON vr.user_id = u.id 
               WHERE vr.status = 'Ausstehend' 
               ORDER BY vr.request_date ASC""")
        results = cursor.fetchall()
        for row in results:
            if row['start_date']:
                row['start_date'] = row['start_date'].strftime('%Y-%m-%d')
            if row['end_date']:
                row['end_date'] = row['end_date'].strftime('%Y-%m-%d')
        return results
    except mysql.connector.Error:
        return []
    finally:
        cursor.close()


def update_vacation_request_status(request_id, new_status):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET status = %s WHERE id = %s", (new_status, request_id))
        conn.commit()
        return True, "Urlaubsstatus erfolgreich aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        cursor.close()


def get_pending_vacation_requests_count():
    """Zählt die Anzahl der ausstehenden Urlaubsanträge."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vacation_requests WHERE status = 'Ausstehend'")
        return cursor.fetchone()[0]
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der Urlaubsanträge: {e}")
        return 0
    finally:
        cursor.close()


def set_user_tutorial_seen(user_id):
    """Setzt das Flag, dass der Benutzer das Tutorial gesehen hat."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = %s", (user_id,))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"DB-Fehler beim Setzen des Tutorial-Status: {e}")
        return False
    finally:
        cursor.close()