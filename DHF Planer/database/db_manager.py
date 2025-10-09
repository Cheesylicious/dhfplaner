# database/db_manager.py
import sqlite3
import hashlib
from datetime import date, datetime
import calendar

DATABASE_NAME = 'planer.db'

ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row['name'] for row in cursor.fetchall()]
    if column_name not in columns:
        print(f"Füge Spalte '{column_name}' zur Tabelle '{table_name}' hinzu...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def initialize_db():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                vorname TEXT NOT NULL,
                name TEXT NOT NULL,
                geburtstag TEXT,
                telefon TEXT,
                diensthund TEXT,
                urlaub_gesamt INTEGER DEFAULT 30,
                urlaub_rest INTEGER DEFAULT 30,
                entry_date TEXT,
                UNIQUE (vorname, name)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacation_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL,
                request_date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wunschfrei_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                request_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ausstehend',
                notified INTEGER DEFAULT 0,
                rejection_reason TEXT,
                requested_shift TEXT,
                UNIQUE(user_id, request_date),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                breed TEXT,
                birth_date TEXT,
                chip_number TEXT UNIQUE,
                acquisition_date TEXT,
                departure_date TEXT,
                last_dpo_date TEXT,
                vaccination_info TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                abbreviation TEXT UNIQUE NOT NULL,
                hours INTEGER NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#FFFFFF',
                start_time TEXT,
                end_time TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                shift_date TEXT NOT NULL,
                shift_abbrev TEXT NOT NULL,
                UNIQUE (user_id, shift_date),
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (shift_abbrev) REFERENCES shift_types (abbreviation)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_order (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL,
                is_visible INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_order (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                abbreviation TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL,
                is_visible INTEGER DEFAULT 1,
                check_for_understaffing INTEGER DEFAULT 0
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER,
                action_type TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bug_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Neu',
                is_read INTEGER NOT NULL DEFAULT 0,
                user_notified INTEGER NOT NULL DEFAULT 1,
                archived INTEGER NOT NULL DEFAULT 0,
                admin_notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)

        _add_column_if_not_exists(cursor, "users", "entry_date", "TEXT")
        _add_column_if_not_exists(cursor, "shift_types", "color", "TEXT DEFAULT '#FFFFFF'")
        _add_column_if_not_exists(cursor, "user_order", "is_visible", "INTEGER DEFAULT 1")
        _add_column_if_not_exists(cursor, "shift_order", "is_visible", "INTEGER DEFAULT 1")
        _add_column_if_not_exists(cursor, "shift_order", "check_for_understaffing", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "notified", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "rejection_reason", "TEXT")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "requested_shift", "TEXT")
        _add_column_if_not_exists(cursor, "shift_types", "start_time", "TEXT")
        _add_column_if_not_exists(cursor, "shift_types", "end_time", "TEXT")
        _add_column_if_not_exists(cursor, "bug_reports", "user_notified", "INTEGER NOT NULL DEFAULT 1")
        _add_column_if_not_exists(cursor, "bug_reports", "archived", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_not_exists(cursor, "bug_reports", "admin_notes", "TEXT")
        _add_column_if_not_exists(cursor, "users", "has_seen_tutorial", "INTEGER DEFAULT 0")

        conn.commit()
    finally:
        conn.close()


def _log_activity(cursor, user_id, action_type, details):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (?, ?, ?, ?)",
        (timestamp, user_id, action_type, details)
    )


def _create_admin_notification(cursor, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO admin_notifications (message, timestamp) VALUES (?, ?)",
        (message, timestamp)
    )


def get_unread_admin_notifications():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, message FROM admin_notifications WHERE is_read = 0 ORDER BY timestamp ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_admin_notifications_as_read(notification_ids):
    if not notification_ids:
        return
    conn = create_connection()
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(notification_ids)
        placeholders = ', '.join('?' for _ in ids_tuple)
        query = f"UPDATE admin_notifications SET is_read = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    finally:
        conn.close()


def get_all_logs_formatted():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                a.timestamp,
                COALESCE(u.vorname || ' ' || u.name, 'Unbekannt') as user_name,
                a.action_type,
                a.details
            FROM activity_log a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def submit_bug_report(user_id, title, description):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO bug_reports (user_id, title, description, timestamp, user_notified) VALUES (?, ?, ?, ?, 1)",
            (user_id, title, description, timestamp)
        )

        cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        user_role = cursor.fetchone()['role']
        if user_role not in ["Admin", "SuperAdmin"]:
            _create_admin_notification(cursor, "Ein neuer Bug-Report wurde eingereicht.")

        conn.commit()
        return True, "Bug-Report erfolgreich übermittelt."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_open_bug_reports_count():
    """Zählt alle nicht erledigten und nicht archivierten Bug-Reports."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bug_reports WHERE status != 'Erledigt' AND archived = 0")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_all_bug_reports():
    """Holt alle Bug-Reports inklusive des Archivierungsstatus."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id, u.vorname, u.name, b.timestamp, b.title, b.description, b.status, b.archived, b.admin_notes
            FROM bug_reports b
            JOIN users u ON b.user_id = u.id
            ORDER BY b.archived ASC, b.timestamp DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_visible_bug_reports():
    """Holt alle nicht-archivierten Bug-Reports für die Benutzeransicht."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id, b.timestamp, b.title, b.description, b.status, b.admin_notes
            FROM bug_reports b
            WHERE b.archived = 0
            ORDER BY b.timestamp DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_bug_report_status(bug_id, new_status):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET status = ?, user_notified = 0 WHERE id = ?",
            (new_status, bug_id)
        )
        conn.commit()
        return True, "Status aktualisiert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def update_bug_report_notes(bug_id, notes):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET admin_notes = ? WHERE id = ?",
            (notes, bug_id)
        )
        conn.commit()
        return True, "Notizen gespeichert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def archive_bug_report(bug_id):
    """Setzt den 'archived' Status für einen Bug-Report auf 1."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET archived = 1 WHERE id = ?",
            (bug_id,)
        )
        conn.commit()
        return True, "Bug-Report wurde archiviert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def unarchive_bug_report(bug_id):
    """Setzt den 'archived' Status für einen Bug-Report auf 0 zurück."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bug_reports SET archived = 0 WHERE id = ?",
            (bug_id,)
        )
        conn.commit()
        return True, "Bug-Report wurde wiederhergestellt."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def delete_bug_reports(report_ids):
    """Löscht einen oder mehrere Bug-Reports endgültig aus der Datenbank."""
    if not report_ids:
        return False, "Keine IDs zum Löschen übergeben."

    conn = create_connection()
    try:
        cursor = conn.cursor()
        placeholders = ', '.join('?' for _ in report_ids)
        query = f"DELETE FROM bug_reports WHERE id IN ({placeholders})"
        cursor.execute(query, report_ids)
        conn.commit()

        if cursor.rowcount > 0:
            return True, f"{cursor.rowcount} Bug-Report(s) endgültig gelöscht."
        else:
            return False, "Keine passenden Bug-Reports zum Löschen gefunden."

    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_unnotified_bug_reports_for_user(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, status FROM bug_reports WHERE user_id = ? AND user_notified = 0",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_bug_reports_as_notified(report_ids):
    if not report_ids:
        return
    conn = create_connection()
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(report_ids)
        placeholders = ', '.join('?' for _ in ids_tuple)
        query = f"UPDATE bug_reports SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    finally:
        conn.close()


def submit_user_request(user_id, request_date_str, requested_shift=None):
    """Speichert oder aktualisiert eine Benutzeranfrage (Wunschfrei oder Schichtpräferenz)."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        shift_to_store = "WF" if requested_shift is None else requested_shift

        cursor.execute("""
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, notified, rejection_reason)
            VALUES (?, ?, ?, 'Ausstehend', 0, NULL)
            ON CONFLICT(user_id, request_date) DO UPDATE SET
                requested_shift = excluded.requested_shift,
                status = 'Ausstehend',
                notified = 0,
                rejection_reason = NULL;
        """, (user_id, request_date_str, shift_to_store))

        conn.commit()
        return True, "Anfrage erfolgreich gestellt oder aktualisiert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def withdraw_wunschfrei_request(request_id, user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        cursor.execute("SELECT * FROM wunschfrei_requests WHERE id = ? AND user_id = ?", (request_id, user_id))
        request_data = cursor.fetchone()

        if not request_data:
            conn.rollback()
            return False, "Antrag nicht gefunden oder gehört nicht Ihnen."

        status = request_data['status']
        request_date = request_data['request_date']

        if status not in ['Ausstehend', 'Genehmigt', 'Abgelehnt']:
            conn.rollback()
            return False, "Nur ausstehende, genehmigte oder abgelehnte Anträge können zurückgezogen werden."

        cursor.execute("DELETE FROM wunschfrei_requests WHERE id = ?", (request_id,))

        user_info_cursor = conn.cursor()
        user_info_cursor.execute("SELECT vorname, name FROM users WHERE id = ?", (user_id,))
        user = user_info_cursor.fetchone()
        user_name = f"{user['vorname']} {user['name']}" if user else "Unbekannter Benutzer"

        date_formatted = datetime.strptime(request_date, '%Y-%m-%d').strftime('%d.%m.%Y')

        if status == 'Genehmigt':
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = ? AND shift_date = ?",
                           (user_id, request_date))
            details = f"Benutzer '{user_name}' hat genehmigten Antrag für {date_formatted} zurückgezogen."
            _log_activity(cursor, user_id, "ANTRAG_GENEHMIGT_ZURÜCKGEZOGEN", details)
            _create_admin_notification(cursor, details)
            msg = "Genehmigter Antrag wurde zurückgezogen."
        elif status == 'Ausstehend':
            details = f"Benutzer '{user_name}' hat ausstehenden Antrag für {date_formatted} zurückgezogen."
            _log_activity(cursor, user_id, "ANTRAG_AUSSTEHEND_ZURÜCKGEZOGEN", details)
            msg = "Ausstehender Antrag wurde zurückgezogen."
        elif status == 'Abgelehnt':
            details = f"Benutzer '{user_name}' hat abgelehnten Antrag für {date_formatted} gelöscht."
            _log_activity(cursor, user_id, "ANTRAG_ABGELEHNT_GELÖSCHT", details)
            msg = "Abgelehnter Antrag wurde gelöscht."

        conn.commit()
        return True, msg
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_wunschfrei_requests_by_user_for_month(user_id, year, month):
    """Zählt die 'Wunschfrei'-Anfragen eines Benutzers für einen Monat, die NICHT abgelehnt wurden."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = ? AND request_date BETWEEN ? AND ? AND status != 'Abgelehnt' AND requested_shift = 'WF'",
            (user_id, start_date, end_date)
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_pending_wunschfrei_requests():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT wr.id, u.vorname, u.name, wr.request_date, wr.user_id, wr.requested_shift
            FROM wunschfrei_requests wr
            JOIN users u ON wr.user_id = u.id
            WHERE wr.status = 'Ausstehend'
            ORDER BY wr.request_date ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_wunschfrei_request_by_user_and_date(user_id, request_date_str):
    """Holt eine spezifische 'Wunschfrei'-Anfrage anhand von Benutzer und Datum."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, request_date, status, requested_shift FROM wunschfrei_requests WHERE user_id = ? AND request_date = ?",
            (user_id, request_date_str)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_wunschfrei_requests_for_month(year, month):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift FROM wunschfrei_requests WHERE request_date BETWEEN ? AND ?",
            (start_date, end_date)
        )
        requests = {}
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            if user_id_str not in requests:
                requests[user_id_str] = {}
            requests[user_id_str][row['request_date']] = (row['status'], row['requested_shift'])
        return requests
    finally:
        conn.close()


def update_wunschfrei_status(request_id, new_status, reason=None):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE wunschfrei_requests SET status = ?, notified = 0, rejection_reason = ? WHERE id = ?",
            (new_status, reason, request_id)
        )
        conn.commit()
        return True, "Status erfolgreich aktualisiert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_all_requests_by_user(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason, requested_shift FROM wunschfrei_requests WHERE user_id = ? ORDER BY request_date DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_unnotified_requests(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason FROM wunschfrei_requests WHERE user_id = ? AND notified = 0 AND status != 'Ausstehend'",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_requests_as_notified(request_ids):
    if not request_ids:
        return
    conn = create_connection()
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(request_ids)
        placeholders = ', '.join('?' for _ in ids_tuple)
        query = f"UPDATE wunschfrei_requests SET notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    finally:
        conn.close()


def save_shift_entry(user_id, shift_date_str, shift_abbrev):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        if shift_abbrev in ["", "FREI"]:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = ? AND shift_date = ?",
                           (user_id, shift_date_str))
        else:
            cursor.execute("""
                UPDATE shift_schedule SET shift_abbrev = ?
                WHERE user_id = ? AND shift_date = ?
            """, (shift_abbrev, user_id, shift_date_str))
            if cursor.rowcount == 0:
                cursor.execute("""
                    INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                    VALUES (?, ?, ?)
                """, (user_id, shift_date_str, shift_abbrev))

        if shift_abbrev != 'X':
            cursor.execute("DELETE FROM wunschfrei_requests WHERE user_id = ? AND request_date = ?",
                           (user_id, shift_date_str))

        conn.commit()
        return True, "Schicht gespeichert."

    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schicht: {e}"
    finally:
        conn.close()


def get_shifts_for_month(year, month):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT user_id, shift_date, shift_abbrev
            FROM shift_schedule
            WHERE shift_date BETWEEN ? AND ?
        """, (start_date, end_date))

        shifts = {}
        for row in cursor.fetchall():
            user_id = str(row['user_id'])
            if user_id not in shifts:
                shifts[user_id] = {}
            shifts[user_id][row['shift_date']] = row['shift_abbrev']

        return shifts

    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen des Schichtplans: {e}")
        return {}
    finally:
        conn.close()


def get_daily_shift_counts_for_month(year, month):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                shift_date,
                shift_abbrev,
                COUNT(shift_abbrev) as count
            FROM shift_schedule
            WHERE shift_date BETWEEN ? AND ?
            GROUP BY shift_date, shift_abbrev
        """, (start_date, end_date))

        daily_counts = {}
        for row in cursor.fetchall():
            shift_date = row['shift_date']
            if shift_date not in daily_counts:
                daily_counts[shift_date] = {}
            daily_counts[shift_date][row['shift_abbrev']] = row['count']

        return daily_counts

    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}")
        return {}
    finally:
        conn.close()


def get_all_shift_types():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, abbreviation, hours, description, color, start_time, end_time FROM shift_types ORDER BY abbreviation")
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der Schichtarten: {e}")
        return []
    finally:
        conn.close()


def add_shift_type(data):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO shift_types
               (name, abbreviation, hours, description, color, start_time, end_time)
               VALUES (:name, :abbreviation, :hours, :description, :color, :start_time, :end_time)""",
            data)
        conn.commit()
        return True, "Schichtart erfolgreich hinzugefügt."
    except sqlite3.IntegrityError:
        return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def update_shift_type(shift_type_id, data):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        sql = """ UPDATE shift_types
                  SET name = :name,
                      abbreviation = :abbreviation,
                      hours = :hours,
                      description = :description,
                      color = :color,
                      start_time = :start_time,
                      end_time = :end_time
                  WHERE id = :id """

        data['id'] = shift_type_id

        cursor.execute(sql, data)
        conn.commit()
        return True, "Schichtart erfolgreich aktualisiert."
    except sqlite3.IntegrityError:
        return False, "Die neue Abkürzung wird bereits von einer anderen Schichtart verwendet."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def delete_shift_type(shift_type_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT abbreviation FROM shift_types WHERE id = ?", (shift_type_id,))
        abbrev = cursor.fetchone()
        cursor.execute("DELETE FROM shift_types WHERE id = ?", (shift_type_id,))
        if abbrev:
            cursor.execute("DELETE FROM shift_order WHERE abbreviation = ?", (abbrev['abbreviation'],))
        conn.commit()
        return True, "Schichtart erfolgreich gelöscht."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_ordered_shift_abbrevs(include_hidden=False):
    conn = create_connection()
    try:
        cursor = conn.cursor()
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
                        'name': f"({abbrev} - Regel)" if abbrev not in ['T.', '6', 'N.', '24'] else abbrev, 'hours': 0,
                        'description': f"Harte Regel für {abbrev}.", 'color': '#FFFFFF'}
            order_data = order_map.get(abbrev, {'sort_order': 999999, 'is_visible': 1, 'check_for_understaffing': 0})
            item['sort_order'] = order_data['sort_order']
            item['is_visible'] = order_data['is_visible']
            item['check_for_understaffing'] = order_data['check_for_understaffing']
            if include_hidden or item['is_visible'] == 1:
                ordered_list.append(item)
        ordered_list.sort(key=lambda x: x['sort_order'])
        return ordered_list
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der Schichtreihenfolge: {e}")
        return [dict(st, sort_order=999999, is_visible=1, check_for_understaffing=0) for st in get_all_shift_types()]


def save_shift_order(order_data_list):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM shift_order")
        cursor.executemany(
            "INSERT INTO shift_order (abbreviation, sort_order, is_visible, check_for_understaffing) VALUES (?, ?, ?, ?)",
            order_data_list)
        conn.commit()
        return True, "Schichtreihenfolge erfolgreich gespeichert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schichtreihenfolge: {e}"
    finally:
        conn.close()


def get_all_dogs():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dogs ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def add_dog(data):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dogs (name, breed, birth_date, chip_number, acquisition_date, departure_date, last_dpo_date, vaccination_info) VALUES (:name, :breed, :birth_date, :chip_number, :acquisition_date, :departure_date, :last_dpo_date, :vaccination_info)",
            data)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_dog(dog_id, data):
    data['id'] = dog_id
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dogs SET name = :name, breed = :breed, birth_date = :birth_date, chip_number = :chip_number, acquisition_date = :acquisition_date, departure_date = :departure_date, last_dpo_date = :last_dpo_date, vaccination_info = :vaccination_info WHERE id = :id",
            data)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_dog(dog_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET diensthund = '' WHERE diensthund = (SELECT name FROM dogs WHERE id = ?)",
                       (dog_id,))
        cursor.execute("DELETE FROM dogs WHERE id = ?", (dog_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_dog_handlers(dog_name):
    if not dog_name: return []
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, vorname, name FROM users WHERE diensthund = ?", (dog_name,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_dog_assignment_count(dog_name):
    if not dog_name or dog_name == "Kein": return 0
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE diensthund = ?", (dog_name,))
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_available_dogs():
    conn = create_connection()
    try:
        cursor = conn.cursor()
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
    finally:
        conn.close()


def assign_dog(dog_name, user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET diensthund = ? WHERE id = ?", (dog_name, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Fehler bei der Zuweisung: {e}")
        return False
    finally:
        conn.close()


def get_user_count():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def add_user(vorname, name, password):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        user_count = get_user_count()
        role = "SuperAdmin" if user_count == 0 else "Benutzer"
        if not vorname or not name: return False, "Bitte Vor- und Nachnamen angeben."
        cursor.execute("INSERT INTO users (password_hash, role, vorname, name) VALUES (?, ?, ?, ?)",
                       (hash_password(password), role, vorname, name))
        conn.commit()
        return True, "Registrierung erfolgreich."
    except sqlite3.IntegrityError:
        return False, "Ein Benutzer mit diesem Namen existiert bereits."
    finally:
        conn.close()


def check_login(vorname, name, password):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE lower(vorname) = ? AND lower(name) = ?",
                       (vorname.lower(), name.lower()))
        user = cursor.fetchone()
        if user and user['password_hash'] == hash_password(password):
            return dict(user)
        return None
    finally:
        conn.close()


def get_all_users():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY name")
        users = cursor.fetchall()
        return {str(user['id']): dict(user) for user in users}
    finally:
        conn.close()


def get_ordered_users_for_schedule(include_hidden=False):
    conn = create_connection()
    try:
        query = "SELECT u.*, COALESCE(uo.sort_order, 999999) AS sort_order, COALESCE(uo.is_visible, 1) AS is_visible FROM users u LEFT JOIN user_order uo ON u.id = uo.user_id"
        if not include_hidden:
            query += " WHERE COALESCE(uo.is_visible, 1) = 1"
        query += " ORDER BY sort_order ASC, u.name ASC"
        cursor = conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der geordneten Benutzer: {e}")
        return list(get_all_users().values())


def save_user_order(order_data_list):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM user_order")
        cursor.executemany("INSERT INTO user_order (user_id, sort_order, is_visible) VALUES (?, ?, ?)", order_data_list)
        conn.commit()
        return True, "Reihenfolge und Sichtbarkeit erfolgreich gespeichert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Reihenfolge und Sichtbarkeit: {e}"
    finally:
        conn.close()


def update_user(user_id, data):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        data['urlaub_rest'] = data.get('urlaub_gesamt', 30)
        cursor.execute(
            "UPDATE users SET vorname = ?, name = ?, geburtstag = ?, telefon = ?, diensthund = ?, urlaub_gesamt = ?, urlaub_rest = ?, role = ?, entry_date = ? WHERE id = ?",
            (data['vorname'], data['name'], data['geburtstag'], data['telefon'], data['diensthund'],
             data['urlaub_gesamt'], data['urlaub_rest'], data['role'], data['entry_date'], user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def create_user_by_admin(data):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, geburtstag, telefon, diensthund, urlaub_gesamt, urlaub_rest, entry_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data['vorname'], data['name'], hash_password(data['password']), data['role'], data['geburtstag'],
             data['telefon'], data['diensthund'], data['urlaub_gesamt'], data['urlaub_gesamt'], data['entry_date']))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_user(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vacation_requests WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        cursor.execute("DELETE FROM user_order WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def add_vacation_request(user_id, start_date, end_date):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO vacation_requests (user_id, start_date, end_date, status, request_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "Ausstehend",
             date.today().strftime('%Y-%m-%d')))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_requests_by_user(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vacation_requests WHERE user_id = ? ORDER BY start_date DESC", (user_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_pending_vacation_requests():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT vr.id, u.vorname, u.name, vr.start_date, vr.end_date, vr.status FROM vacation_requests vr JOIN users u ON vr.user_id = u.id WHERE vr.status = 'Ausstehend' ORDER BY vr.request_date ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_vacation_request_status(request_id, new_status):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET status = ? WHERE id = ?", (new_status, request_id))
        conn.commit()
        return True, "Urlaubsstatus erfolgreich aktualisiert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_pending_vacation_requests_count():
    """Zählt die Anzahl der ausstehenden Urlaubsanträge."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vacation_requests WHERE status = 'Ausstehend'")
        count = cursor.fetchone()[0]
        return count
    except sqlite3.Error as e:
        print(f"Fehler beim Zählen der Urlaubsanträge: {e}")
        return 0
    finally:
        conn.close()


def set_user_tutorial_seen(user_id):
    """Setzt das Flag, dass der Benutzer das Tutorial gesehen hat."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"DB-Fehler beim Setzen des Tutorial-Status: {e}")
        return False
    finally:
        conn.close()