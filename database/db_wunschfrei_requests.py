# database/db_wunschfrei_requests.py
# NEU: Ausgelagerte Funktionen für Wunschfrei-Anträge (wunschfrei_requests)

import calendar
from datetime import date, datetime, timedelta
from .db_core import create_connection, _log_activity, _create_admin_notification
import mysql.connector

# Import der Hilfsfunktion aus dem neuen Urlaubs-Modul, da sie dort definiert wurde
try:
    from .db_vacation_requests import get_user_info_for_notification
except ImportError:
    # Fallback, falls die Datei noch nicht existiert (sollte nicht passieren)
    def get_user_info_for_notification(user_id):
        """ Holt Vorname und Name für Benachrichtigungen. """
        conn = create_connection()
        if conn is None: return None
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
        except mysql.connector.Error as e:
            print(f"DB Fehler in get_user_info_for_notification (Fallback): {e}")
            return None
        finally:
            if conn and conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()


# --- WUNSCHFREI-ANTRÄGE (WUNSCHFREI_REQUESTS) ---

def submit_user_request(user_id, request_date_str, requested_shift=None):
    """Reicht einen Wunschfrei-Antrag ein oder aktualisiert ihn."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor()
        shift_to_store = "WF" if requested_shift is None else requested_shift

        query = """
                INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, notified, \
                                                 rejection_reason, requested_by)
                VALUES (%s, %s, %s, 'Ausstehend', 0, NULL, 'user') ON DUPLICATE KEY \
                UPDATE \
                    requested_shift = \
                VALUES (requested_shift), status = 'Ausstehend', notified = 0, rejection_reason = NULL, requested_by = 'user' \
                """
        cursor.execute(query, (user_id, request_date_str, shift_to_store))
        conn.commit()
        _log_activity(cursor, user_id, "WUNSCHFREI_EINGEREICHT",
                      f"User {user_id} hat Wunsch '{shift_to_store}' für {request_date_str} eingereicht/aktualisiert.")
        return True, "Anfrage erfolgreich gestellt oder aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def admin_submit_request(user_id, request_date_str, requested_shift):
    """Reicht einen Wunschfrei-Antrag durch einen Admin ein oder aktualisiert ihn."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor()
        query = """
                INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, requested_by, notified, \
                                                 rejection_reason)
                VALUES (%s, %s, %s, 'Ausstehend', 'admin', 0, NULL) ON DUPLICATE KEY \
                UPDATE \
                    requested_shift = \
                VALUES (requested_shift), status = 'Ausstehend', requested_by = 'admin', notified = 0, rejection_reason = NULL \
                """
        cursor.execute(query, (user_id, request_date_str, requested_shift))
        conn.commit()
        _log_activity(cursor, None, "ADMIN_WUNSCHFREI_GESENDET",
                      f"Admin hat Wunsch '{requested_shift}' für User {user_id} am {request_date_str} gesendet/aktualisiert.")
        return True, "Anfrage erfolgreich an den Benutzer gesendet."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def user_respond_to_request(request_id, response):
    """Verarbeitet die Antwort eines Benutzers auf einen Wunschfrei-Antrag des Admins."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
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

        cursor.execute("SELECT user_id, request_date, requested_shift FROM wunschfrei_requests WHERE id=%s",
                       (request_id,))
        req_data = cursor.fetchone()
        user_id = req_data[0] if req_data else None
        date_str = req_data[1].strftime('%Y-%m-%d') if req_data and isinstance(req_data[1], date) else "Unbekannt"
        shift = req_data[2] if req_data else "Unbekannt"

        _log_activity(cursor, user_id, "USER_ANTWORT_WUNSCHFREI",
                      f"User {user_id} hat auf Admin-Anfrage ID {request_id} ({shift} am {date_str}) mit '{response}' geantwortet.")
        return True, "Antwort erfolgreich übermittelt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def withdraw_wunschfrei_request(request_id, user_id):
    """Zieht einen Wunschfrei-Antrag zurück (User-Aktion)."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    user_info_cursor = None
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id, user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE id = %s AND user_id = %s",
            (request_id, user_id))
        request_data = cursor.fetchone()

        if not request_data:
            return False, "Antrag nicht gefunden oder gehört nicht Ihnen."

        # User-Info holen
        user_info = get_user_info_for_notification(user_id)
        user_name = f"{user_info['vorname']} {user_info['name']}" if user_info else "Unbekannter Benutzer"

        try:
            req_date_obj = request_data['request_date']
            if isinstance(req_date_obj, str):
                req_date_obj = datetime.strptime(req_date_obj, '%Y-%m-%d').date()
            date_formatted = req_date_obj.strftime('%d.%m.%Y')
            date_sql_format = req_date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError) as e:
            print(f"Fehler bei Datumskonvertierung in withdraw_wunschfrei_request: {e}")
            return False, "Interner Datumsfehler bei Verarbeitung."

        # Antrag löschen
        cursor.execute("DELETE FROM wunschfrei_requests WHERE id = %s", (request_id,))

        shift_to_delete = None
        if request_data['status'] == 'Akzeptiert von Admin' or request_data['status'] == 'Akzeptiert von Benutzer' or \
                request_data['status'] == 'Genehmigt':
            shift_to_delete = 'X' if request_data['requested_shift'] == 'WF' else request_data['requested_shift']

        if shift_to_delete:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s AND shift_abbrev = %s",
                           (user_id, date_sql_format, shift_to_delete))
            details = f"Benutzer '{user_name}' hat akzeptierten/genehmigten Antrag (ID: {request_id}, Schicht: {shift_to_delete}) für {date_formatted} zurückgezogen. Schicht entfernt."
            _log_activity(cursor, user_id, "ANTRAG_AKZEPTIERT_ZURÜCKGEZOGEN", details)
            _create_admin_notification(details)
            msg = "Akzeptierter/Genehmigter Antrag wurde zurückgezogen und Schicht entfernt."
        else:
            details = f"Benutzer '{user_name}' hat Antrag (ID: {request_id}) für {date_formatted} zurückgezogen/gelöscht (Status war: {request_data['status']})."
            _log_activity(cursor, user_id, "ANTRAG_ZURÜCKGEZOGEN", details)
            msg = "Antrag wurde zurückgezogen/gelöscht."

        conn.commit()
        return True, msg
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            if user_info_cursor is not None:
                try:
                    user_info_cursor.close()
                except Exception:
                    pass
            conn.close()


def get_wunschfrei_requests_by_user_for_month(user_id, year, month):
    """Holt die Anzahl der NICHT ABGELEHNTEN WF-Wunschfrei-Anträge für einen Benutzer in einem Monat."""
    conn = create_connection()
    if conn is None: return 0
    cursor = None
    try:
        cursor = conn.cursor()
        try:
            start_date = date(year, month, 1).strftime('%Y-%m-01')
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day).strftime('%Y-%m-%d')
        except ValueError:
            print(f"Ungültiger Monat/Jahr in get_wunschfrei_requests_by_user_for_month: {year}-{month}")
            return 0

        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = %s AND request_date BETWEEN %s AND %s AND status NOT LIKE 'Abgelehnt%' AND requested_shift = 'WF'",
            (user_id, start_date, end_date)
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_wunschfrei_requests_by_user_for_month: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_pending_wunschfrei_requests():
    """Holt alle ausstehenden Wunschfrei-Anträge."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
                       SELECT wr.id, u.vorname, u.name, wr.request_date, wr.user_id, wr.requested_shift
                       FROM wunschfrei_requests wr
                                JOIN users u ON wr.user_id = u.id
                       WHERE wr.status = 'Ausstehend'
                       ORDER BY wr.request_date ASC
                       """)
        requests = cursor.fetchall()
        for req in requests:
            if isinstance(req['request_date'], date):
                req['request_date'] = req['request_date'].strftime('%Y-%m-%d')
        return requests
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_pending_wunschfrei_requests: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_pending_admin_requests_for_user(user_id):
    """Holt die Anzahl der vom Admin gestellten, ausstehenden Anträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM wunschfrei_requests WHERE user_id = %s AND requested_by = 'admin' AND status = 'Ausstehend'",
            (user_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_pending_admin_requests_for_user: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_wunschfrei_request_by_user_and_date(user_id, request_date_str):
    """Holt einen Wunschfrei-Antrag für einen Benutzer und ein Datum."""
    conn = create_connection()
    if conn is None: return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s",
            (user_id, request_date_str)
        )
        return cursor.fetchone()
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_wunschfrei_request_by_user_and_date: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_wunschfrei_request_by_id(request_id):
    """Holt einen Wunschfrei-Antrag anhand seiner ID."""
    conn = create_connection()
    if conn is None: return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM wunschfrei_requests WHERE id = %s", (request_id,))
        return cursor.fetchone()
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_wunschfrei_request_by_id: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_wunschfrei_requests_for_month(year, month):
    """Holt alle Wunschfrei-Anträge für einen gegebenen Monat."""
    conn = create_connection()
    if conn is None: return {}
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        try:
            start_date = date(year, month, 1).strftime('%Y-%m-01')
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day).strftime('%Y-%m-%d')
        except ValueError:
            print(f"Ungültiger Monat/Jahr in get_wunschfrei_requests_for_month: {year}-{month}")
            return {}

        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (start_date, end_date)
        )
        requests = {}
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            if user_id_str not in requests:
                requests[user_id_str] = {}

            req_date_str = row['request_date'].strftime('%Y-%m-%d') if isinstance(row['request_date'], date) else str(
                row['request_date'])
            requests[user_id_str][req_date_str] = (row['status'], row['requested_shift'], row['requested_by'],
                                                   None)  # None für Timestamp
        return requests
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Wunschfrei-Anträge für {year}-{month}: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def update_wunschfrei_status(request_id, new_status, reason=None):
    """Aktualisiert den Status eines Wunschfrei-Antrags (Admin-Aktion)."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
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
        _log_activity(cursor, None, "ADMIN_WUNSCHFREI_STATUS",
                      f"Admin hat Status für Wunschfrei-Antrag ID {request_id} auf '{final_status}' gesetzt.")
        return True, "Status erfolgreich aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_all_requests_by_user(user_id):
    """Holt alle Wunschfrei-Anträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = %s ORDER BY request_date DESC",
            (user_id,)
        )
        requests = cursor.fetchall()
        for req in requests:
            if isinstance(req['request_date'], date):
                req['request_date'] = req['request_date'].strftime('%Y-%m-%d')
        return requests
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_all_requests_by_user: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_unnotified_requests(user_id):
    """Holt unbenachrichtigte (abgeschlossene) Wunschfrei-Anträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason FROM wunschfrei_requests WHERE user_id = %s AND notified = 0 AND status != 'Ausstehend'",
            (user_id,)
        )
        requests = cursor.fetchall()
        for req in requests:
            if isinstance(req['request_date'], date):
                req['request_date'] = req['request_date'].strftime('%Y-%m-%d')
        return requests
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_unnotified_requests: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def mark_requests_as_notified(request_ids):
    """Markiert Wunschfrei-Anträge als benachrichtigt (für den User)."""
    if not request_ids: return False
    conn = create_connection()
    if conn is None: return False
    cursor = None
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(request_ids))
        query = f"UPDATE wunschfrei_requests SET notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Fehler in mark_requests_as_notified: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()