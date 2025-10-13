import calendar
from datetime import date, datetime, timedelta
from .db_core import create_connection, _log_activity, _create_admin_notification
import mysql.connector


def add_vacation_request(user_id, start_date, end_date):
    """Fügt einen neuen Urlaubsantrag hinzu."""
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
        print(f"DB Fehler in add_vacation_request: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_requests_by_user(user_id):
    """Holt alle Urlaubsanträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM vacation_requests WHERE user_id = %s ORDER BY start_date DESC", (user_id,))
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_vacation_requests_for_admin():
    """Holt alle Urlaubsanträge für die Admin-Ansicht."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT vr.id, u.id as user_id, u.vorname, u.name, vr.start_date, vr.end_date, vr.status, vr.archived
            FROM vacation_requests vr
            JOIN users u ON vr.user_id = u.id
            ORDER BY
                vr.archived,
                CASE vr.status
                    WHEN 'Ausstehend' THEN 1
                    WHEN 'Genehmigt' THEN 2
                    WHEN 'Storniert' THEN 3
                    WHEN 'Abgelehnt' THEN 4
                    ELSE 5
                END,
                vr.request_date ASC
        """)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_vacation_requests(request_ids):
    """Löscht Urlaubsanträge."""
    if not request_ids:
        return False, "Keine Anträge zum Löschen ausgewählt."
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(request_ids))
        query = f"DELETE FROM vacation_requests WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
        return True, f"{cursor.rowcount} Urlaubsantrag/anträge endgültig gelöscht."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_vacation_request_status(request_id, new_status):
    """Aktualisiert den Status eines Urlaubsantrags."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET status = %s, user_notified = 0 WHERE id = %s",
                       (new_status, request_id))
        conn.commit()
        return True, "Urlaubsstatus erfolgreich aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def approve_vacation_request(request_id, admin_id):
    """Genehmigt einen Urlaubsantrag."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM vacation_requests WHERE id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."

        cursor.execute("UPDATE vacation_requests SET status = 'Genehmigt', user_notified = 0 WHERE id = %s",
                       (request_id,))

        user_id = request_data['user_id']
        start_date_obj = datetime.strptime(request_data['start_date'], '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(request_data['end_date'], '%Y-%m-%d').date()

        current_date = start_date_obj
        while current_date <= end_date_obj:
            date_str = current_date.strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (%s, %s, 'U')
                ON DUPLICATE KEY UPDATE shift_abbrev = 'U'
            """, (user_id, date_str))
            current_date += timedelta(days=1)

        _log_activity(cursor, admin_id, "URLAUB_GENEHMIGT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) für Benutzer (ID: {user_id}) genehmigt.")

        conn.commit()
        return True, "Urlaubsantrag genehmigt und im Plan eingetragen."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def cancel_vacation_request(request_id, admin_id):
    """Storniert einen genehmigten Urlaubsantrag."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM vacation_requests WHERE id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."
        if request_data['status'] != 'Genehmigt':
            return False, "Nur bereits genehmigte Anträge können storniert werden."

        cursor.execute("UPDATE vacation_requests SET status = 'Storniert', user_notified = 0 WHERE id = %s",
                       (request_id,))

        user_id = request_data['user_id']
        start_date_obj = datetime.strptime(request_data['start_date'], '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(request_data['end_date'], '%Y-%m-%d').date()

        current_date = start_date_obj
        while current_date <= end_date_obj:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s AND shift_abbrev = 'U'",
                           (user_id, current_date.strftime('%Y-%m-%d')))
            current_date += timedelta(days=1)

        _log_activity(cursor, admin_id, "URLAUB_STORNIERT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) für Benutzer (ID: {user_id}) storniert.")
        conn.commit()
        return True, "Urlaub wurde storniert und aus dem Plan entfernt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def archive_vacation_request(request_id, admin_id):
    """Archiviert einen Urlaubsantrag."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET archived = 1 WHERE id = %s", (request_id,))
        _log_activity(cursor, admin_id, "URLAUB_ARCHIVIERT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) archiviert.")
        conn.commit()
        return True, "Urlaubsantrag wurde archiviert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Archivieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_pending_vacation_requests_count():
    """Gibt die Anzahl der ausstehenden Urlaubsanträge zurück."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vacation_requests WHERE status = 'Ausstehend' AND archived = 0")
        return cursor.fetchone()[0]
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der Urlaubsanträge: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_vacation_requests_for_month(year, month):
    """Holt alle Urlaubsanträge für einen gegebenen Monat."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        start_of_month = f"{year}-{month:02d}-01"
        _, last_day = calendar.monthrange(year, month)
        end_of_month = f"{year}-{month:02d}-{last_day:02d}"

        query = "SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0"
        cursor.execute(query, (end_of_month, start_of_month))
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Urlaubsanträge: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_unnotified_vacation_requests_for_user(user_id):
    """Holt unbenachrichtigte Urlaubsanträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, start_date, end_date, status FROM vacation_requests WHERE user_id = %s AND user_notified = 0",
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def mark_vacation_requests_as_notified(request_ids):
    """Markiert Urlaubsanträge als benachrichtigt."""
    if not request_ids: return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(request_ids))
        query = f"UPDATE vacation_requests SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def submit_user_request(user_id, request_date_str, requested_shift=None):
    """Reicht einen Wunschfrei-Antrag ein."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        shift_to_store = "WF" if requested_shift is None else requested_shift

        query = """
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, notified, rejection_reason, requested_by)
            VALUES (%s, %s, %s, 'Ausstehend', 0, NULL, 'user')
            ON DUPLICATE KEY UPDATE
                requested_shift = VALUES(requested_shift),
                status = 'Ausstehend',
                notified = 0,
                rejection_reason = NULL,
                requested_by = 'user'
        """
        cursor.execute(query, (user_id, request_date_str, shift_to_store))
        conn.commit()
        return True, "Anfrage erfolgreich gestellt oder aktualisiert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def admin_submit_request(user_id, request_date_str, requested_shift):
    """Reicht einen Wunschfrei-Antrag durch einen Admin ein."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, requested_by)
            VALUES (%s, %s, %s, 'Ausstehend', 'admin')
            ON DUPLICATE KEY UPDATE
                requested_shift = VALUES(requested_shift),
                status = 'Ausstehend',
                requested_by = 'admin'
        """
        cursor.execute(query, (user_id, request_date_str, requested_shift))
        conn.commit()
        return True, "Anfrage erfolgreich an den Benutzer gesendet."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def user_respond_to_request(request_id, response):
    """Verarbeitet die Antwort eines Benutzers auf einen Wunschfrei-Antrag."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        if response == 'Genehmigt':
            new_status = "Akzeptiert von Benutzer"
        elif response == 'Abgelehnt':
            new_status = "Abgelehnt von Benutzer"
        else:
            new_status = response
        cursor.execute("UPDATE wunschfrei_requests SET status = %s, notified = 1 WHERE id = %s",
                       (new_status, request_id))
        conn.commit()
        return True, "Antwort erfolgreich übermittelt."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def withdraw_wunschfrei_request(request_id, user_id):
    """Zieht einen Wunschfrei-Antrag zurück."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM wunschfrei_requests WHERE id = %s AND user_id = %s", (request_id, user_id))
        request_data = cursor.fetchone()

        if not request_data:
            return False, "Antrag nicht gefunden oder gehört nicht Ihnen."

        cursor.execute("DELETE FROM wunschfrei_requests WHERE id = %s", (request_id,))

        user_info_cursor = conn.cursor(dictionary=True)
        user_info_cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user = user_info_cursor.fetchone()
        user_name = f"{user['vorname']} {user['name']}" if user else "Unbekannter Benutzer"
        date_formatted = datetime.strptime(request_data['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')

        if "Akzeptiert" in request_data['status'] or "Genehmigt" in request_data['status']:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s",
                           (user_id, request_data['request_date']))
            details = f"Benutzer '{user_name}' hat akzeptierten Antrag für {date_formatted} zurückgezogen."
            _log_activity(cursor, user_id, "ANTRAG_AKZEPTIERT_ZURÜCKGEZOGEN", details)
            _create_admin_notification(cursor, details)
            msg = "Akzeptierter Antrag wurde zurückgezogen."
        else:
            details = f"Benutzer '{user_name}' hat Antrag für {date_formatted} zurückgezogen/gelöscht."
            _log_activity(cursor, user_id, "ANTRAG_ZURÜCKGEZOGEN", details)
            msg = "Antrag wurde zurückgezogen/gelöscht."

        conn.commit()
        return True, msg
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_wunschfrei_requests_by_user_for_month(user_id, year, month):
    """Holt die Anzahl der Wunschfrei-Anträge für einen Benutzer in einem Monat."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = %s AND request_date BETWEEN %s AND %s AND status NOT LIKE 'Abgelehnt%' AND requested_shift = 'WF'",
            (user_id, start_date, end_date)
        )
        return cursor.fetchone()[0]
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_pending_wunschfrei_requests():
    """Holt alle ausstehenden Wunschfrei-Anträge."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT wr.id, u.vorname, u.name, wr.request_date, wr.user_id, wr.requested_shift
            FROM wunschfrei_requests wr
            JOIN users u ON wr.user_id = u.id
            WHERE wr.status = 'Ausstehend'
            ORDER BY wr.request_date ASC
        """)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_pending_admin_requests_for_user(user_id):
    """Holt die Anzahl der vom Admin gestellten, ausstehenden Anträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = %s AND requested_by = 'admin' AND status = 'Ausstehend'",
            (user_id,)
        )
        return cursor.fetchone()[0]
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_wunschfrei_request_by_user_and_date(user_id, request_date_str):
    """Holt einen Wunschfrei-Antrag für einen Benutzer und ein Datum."""
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s",
            (user_id, request_date_str)
        )
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_wunschfrei_request_by_id(request_id):
    """Holt einen Wunschfrei-Antrag anhand seiner ID."""
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM wunschfrei_requests WHERE id = %s", (request_id,))
        return cursor.fetchone()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_wunschfrei_requests_for_month(year, month):
    """Holt alle Wunschfrei-Anträge für einen gegebenen Monat."""
    conn = create_connection()
    if conn is None: return {}
    try:
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (start_date, end_date)
        )
        requests = {}
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            if user_id_str not in requests:
                requests[user_id_str] = {}
            requests[user_id_str][row['request_date']] = (row['status'], row['requested_shift'], row['requested_by'])
        return requests
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_wunschfrei_status(request_id, new_status, reason=None):
    """Aktualisiert den Status eines Wunschfrei-Antrags."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        if new_status == 'Genehmigt':
            final_status = 'Akzeptiert von Admin'
        elif new_status == 'Abgelehnt':
            final_status = 'Abgelehnt von Admin'
        else:
            final_status = new_status

        cursor.execute(
            "UPDATE wunschfrei_requests SET status = %s, notified = 0, rejection_reason = %s WHERE id = %s",
            (final_status, reason, request_id)
        )
        conn.commit()
        return True, "Status erfolgreich aktualisiert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_requests_by_user(user_id):
    """Holt alle Wunschfrei-Anträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = %s ORDER BY request_date DESC",
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_unnotified_requests(user_id):
    """Holt unbenachrichtigte Wunschfrei-Anträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason FROM wunschfrei_requests WHERE user_id = %s AND notified = 0 AND status != 'Ausstehend'",
            (user_id,)
        )
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def mark_requests_as_notified(request_ids):
    """Markiert Wunschfrei-Anträge als benachrichtigt."""
    if not request_ids: return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(request_ids))
        query = f"UPDATE wunschfrei_requests SET notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()