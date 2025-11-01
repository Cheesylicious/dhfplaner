# database/db_password_reset.py
# NEU: Ausgelagerte Funktionen für Admin-Passwort-Reset und Benutzer-Anfragen

from datetime import datetime
from .db_core import create_connection, hash_password, _create_admin_notification, _log_activity
import mysql.connector


def admin_reset_password(user_id, new_password, admin_id):
    """ Setzt das Passwort eines Benutzers durch einen Admin zurück. """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        cursor.execute(
            "UPDATE users SET password_hash = %s, password_changed = 0 WHERE id = %s",
            (hash_password(new_password), user_id)
        )

        _log_activity(cursor, admin_id, 'USER_PASSWORD_RESET',
                      f'Passwort von Benutzer {user_fullname} (ID: {user_id}) wurde durch Admin {admin_id} zurückgesetzt.')

        conn.commit()
        return True, f"Passwort für {user_fullname} wurde zurückgesetzt. Der Benutzer muss es beim nächsten Login ändern."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def request_password_reset(vorname, name):
    """ Verarbeitet die Anfrage eines Benutzers auf Passwort-Reset (z.B. vom Login-Fenster). """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None  # Cursor im finally-Block verfügbar machen
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE lower(vorname) = %s AND lower(name) = %s",
                       (vorname.lower(), name.lower()))
        user = cursor.fetchone()
        if user:
            user_id = user['id']
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # --- KORREKTUR (FIX FÜR 1054 Unknown column 'token') ---
            # Die Spalte 'token' wurde aus der Abfrage entfernt.
            query = """
                    INSERT INTO password_reset_requests (user_id, timestamp)
                    VALUES (%s, %s) ON DUPLICATE KEY \
                    UPDATE timestamp= \
                    VALUES (timestamp) \
                    """
            params = (user_id, timestamp)
            # --- ENDE KORREKTUR ---

            cursor.execute(query, params)

            _create_admin_notification(cursor, f"Benutzer {vorname} {name} hat ein Passwort-Reset angefordert.")
            conn.commit()
            return True, "Ihre Anfrage wurde an einen Administrator gesendet."
        else:
            return False, "Benutzer nicht gefunden."
    except mysql.connector.Error as e:
        if conn and e.errno == 1062:  # Duplicate entry for user_id (UNIQUE constraint)
            try:
                # Trotz "Duplicate" (was OK ist), versuchen wir, die Benachrichtigung zu senden.
                _create_admin_notification(cursor,
                                           f"Benutzer {vorname} {name} hat ERNEUT ein Passwort-Reset angefordert.")
                conn.commit()
            except Exception as e_notify:
                print(f"Fehler bei Benachrichtigung über doppelten Reset: {e_notify}")
                if conn: conn.rollback()
            return True, "Eine Anfrage für diesen Benutzer existiert bereits und wurde erneut an einen Admin gemeldet."

        print(f"DB Error on request_password_reset: {e}")
        if conn: conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor:
                cursor.close()
            conn.close()


def get_pending_password_resets():
    """ Holt alle ausstehenden Passwort-Reset-Anfragen. """
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
                       SELECT pr.id, u.vorname, u.name, pr.timestamp, u.id as user_id
                       FROM password_reset_requests pr
                                JOIN users u ON pr.user_id = u.id
                       ORDER BY pr.timestamp ASC
                       """)
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def approve_password_reset(request_id, new_password):
    """ Genehmigt eine Passwort-Reset-Anfrage (Admin-Aktion). """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id FROM password_reset_requests WHERE id = %s", (request_id,))
        result = cursor.fetchone()
        if result:
            user_id = result['user_id']
            cursor.execute(
                "UPDATE users SET password_hash = %s, password_changed = 0 WHERE id = %s",
                (hash_password(new_password), user_id)
            )
            cursor.execute("DELETE FROM password_reset_requests WHERE id = %s", (request_id,))
            conn.commit()
            return True, f"Passwort für Benutzer ID {user_id} wurde zurückgesetzt."
        return False, "Anfrage nicht gefunden."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def reject_password_reset(request_id):
    """ Lehnt eine Passwort-Reset-Anfrage ab (Admin-Aktion). """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM password_reset_requests WHERE id = %s", (request_id,))
        conn.commit()
        return True, "Anfrage abgelehnt und entfernt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_pending_password_resets_count():
    """ Zählt die ausstehenden Passwort-Reset-Anfragen. """
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM password_reset_requests")
        return cursor.fetchone()[0]
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der Passwort-Resets: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()