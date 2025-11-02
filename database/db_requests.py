import calendar
from datetime import date, datetime, timedelta
# Angepasst: _log_activity und _create_admin_notification werden direkt aus db_core importiert (Annahme)
from .db_core import create_connection, _log_activity, _create_admin_notification
import mysql.connector

# --- HILFSFUNKTION (aus Original übernommen, ggf. anpassen falls sie woanders liegt) ---
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

# --- NEUE FUNKTION: Stornierung durch den Benutzer ---
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
        # Optional: Admin Benachrichtigung?
        # user_info = get_user_info_for_notification(user_id)
        # if user_info:
        #      message = f"{user_info['vorname']} {user_info['name']} hat Urlaubsantrag ID {request_id} storniert."
        #      _create_admin_notification(message, notification_type='vacation_cancel')
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
# --- ENDE NEUE FUNKTION ---


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
        # Datumsformate prüfen/konvertieren falls nötig (Annahme: DB liefert korrekte Strings/Date-Objekte)
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
        # Logging hinzufügen (optional)
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
        # Setzt user_notified auf 0, damit User benachrichtigt wird
        cursor.execute("UPDATE vacation_requests SET status = %s, user_notified = 0 WHERE id = %s",
                       (new_status, request_id))
        conn.commit()
        # Logging (ohne Admin-ID, da generisch)
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
        cursor = conn.cursor(dictionary=True) # Dictionary für einfachen Zugriff

        # Antrag holen
        cursor.execute("SELECT user_id, start_date, end_date, status FROM vacation_requests WHERE id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."
        # Nur ausstehende Anträge genehmigen
        if request_data['status'] != 'Ausstehend':
             return False, f"Antrag hat bereits Status '{request_data['status']}'."

        # Status aktualisieren
        cursor.execute("UPDATE vacation_requests SET status = 'Genehmigt', user_notified = 0 WHERE id = %s",
                       (request_id,))

        # Daten für Schichtplan holen
        user_id = request_data['user_id']
        # Konvertiere Datumstrings sicher zu Date-Objekten
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

        # 'U'-Einträge im Schichtplan erstellen/aktualisieren
        current_date = start_date_obj
        while current_date <= end_date_obj:
            date_str = current_date.strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (%s, %s, 'U')
                ON DUPLICATE KEY UPDATE shift_abbrev = 'U'
            """, (user_id, date_str)) # Korrigiert: shift_date und shift_abbrev für shift_schedule
            current_date += timedelta(days=1)

        # Logging im Stil der Originaldatei
        _log_activity(cursor, admin_id, "URLAUB_GENEHMIGT",
                      f"Admin (ID: {admin_id}) hat Urlaubsantrag (ID: {request_id}) für Benutzer (ID: {user_id}) genehmigt.")

        conn.commit()
        return True, "Urlaubsantrag genehmigt und im Plan eingetragen."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            # Stelle sicher, dass der Cursor existiert, bevor er geschlossen wird
            if cursor is not None:
                cursor.close()
            conn.close()


def cancel_vacation_request(request_id, admin_id):
    """Storniert einen genehmigten Urlaubsantrag durch Admin."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True) # Dictionary für einfachen Zugriff

        # Antrag holen
        cursor.execute("SELECT user_id, start_date, end_date, status FROM vacation_requests WHERE id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Antrag nicht gefunden."
        if request_data['status'] != 'Genehmigt':
            return False, "Nur bereits genehmigte Anträge können storniert werden."

        # Status aktualisieren
        cursor.execute("UPDATE vacation_requests SET status = 'Storniert', user_notified = 0 WHERE id = %s",
                       (request_id,))

        # Daten für Schichtplan holen
        user_id = request_data['user_id']
        # Konvertiere Datumstrings sicher zu Date-Objekten
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

        # 'U'-Einträge im Schichtplan löschen
        current_date = start_date_obj
        while current_date <= end_date_obj:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s AND shift_abbrev = 'U'", # Korrigiert: shift_date und shift_abbrev
                           (user_id, current_date.strftime('%Y-%m-%d')))
            current_date += timedelta(days=1)

        # Logging im Stil der Originaldatei
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
        # Logging im Stil der Originaldatei
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
        # Korrekte Datumsberechnung für Monatsanfang/-ende
        try:
            start_of_month = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_of_month = date(year, month, last_day)
        except ValueError:
            print(f"Ungültiger Monat/Jahr in get_all_vacation_requests_for_month: {year}-{month}")
            return []

        # Überschneidungslogik: (Antragsende >= Monatsanfang) AND (Antragsanfang <= Monatsende)
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
        # Prüft das Feld 'user_notified'
        cursor.execute(
            "SELECT id, start_date, end_date, status FROM vacation_requests WHERE user_id = %s AND user_notified = 0 AND status != 'Ausstehend'", # Nur abgeschlossene (nicht Ausstehend)
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
    if not request_ids: return False # Geändert auf False returnen
    conn = create_connection()
    if conn is None: return False
    cursor = None
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(request_ids))
        query = f"UPDATE vacation_requests SET user_notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
        return True # Erfolg zurückgeben
    except mysql.connector.Error as e:
        print(f"DB Fehler in mark_vacation_requests_as_notified: {e}")
        conn.rollback()
        return False # Misserfolg zurückgeben
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()


def submit_user_request(user_id, request_date_str, requested_shift=None):
    """Reicht einen Wunschfrei-Antrag ein oder aktualisiert ihn."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None
    try:
        cursor = conn.cursor()
        shift_to_store = "WF" if requested_shift is None else requested_shift

        # ON DUPLICATE KEY UPDATE Logik aus Original übernommen
        # KORREKTUR: Entferne 'timestamp' aus INSERT und UPDATE
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
        # Parameter: (user_id, request_date_str, shift_to_store)
        cursor.execute(query, (user_id, request_date_str, shift_to_store))
        conn.commit()
        # Logging
        _log_activity(cursor, user_id, "WUNSCHFREI_EINGEREICHT", f"User {user_id} hat Wunsch '{shift_to_store}' für {request_date_str} eingereicht/aktualisiert.")
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
        # ON DUPLICATE KEY UPDATE Logik aus Original übernommen
        # KORREKTUR: Entferne 'timestamp' aus INSERT und UPDATE
        query = """
            INSERT INTO wunschfrei_requests (user_id, request_date, requested_shift, status, requested_by, notified, rejection_reason)
            VALUES (%s, %s, %s, 'Ausstehend', 'admin', 0, NULL)
            ON DUPLICATE KEY UPDATE
                requested_shift = VALUES(requested_shift),
                status = 'Ausstehend',
                requested_by = 'admin',
                notified = 0,
                rejection_reason = NULL
        """
        # Parameter: (user_id, request_date_str, requested_shift)
        cursor.execute(query, (user_id, request_date_str, requested_shift))
        conn.commit()
        # Logging
        _log_activity(cursor, None, "ADMIN_WUNSCHFREI_GESENDET", f"Admin hat Wunsch '{requested_shift}' für User {user_id} am {request_date_str} gesendet/aktualisiert.")
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
        # Status Mapping aus Original übernommen
        if response == 'Genehmigt':
            new_status = "Akzeptiert von Benutzer"
        elif response == 'Abgelehnt':
            new_status = "Abgelehnt von Benutzer"
        else:
            # Ungültige Antwort? Im Original nicht behandelt, hier vielleicht Fehler werfen?
            # return False, "Ungültige Antwort."
            new_status = response # Behalte Verhalten bei

        # Setzt notified auf 0 (damit Admin die Antwort sieht?) oder 1 (damit User keine weitere Benachrichtigung bekommt)?
        # Original setzt notified=1. Behalte das bei.
        cursor.execute("UPDATE wunschfrei_requests SET status = %s, notified = 1 WHERE id = %s",
                       (new_status, request_id))
        conn.commit()
        # Logging (Annahme: User-ID wird benötigt)
        cursor.execute("SELECT user_id, request_date, requested_shift FROM wunschfrei_requests WHERE id=%s", (request_id,))
        req_data = cursor.fetchone()
        user_id = req_data[0] if req_data else None
        date_str = req_data[1].strftime('%Y-%m-%d') if req_data and isinstance(req_data[1], date) else "Unbekannt"
        shift = req_data[2] if req_data else "Unbekannt"
        _log_activity(cursor, user_id, "USER_ANTWORT_WUNSCHFREI", f"User {user_id} hat auf Admin-Anfrage ID {request_id} ({shift} am {date_str}) mit '{response}' geantwortet.")
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
    user_info_cursor = None # Eigener Cursor für User-Info
    try:
        cursor = conn.cursor(dictionary=True)

        # Antrag holen
        cursor.execute("SELECT id, user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE id = %s AND user_id = %s", (request_id, user_id))
        request_data = cursor.fetchone()

        if not request_data:
            return False, "Antrag nicht gefunden oder gehört nicht Ihnen."

        # User-Info holen (aus Original übernommen)
        user_info_cursor = conn.cursor(dictionary=True)
        user_info_cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user = user_info_cursor.fetchone()
        user_name = f"{user['vorname']} {user['name']}" if user else "Unbekannter Benutzer"
        user_info_cursor.close() # Cursor explizit schließen

        # Datum formatieren (aus Original übernommen)
        # Konvertiere Datumstrings sicher zu Date-Objekten und dann zu String
        try:
             req_date_obj = request_data['request_date']
             if isinstance(req_date_obj, str):
                  req_date_obj = datetime.strptime(req_date_obj, '%Y-%m-%d').date()
             date_formatted = req_date_obj.strftime('%d.%m.%Y')
             date_sql_format = req_date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError) as e:
             print(f"Fehler bei Datumskonvertierung in withdraw_wunschfrei_request (Originalteil): {e}")
             return False, "Interner Datumsfehler bei Verarbeitung."

        # Antrag löschen
        cursor.execute("DELETE FROM wunschfrei_requests WHERE id = %s", (request_id,))

        # Wenn genehmigt/akzeptiert, auch aus Schichtplan löschen
        shift_to_delete = None
        if request_data['status'] == 'Akzeptiert von Admin' or request_data['status'] == 'Akzeptiert von Benutzer' or request_data['status'] == 'Genehmigt':
            shift_to_delete = 'X' if request_data['requested_shift'] == 'WF' else request_data['requested_shift']

        if shift_to_delete:
            # Korrigiert: Nutze korrekte Spaltennamen für shift_schedule
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s AND shift_abbrev = %s",
                           (user_id, date_sql_format, shift_to_delete))
            details = f"Benutzer '{user_name}' hat akzeptierten/genehmigten Antrag (ID: {request_id}, Schicht: {shift_to_delete}) für {date_formatted} zurückgezogen. Schicht entfernt."
            _log_activity(cursor, user_id, "ANTRAG_AKZEPTIERT_ZURÜCKGEZOGEN", details)
            _create_admin_notification(details) # Admin informieren
            msg = "Akzeptierter/Genehmigter Antrag wurde zurückgezogen und Schicht entfernt."
        else:
            # Antrag war 'Ausstehend' oder 'Abgelehnt' etc.
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
            # Sicherstellen, dass user_info_cursor geschlossen wird, falls er geöffnet wurde
            if user_info_cursor is not None:
                 try:
                      user_info_cursor.close()
                 except Exception: # Ignoriere Fehler, falls schon geschlossen
                      pass
            conn.close()


def get_wunschfrei_requests_by_user_for_month(user_id, year, month):
    """Holt die Anzahl der NICHT ABGELEHNTEN WF-Wunschfrei-Anträge für einen Benutzer in einem Monat."""
    conn = create_connection()
    if conn is None: return 0
    cursor = None
    try:
        cursor = conn.cursor()
        # Korrekte Datumsberechnung für Monatsanfang/-ende
        try:
            start_date = date(year, month, 1).strftime('%Y-%m-01')
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day).strftime('%Y-%m-%d')
        except ValueError:
            print(f"Ungültiger Monat/Jahr in get_wunschfrei_requests_by_user_for_month: {year}-{month}")
            return 0

        # Zählt nur WF Anträge, die nicht 'Abgelehnt...' sind
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


# --- Diese Funktion heißt im Original get_pending_wunschfrei_requests ---
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
        # Datum ggf. konvertieren
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
# --- Ende ---

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
        # Korrekte Datumsberechnung
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
            # Konvertiere Datum zu String
            req_date_str = row['request_date'].strftime('%Y-%m-%d') if isinstance(row['request_date'], date) else str(row['request_date'])
            # --- KORREKTUR: Timestamp-Platzhalter entfernt, wie im Original ---
            requests[user_id_str][req_date_str] = (row['status'], row['requested_shift'], row['requested_by'], None) # None für Timestamp
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

        # Status-Mapping aus Original übernommen
        if new_status == 'Genehmigt':
            final_status = 'Akzeptiert von Admin'
        elif new_status == 'Abgelehnt':
            final_status = 'Abgelehnt von Admin'
        else:
            final_status = new_status # z.B. 'Ausstehend'

        # Setzt notified=0 und ggf. rejection_reason
        cursor.execute(
            "UPDATE wunschfrei_requests SET status = %s, notified = 0, rejection_reason = %s WHERE id = %s",
            (final_status, reason, request_id)
        )
        conn.commit()
        # Logging (Admin-ID fehlt hier im Original, daher None)
        _log_activity(cursor, None, "ADMIN_WUNSCHFREI_STATUS", f"Admin hat Status für Wunschfrei-Antrag ID {request_id} auf '{final_status}' gesetzt.")
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
    """Holt alle Wunschfrei-Anträge für einen Benutzer (ggf. redundant zu get_my_requests?)."""
    conn = create_connection()
    if conn is None: return []
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, request_date, status, rejection_reason, requested_shift, requested_by FROM wunschfrei_requests WHERE user_id = %s ORDER BY request_date DESC",
            (user_id,)
        )
        # Datum konvertieren
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
        # Datum konvertieren
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
    if not request_ids: return False # Geändert von None zu False
    conn = create_connection()
    if conn is None: return False
    cursor = None
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(request_ids))
        query = f"UPDATE wunschfrei_requests SET notified = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(request_ids))
        conn.commit()
        return True # Erfolg zurückgeben
    except mysql.connector.Error as e:
        print(f"DB Fehler in mark_requests_as_notified: {e}")
        conn.rollback() # Rollback bei Fehler
        return False # Misserfolg zurückgeben
    finally:
        if conn and conn.is_connected():
            if cursor is not None:
                cursor.close()
            conn.close()