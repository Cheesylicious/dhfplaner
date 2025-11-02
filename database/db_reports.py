# database/db_reports.py
from datetime import datetime
from .db_core import create_connection, _create_admin_notification
import mysql.connector
# NEU: Import für das Abrufen von Benutzernamen in der neuen Log-Funktion
from database.db_users import get_user_by_id

SEVERITY_ORDER = {
    "Kritischer Fehler": 5,
    "Mittlerer Fehler": 4,
    "Kleiner Fehler": 3,
    "Schönheitsfehler": 2,
    "Unwichtiger Fehler": 1
}


def create_bug_report(user_id, title, description, category):
    """Reicht einen Bug-Report ein, jetzt mit Kategorie."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(
            "INSERT INTO bug_reports (user_id, title, description, category, timestamp, status, user_notified) VALUES (%s, %s, %s, %s, %s, 'Neu', 1)",
            (user_id, title, description, category, timestamp)
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


def get_reports_awaiting_feedback_for_user(user_id):
    """Holt die IDs der Reports, die auf Feedback vom Benutzer warten."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM bug_reports WHERE user_id = %s AND status = 'Warte auf Rückmeldung' ORDER BY timestamp DESC",
            (user_id,))
        return [item[0] for item in cursor.fetchall()]
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_reports_with_user_feedback_count():
    """Gibt die Anzahl der Reports mit User-Feedback für den Admin zurück."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM bug_reports WHERE status IN ('Rückmeldung (Offen)', 'Rückmeldung (Behoben)')")
        count = cursor.fetchone()[0]
        return count
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der Bug-Reports mit User-Feedback: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def submit_user_feedback(report_id, is_fixed, user_note):
    """Speichert das Feedback des Benutzers und benachrichtigt den Admin."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT title FROM bug_reports WHERE id = %s", (report_id,))
        report = cursor.fetchone()
        report_title = report['title'] if report else "Unbekannt"

        new_status = "Rückmeldung (Behoben)" if is_fixed else "Rückmeldung (Offen)"

        formatted_note = ""
        if user_note:
            formatted_note = f"[User-Feedback am {datetime.now().strftime('%d.%m.%Y %H:%M')}]:\n{user_note}"

        # Hängt das User-Feedback an bestehende user_notes an
        cursor.execute(
            "UPDATE bug_reports SET status = %s, user_notes = CONCAT_WS('\n\n', user_notes, %s) WHERE id = %s",
            (new_status, formatted_note, report_id)
        )

        _create_admin_notification(cursor,
                                   f"User-Feedback zu '{report_title[:30]}...': Status ist jetzt '{new_status}'")

        conn.commit()
        return True, "Dein Feedback wurde erfolgreich übermittelt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_bug_reports():
    """Holt alle Bug-Reports und sortiert sie nach Schweregrad."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
                       SELECT b.id,
                              u.vorname,
                              u.name,
                              b.timestamp,
                              b.title,
                              b.description,
                              b.status,
                              b.category,
                              b.archived,
                              b.admin_notes,
                              b.user_notes
                       FROM bug_reports b
                                LEFT JOIN users u ON b.user_id = u.id
                       """)
        reports = cursor.fetchall()

        reports.sort(key=lambda r: (
            r.get('archived', 0),
            -SEVERITY_ORDER.get(r.get('category'), 0),
            r.get('timestamp')
        ), reverse=False)

        return reports
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
                       SELECT id, timestamp, title, description, status, category, admin_notes, user_notes
                       FROM bug_reports
                       WHERE archived = 0
                       """)
        reports = cursor.fetchall()
        reports.sort(key=lambda r: (-SEVERITY_ORDER.get(r.get('category'), 0), r.get('timestamp')), reverse=False)
        return reports
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_open_bug_reports_count():
    """Gibt die Anzahl der offenen Bug-Reports zurück (ohne die, die nur auf Feedback warten)."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM bug_reports WHERE status NOT IN ('Erledigt', 'Geschlossen', 'Rückmeldung (Behoben)') AND archived = 0")
        count = cursor.fetchone()[0]
        return count
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der offenen Bug-Reports: {e}")
        return 0
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
        # Setzt user_notes zurück, wenn der Admin den Fall wieder öffnet
        if new_status == "Warte auf Rückmeldung":
            cursor.execute("UPDATE bug_reports SET user_notes = NULL WHERE id = %s", (bug_id,))
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


def update_bug_report_category(report_id, new_category):
    """Aktualisiert die Kategorie eines Bug-Reports."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE bug_reports SET category = %s WHERE id = %s", (new_category, report_id))
        conn.commit()
        return True, "Kategorie aktualisiert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def append_admin_note(bug_id, note):
    """Hängt eine neue Admin-Notiz an einen Bug-Report an."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        timestamped_note = f"[Admin-Notiz am {datetime.now().strftime('%d.%m.%Y %H:%M')}]:\n{note}"
        cursor.execute(
            "UPDATE bug_reports SET admin_notes = CONCAT_WS('\n\n', admin_notes, %s) WHERE id = %s",
            (timestamped_note, bug_id)
        )
        conn.commit()
        return True, "Notiz hinzugefügt."
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
        cursor.execute("UPDATE bug_reports SET archived = 1 WHERE id = %s", (bug_id,))
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
    """Holt alle formatierten Log-Einträge, JETZT MIT ID."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # --- ÄNDERUNG: a.id HINZUGEFÜGT ---
        cursor.execute("""
                       SELECT a.id,
                              a.timestamp,
                              COALESCE(CONCAT(u.vorname, ' ', u.name), 'Unbekannt') as user_name,
                              a.action_type,
                              a.details
                       FROM activity_log a
                                LEFT JOIN users u ON a.user_id = u.id
                       ORDER BY a.timestamp DESC
                       """)
        # --- ENDE ÄNDERUNG ---
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_login_logout_logs_formatted():
    """
    Holt alle Login- und Logout-Protokolleinträge, formatiert den Benutzernamen
    und extrahiert die Sitzungsdauer für Logout-Einträge aus dem Detailfeld.
    JETZT MIT ID.
    """
    conn = create_connection()
    if conn is None:
        return []

    logs = []
    try:
        cursor = conn.cursor(dictionary=True)
        # Nur Login- und Logout-Einträge abrufen
        cursor.execute("""
                       SELECT id, timestamp, user_id, action_type, details
                       FROM activity_log
                       WHERE action_type IN ('USER_LOGIN', 'USER_LOGOUT')
                       ORDER BY id DESC
                       """)
        raw_logs = cursor.fetchall()

        # Sammle alle User-IDs für effizientes Abrufen der Namen
        user_ids = {log['user_id'] for log in raw_logs if log['user_id']}
        user_map = {}
        # Verwende get_user_by_id aus db_users für die Namen
        for user_id in user_ids:
            user_data = get_user_by_id(user_id)
            if user_data:
                user_map[user_id] = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            else:
                user_map[user_id] = f"Unbekannt (ID: {user_id})"

        for log in raw_logs:
            user_name = user_map.get(log['user_id'], 'System') if log['user_id'] else 'System'

            session_duration = ""
            if log['action_type'] == 'USER_LOGOUT':
                # Suche im Detail-String nach der Dauer, die nach 'Sitzungsdauer:' steht.
                details_parts = log['details'].split('Sitzungsdauer:')
                if len(details_parts) > 1:
                    duration_and_rest = details_parts[1].strip()
                    duration_end_index = duration_and_rest.find('.')
                    if duration_end_index != -1:
                        session_duration = duration_and_rest[:duration_end_index].strip()
                    else:
                        session_duration = duration_and_rest.strip()

            # --- ÄNDERUNG: log['id'] HINZUGEFÜGT ---
            logs.append({
                'id': log['id'],  # Hinzugefügt für die Löschfunktion
                'timestamp': log['timestamp'],
                'user_name': user_name,
                'action_type': log['action_type'],
                'details': log['details'],
                'duration': session_duration
            })
            # --- ENDE ÄNDERUNG ---

    except Exception as e:
        print(f"Fehler beim Abrufen der Protokoll-Logs: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return logs


# --- NEUE FUNKTION ---
def delete_activity_logs(log_ids):
    """Löscht Aktivitäts-Log-Einträge anhand ihrer IDs."""
    if not log_ids:
        return False, "Keine IDs zum Löschen übergeben."

    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()

        # Sicherstellen, dass die IDs Zahlen sind (Schutz vor SQL-Injection)
        safe_ids = [int(id_val) for id_val in log_ids]
        if not safe_ids:
            return False, "Keine gültigen IDs zum Löschen übergeben."

        placeholders = ', '.join(['%s'] * len(safe_ids))
        query = f"DELETE FROM activity_log WHERE id IN ({placeholders})"

        cursor.execute(query, tuple(safe_ids))
        conn.commit()

        rowcount = cursor.rowcount
        if rowcount > 0:
            return True, f"{rowcount} Protokolleintrag(s) erfolgreich gelöscht."
        else:
            return False, "Keine Einträge zum Löschen gefunden."

    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Löschen: {e}"
    except ValueError:
        conn.rollback()
        return False, "Ungültige ID(s) übergeben. Nur Zahlen sind erlaubt."
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
# --- ENDE NEUE FUNKTION ---