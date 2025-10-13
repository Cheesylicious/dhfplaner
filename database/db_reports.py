from datetime import datetime
from .db_core import create_connection, _create_admin_notification
import mysql.connector

def submit_bug_report(user_id, title, description):
    """Reicht einen Bug-Report ein."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True) # dictionary=True, um auf Spalten per Namen zugreifen zu können
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO bug_reports (user_id, title, description, timestamp, user_notified) VALUES (%s, %s, %s, %s, 1)",
            (user_id, title, description, timestamp)
        )

        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user_role_result = cursor.fetchone()
        if user_role_result and user_role_result['role'] not in ["Admin", "SuperAdmin"]:
            _create_admin_notification(cursor, "Ein neuer Bug-Report wurde eingereicht.")

        conn.commit()
        return True, "Bug-Report erfolgreich übermittelt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_open_bug_reports_count():
    """Gibt die Anzahl der offenen Bug-Reports zurück."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bug_reports WHERE status != 'Erledigt' AND archived = 0")
        return cursor.fetchone()[0]
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_bug_reports():
    """Holt alle Bug-Reports."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.id, u.vorname, u.name, b.timestamp, b.title, b.description, b.status, b.archived, b.admin_notes
            FROM bug_reports b
            JOIN users u ON b.user_id = u.id
            ORDER BY b.archived ASC, b.timestamp DESC
        """)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_visible_bug_reports():
    """Holt alle sichtbaren (nicht archivierten) Bug-Reports."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.id, b.timestamp, b.title, b.description, b.status, b.admin_notes
            FROM bug_reports b
            WHERE b.archived = 0
            ORDER BY b.timestamp DESC
        """)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_bug_report_status(bug_id, new_status):
    """Aktualisiert den Status eines Bug-Reports."""
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
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_bug_report_notes(bug_id, notes):
    """Aktualisiert die Admin-Notizen für einen Bug-Report."""
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
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def archive_bug_report(bug_id):
    """Archiviert einen Bug-Report."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute( "UPDATE bug_reports SET archived = 1 WHERE id = %s", (bug_id,))
        conn.commit()
        return True, "Bug-Report wurde archiviert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def unarchive_bug_report(bug_id):
    """Macht die Archivierung eines Bug-Reports rückgängig."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE bug_reports SET archived = 0 WHERE id = %s", (bug_id,))
        conn.commit()
        return True, "Bug-Report wurde wiederhergestellt."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_bug_reports(report_ids):
    """Löscht Bug-Reports."""
    if not report_ids: return False, "Keine IDs zum Löschen übergeben."

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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_unnotified_bug_reports_for_user(user_id):
    """Holt unbenachrichtigte Bug-Reports für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, title, status FROM bug_reports WHERE user_id = %s AND user_notified = 0",
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def mark_bug_reports_as_notified(report_ids):
    """Markiert Bug-Reports als benachrichtigt."""
    if not report_ids: return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(report_ids))
        query = f"UPDATE bug_reports SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(report_ids))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_logs_formatted():
    """Holt alle formatierten Log-Einträge."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # MySQL verwendet die CONCAT()-Funktion statt '||'
        cursor.execute("""
            SELECT
                a.timestamp,
                COALESCE(CONCAT(u.vorname, ' ', u.name), 'Unbekannt') as user_name,
                a.action_type,
                a.details
            FROM activity_log a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.timestamp DESC
        """)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()