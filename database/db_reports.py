# database/db_reports.py
import sqlite3
from datetime import datetime
from .db_core import create_connection, _create_admin_notification

def submit_bug_report(user_id, title, description):
    """Submits a bug report."""
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
    """Gets the count of open bug reports."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bug_reports WHERE status != 'Erledigt' AND archived = 0")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_all_bug_reports():
    """Fetches all bug reports."""
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
    """Fetches all visible bug reports."""
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
    """Updates the status of a bug report."""
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
    """Updates the admin notes for a bug report."""
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
    """Archives a bug report."""
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
    """Unarchives a bug report."""
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
    """Deletes bug reports."""
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
    """Fetches unnotified bug reports for a user."""
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
    """Marks bug reports as notified."""
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


def get_all_logs_formatted():
    """Fetches all formatted logs."""
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