# database/db_requests.py
import sqlite3
import calendar
from datetime import date, datetime, timedelta
from .db_core import create_connection, _log_activity, _create_admin_notification

def add_vacation_request(user_id, start_date, end_date):
    """Adds a new vacation request."""
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
    """Fetches all vacation requests for a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vacation_requests WHERE user_id = ? ORDER BY start_date DESC", (user_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_all_vacation_requests_for_admin():
    """Fetches all vacation requests for the admin view."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
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
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_vacation_requests(request_ids):
    """Deletes vacation requests."""
    if not request_ids:
        return False, "Keine Anträge zum Löschen ausgewählt."
    conn = create_connection()
    try:
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in request_ids)
        query = f"DELETE FROM vacation_requests WHERE id IN ({placeholders})"
        cursor.execute(query, request_ids)
        conn.commit()
        return True, f"{cursor.rowcount} Urlaubsantrag/anträge endgültig gelöscht."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def update_vacation_request_status(request_id, new_status):
    """Updates the status of a vacation request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET status = ?, user_notified = 0 WHERE id = ?",
                       (new_status, request_id))
        conn.commit()
        return True, "Urlaubsstatus erfolgreich aktualisiert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def approve_vacation_request(request_id, admin_id):
    """Approves a vacation request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        cursor.execute("SELECT * FROM vacation_requests WHERE id = ?", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            conn.rollback()
            return False, "Antrag nicht gefunden."

        cursor.execute("UPDATE vacation_requests SET status = 'Genehmigt', user_notified = 0 WHERE id = ?",
                       (request_id,))

        user_id = request_data['user_id']
        start_date = datetime.strptime(request_data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request_data['end_date'], '%Y-%m-%d').date()

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (?, ?, 'U')
                ON CONFLICT(user_id, shift_date) DO UPDATE SET shift_abbrev = 'U';
            """, (user_id, date_str))
            current_date += timedelta(days=1)

        _log_activity(cursor, admin_id, "URLAUB_GENEHMIGT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) für Benutzer (ID: {user_id}) genehmigt.")

        conn.commit()
        return True, "Urlaubsantrag genehmigt und im Plan eingetragen."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    except Exception as e:
        conn.rollback()
        return False, f"Ein unerwarteter Fehler ist aufgetreten: {e}"
    finally:
        conn.close()


def cancel_vacation_request(request_id, admin_id):
    """Cancels an approved vacation request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")

        cursor.execute("SELECT * FROM vacation_requests WHERE id = ?", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."
        if request_data['status'] != 'Genehmigt':
            return False, "Nur bereits genehmigte Anträge können storniert werden."

        cursor.execute("UPDATE vacation_requests SET status = 'Storniert', user_notified = 0 WHERE id = ?",
                       (request_id,))

        user_id = request_data['user_id']
        start_date = datetime.strptime(request_data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request_data['end_date'], '%Y-%m-%d').date()

        current_date = start_date
        while current_date <= end_date:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = ? AND shift_date = ? AND shift_abbrev = 'U'",
                           (user_id, current_date.strftime('%Y-%m-%d')))
            current_date += timedelta(days=1)

        _log_activity(cursor, admin_id, "URLAUB_STORNIERT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) für Benutzer (ID: {user_id}) storniert.")
        conn.commit()
        return True, "Urlaub wurde storniert und aus dem Plan entfernt."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def archive_vacation_request(request_id, admin_id):
    """Archives a vacation request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET archived = 1 WHERE id = ?", (request_id,))
        _log_activity(cursor, admin_id, "URLAUB_ARCHIVIERT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) archiviert.")
        conn.commit()
        return True, "Urlaubsantrag wurde archiviert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Archivieren: {e}"
    finally:
        conn.close()


def get_pending_vacation_requests_count():
    """Gets the count of pending vacation requests."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vacation_requests WHERE status = 'Ausstehend' AND archived = 0")
        count = cursor.fetchone()[0]
        return count
    except sqlite3.Error as e:
        print(f"Fehler beim Zählen der Urlaubsanträge: {e}")
        return 0
    finally:
        conn.close()


def get_all_vacation_requests_for_month(year, month):
    """Fetches all vacation requests for a given month."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_of_month = f"{year}-{month:02d}-01"
        _, last_day = calendar.monthrange(year, month)
        end_of_month = f"{year}-{month:02d}-{last_day:02d}"

        query = """
            SELECT * FROM vacation_requests
            WHERE (start_date <= ? AND end_date >= ?) AND archived = 0
        """
        cursor.execute(query, (end_of_month, start_of_month))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der Urlaubsanträge: {e}")
        return []
    finally:
        conn.close()


def get_unnotified_vacation_requests_for_user(user_id):
    """Fetches unnotified vacation requests for a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, start_date, end_date, status FROM vacation_requests WHERE user_id = ? AND user_notified = 0",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_vacation_requests_as_notified(request_ids):
    """Marks vacation requests as notified."""
    if not request_ids:
        return
    conn = create_connection()
    try:
        cursor = conn.cursor()
        placeholders = ', '.join('?' for _ in request_ids)
        query = f"UPDATE vacation_requests SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, request_ids)
        conn.commit()
    finally:
        conn.close()

def submit_user_request(user_id, request_date_str, requested_shift=None):
    """Submits a wunschfrei request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        shift_to_store = "WF" if requested_shift is None else requested_shift

        cursor.execute("""
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, notified, rejection_reason, requested_by)
            VALUES (?, ?, ?, 'Ausstehend', 0, NULL, 'user')
            ON CONFLICT(user_id, request_date) DO UPDATE SET
                requested_shift = excluded.requested_shift,
                status = 'Ausstehend',
                notified = 0,
                rejection_reason = NULL,
                requested_by = 'user';
        """, (user_id, request_date_str, shift_to_store))

        conn.commit()
        return True, "Anfrage erfolgreich gestellt oder aktualisiert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def admin_submit_request(user_id, request_date_str, requested_shift):
    """Submits a wunschfrei request by an admin."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, requested_by)
            VALUES (?, ?, ?, 'Ausstehend', 'admin')
            ON CONFLICT(user_id, request_date) DO UPDATE SET
                requested_shift = excluded.requested_shift,
                status = 'Ausstehend',
                requested_by = 'admin';
        """, (user_id, request_date_str, requested_shift))
        conn.commit()
        return True, "Anfrage erfolgreich an den Benutzer gesendet."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def user_respond_to_request(request_id, response):
    """Handles a user's response to a wunschfrei request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        if response == 'Genehmigt':
            new_status = "Akzeptiert von Benutzer"
        elif response == 'Abgelehnt':
            new_status = "Abgelehnt von Benutzer"
        else:
            new_status = response
        cursor.execute("UPDATE wunschfrei_requests SET status = ?, notified = 1 WHERE id = ?", (new_status, request_id))
        conn.commit()
        return True, "Antwort erfolgreich übermittelt."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def withdraw_wunschfrei_request(request_id, user_id):
    """Withdraws a wunschfrei request."""
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

        log_status = None
        if "Akzeptiert" in status or "Genehmigt" in status:
            log_status = 'Genehmigt'
        elif "Abgelehnt" in status:
            log_status = 'Abgelehnt'
        elif status == 'Ausstehend':
            log_status = 'Ausstehend'
        else:
            conn.rollback()
            return False, "Dieser Antrag kann nicht zurückgezogen werden."

        cursor.execute("DELETE FROM wunschfrei_requests WHERE id = ?", (request_id,))

        user_info_cursor = conn.cursor()
        user_info_cursor.execute("SELECT vorname, name FROM users WHERE id = ?", (user_id,))
        user = user_info_cursor.fetchone()
        user_name = f"{user['vorname']} {user['name']}" if user else "Unbekannter Benutzer"

        date_formatted = datetime.strptime(request_date, '%Y-%m-%d').strftime('%d.%m.%Y')

        if log_status == 'Genehmigt':
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = ? AND shift_date = ?",
                           (user_id, request_date))
            details = f"Benutzer '{user_name}' hat akzeptierten Antrag für {date_formatted} zurückgezogen."
            _log_activity(cursor, user_id, "ANTRAG_AKZEPTIERT_ZURÜCKGEZOGEN", details)
            _create_admin_notification(cursor, details)
            msg = "Akzeptierter Antrag wurde zurückgezogen."
        elif log_status == 'Ausstehend':
            details = f"Benutzer '{user_name}' hat ausstehenden Antrag für {date_formatted} zurückgezogen."
            _log_activity(cursor, user_id, "ANTRAG_AUSSTEHEND_ZURÜCKGEZOGEN", details)
            msg = "Ausstehender Antrag wurde zurückgezogen."
        elif log_status == 'Abgelehnt':
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
    """Fetches wunschfrei requests for a user for a given month."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = ? AND request_date BETWEEN ? AND ? AND status NOT LIKE 'Abgelehnt%' AND requested_shift = 'WF'",
            (user_id, start_date, end_date)
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_pending_wunschfrei_requests():
    """Fetches all pending wunschfrei requests."""
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


def get_pending_admin_requests_for_user(user_id):
    """Fetches the count of pending admin-initiated requests for a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = ? AND requested_by = 'admin' AND status = 'Ausstehend'",
            (user_id,)
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_wunschfrei_request_by_user_and_date(user_id, request_date_str):
    """Fetches a wunschfrei request by user and date."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = ? AND request_date = ?",
            (user_id, request_date_str)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_wunschfrei_request_by_id(request_id):
    """Fetches a wunschfrei request by its ID."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wunschfrei_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_wunschfrei_requests_for_month(year, month):
    """Fetches all wunschfrei requests for a given month."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN ? AND ?",
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
        conn.close()


def update_wunschfrei_status(request_id, new_status, reason=None):
    """Updates the status of a wunschfrei request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()

        if new_status == 'Genehmigt':
            final_status = 'Akzeptiert von Admin'
        elif new_status == 'Abgelehnt':
            final_status = 'Abgelehnt von Admin'
        else:
            final_status = new_status

        cursor.execute(
            "UPDATE wunschfrei_requests SET status = ?, notified = 0, rejection_reason = ? WHERE id = ?",
            (final_status, reason, request_id)
        )
        conn.commit()
        return True, "Status erfolgreich aktualisiert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_all_requests_by_user(user_id):
    """Fetches all wunschfrei requests for a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = ? ORDER BY request_date DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_unnotified_requests(user_id):
    """Fetches unnotified wunschfrei requests for a user."""
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
    """Marks wunschfrei requests as notified."""
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