# database/db_vacation_requests.py
# NEU: Ausgelagerte Funktionen für Urlaubsanträge (vacation_requests)

import calendar
from datetime import date, datetime, timedelta
from .db_core import create_connection, _log_activity, _create_admin_notification
import mysql.connector

# --- HILFSFUNKTION (Wird von beiden Request-Typen benötigt) ---
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
          print(f"DB Fehler in get_user_info_for_notification: {e}")
          return None
     finally:
          if conn and conn.is_connected():
               if cursor is not None:
                    cursor.close()
               conn.close()
# --- ENDE HILFSFUNKTION ---


# --- URLAUBSANTRÄGE (VACATION_REQUESTS) ---

def add_vacation_request(user_id, start_date, end_date):
    """Fügt einen neuen Urlaubsantrag hinzu."""
    conn = create_connection()
    if conn is None: return False
    cursor = None # Vorab definieren
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO vacation_requests (user_id, start_date, end_date, status, request_date, user_notified, archived) VALUES (%s, %s, %s, %s, %s, 0, 0)", # user_notified, archived hinzugefügt
            (user_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "Ausstehend",
             date.today().strftime('%Y-%m-%d')))
        conn.commit()
        # Admin-Benachrichtigung (aus Original übernommen)
        user_info = get_user_info_for_notification(user_id)
        if user_info:
             message = f"Neuer Urlaubsantrag von {user_info['vorname']} {user_info['name']} ({start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m')})."
             # Annahme: _create_admin_notification braucht keinen cursor mehr
             _create_admin_notification(message, notification_type='vacation')
        else:
             _create_admin_notification(f"Neuer Urlaubsantrag von User ID {user_id}.", notification_type='vacation')
        return True
    except mysql.connector.Error as e:
        print(f"DB Fehler in add_vacation_request: {e}")
        conn.rollback() # Rollback hinzufügen
        return False
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_requests_by_user(user_id):
    """Holt alle Urlaubsanträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        # ID hinzugefügt für Stornierung durch User
        cursor.execute("SELECT id, user_id, start_date, end_date, status, request_date, archived FROM vacation_requests WHERE user_id = %s ORDER BY start_date DESC", (user_id,))
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_requests_by_user: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def cancel_vacation_request_by_user(request_id, user_id):
    """Ändert den Status eines ausstehenden Urlaubsantrags auf 'Storniert' (durch den User)."""
    conn = create_connection()
    if conn is None:
        return False, "Datenbankverbindung fehlgeschlagen."
    cursor = None
    try:
        cursor = conn.cursor()
        # Überprüfen, ob der Antrag existiert, dem Benutzer gehört und 'Ausstehend' ist
        cursor.execute("""
            SELECT status FROM vacation_requests
            WHERE id = %s AND user_id = %s
        """, (request_id, user_id))
        result = cursor.fetchone()

        if not result:
            return False, "Antrag nicht gefunden oder gehört nicht Ihnen."
        if result[0] != 'Ausstehend':
            return False, f"Antrag kann nicht storniert werden (Status: {result[0]})."

        # Status auf 'Storniert' setzen und user_notified auf 0 (Admin sieht es evtl.)
        cursor.execute("""
            UPDATE vacation_requests
            SET status = 'Storniert', user_notified = 0
            WHERE id = %s
        """, (request_id,))
        conn.commit()
        # Logging im Stil der Originaldatei (ohne admin_id, da User storniert)
        _log_activity(None, user_id, "URLAUB_STORNIERT_USER", # Angepasster Action Type
                      f"Benutzer (ID: {user_id}) hat Urlaubsantrag (ID: {request_id}) storniert.")
        return True, "Antrag erfolgreich storniert."

    except mysql.connector.Error as e:
        print(f"Fehler beim Stornieren des Urlaubsantrags {request_id} durch User {user_id}: {e}")
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_all_vacation_requests_for_admin():
    """Holt alle Urlaubsanträge für die Admin-Ansicht."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
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
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_all_vacation_requests_for_admin: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def delete_vacation_requests(request_ids):
    """Löscht Urlaubsanträge endgültig."""
    if not request_ids:
        return False, "Keine Anträge zum Löschen ausgewählt."
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(request_ids))
        query = f"DELETE FROM vacation_requests WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
        _log_activity(None, None, "URLAUB_GELÖSCHT", f"Urlaubsanträge IDs {request_ids} endgültig gelöscht.")
        return True, f"{cursor.rowcount} Urlaubsantrag/anträge endgültig gelöscht."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def update_vacation_request_status(request_id, new_status):
    """Aktualisiert den Status eines Urlaubsantrags (generisch)."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacation_requests SET status = %s, user_notified = 0 WHERE id = %s",
                       (new_status, request_id))
        conn.commit()
        _log_activity(None, None, "URLAUB_STATUS_UPDATE", f"Status für Urlaubsantrag ID {request_id} auf '{new_status}' gesetzt.")
        return True, "Urlaubsstatus erfolgreich aktualisiert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def approve_vacation_request(request_id, admin_id):
    """Genehmigt einen Urlaubsantrag durch Admin."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT user_id, start_date, end_date, status FROM vacation_requests WHERE id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."
        if request_data['status'] != 'Ausstehend':
             return False, f"Antrag hat bereits Status '{request_data['status']}'."

        cursor.execute("UPDATE vacation_requests SET status = 'Genehmigt', user_notified = 0 WHERE id = %s",
                       (request_id,))

        user_id = request_data['user_id']
        try:
             start_date_obj = request_data['start_date']
             end_date_obj = request_data['end_date']
             if isinstance(start_date_obj, str):
                  start_date_obj = datetime.strptime(start_date_obj, '%Y-%m-%d').date()
             if isinstance(end_date_obj, str):
                  end_date_obj = datetime.strptime(end_date_obj, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
             print(f"Fehler bei Datumskonvertierung in approve_vacation_request: {e}")
             conn.rollback()
             return False, "Fehler bei der Datumsverarbeitung."

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
            if cursor is not None:
                cursor.close()
            conn.close()


def cancel_vacation_request(request_id, admin_id):
    """Storniert einen genehmigten Urlaubsantrag durch Admin."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT user_id, start_date, end_date, status FROM vacation_requests WHERE id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."
        if request_data['status'] != 'Genehmigt':
            return False, "Nur bereits genehmigte Anträge können storniert werden."

        cursor.execute("UPDATE vacation_requests SET status = 'Storniert', user_notified = 0 WHERE id = %s",
                       (request_id,))

        user_id = request_data['user_id']
        try:
             start_date_obj = request_data['start_date']
             end_date_obj = request_data['end_date']
             if isinstance(start_date_obj, str):
                  start_date_obj = datetime.strptime(start_date_obj, '%Y-%m-%d').date()
             if isinstance(end_date_obj, str):
                  end_date_obj = datetime.strptime(end_date_obj, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
             print(f"Fehler bei Datumskonvertierung in cancel_vacation_request: {e}")
             conn.rollback()
             return False, "Fehler bei der Datumsverarbeitung."

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
            if cursor is not None:
                cursor.close()
            conn.close()


def archive_vacation_request(request_id, admin_id):
    """Archiviert einen Urlaubsantrag."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
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
            if cursor is not None:
                cursor.close()
            conn.close()


def get_pending_vacation_requests_count():
    """Gibt die Anzahl der ausstehenden, nicht archivierten Urlaubsanträge zurück."""
    conn = create_connection()
    if conn is None: return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vacation_requests WHERE status = 'Ausstehend' AND archived = 0")
        result = cursor.fetchone()
        return result[0] if result else 0
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der Urlaubsanträge: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_all_vacation_requests_for_month(year, month):
    """Holt alle nicht archivierten Urlaubsanträge, die einen gegebenen Monat überschneiden."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        try:
            start_of_month = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_of_month = date(year, month, last_day)
        except ValueError:
            print(f"Ungültiger Monat/Jahr in get_all_vacation_requests_for_month: {year}-{month}")
            return []

        query = "SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0"
        cursor.execute(query, (end_of_month.strftime('%Y-%m-%d'), start_of_month.strftime('%Y-%m-%d')))
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Urlaubsanträge für Monat {year}-{month}: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def get_unnotified_vacation_requests_for_user(user_id):
    """Holt unbenachrichtigte Urlaubsanträge für einen Benutzer."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, start_date, end_date, status FROM vacation_requests WHERE user_id = %s AND user_notified = 0 AND status != 'Ausstehend'",
            (user_id,)
        )
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_unnotified_vacation_requests_for_user: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def mark_vacation_requests_as_notified(request_ids):
    """Markiert Urlaubsanträge als benachrichtigt (für den User)."""
    if not request_ids: return False
    conn = create_connection()
    if conn is None: return False
    cursor = None
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(request_ids))
        query = f"UPDATE vacation_requests SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Fehler in mark_vacation_requests_as_notified: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()