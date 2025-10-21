# database/db_users.py
from database.db_core import create_connection, hash_password, _log_activity, _create_admin_notification
from datetime import datetime
import mysql.connector


def get_user_count():
    """Gibt die Anzahl der registrierten Benutzer zurück."""
    conn = create_connection()
    if conn is None:
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        print(f"Fehler beim Zählen der Benutzer: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def log_user_login(user_id, vorname, name):
    """Protokolliert das Benutzer-Login."""
    conn = create_connection()
    if conn is None: return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_fullname = f"{vorname} {name}"

    try:
        cursor = conn.cursor()

        # Log-Eintrag für Login erstellen
        log_details = f'Benutzer {user_fullname} hat sich angemeldet.'
        # USER_LOGIN ist der Schlüssel für die spätere Berechnung des Logouts
        _log_activity(cursor, user_id, 'USER_LOGIN', log_details)

        conn.commit()
    except Exception as e:
        print(f"Fehler beim Protokollieren des Logins: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def log_user_logout(user_id, vorname, name):
    """Protokolliert das Benutzer-Logout und berechnet die Sitzungsdauer basierend auf dem letzten Login-Eintrag."""
    conn = create_connection()
    if conn is None: return

    logout_time = datetime.now()
    user_fullname = f"{vorname} {name}"

    try:
        cursor = conn.cursor()

        # Hole den letzten erfolgreichen Login-Eintrag vom selben Benutzer (absteigend nach ID)
        cursor.execute("""
                       SELECT timestamp
                       FROM activity_log
                       WHERE user_id = %s AND action_type = 'USER_LOGIN'
                       ORDER BY id DESC LIMIT 1
                       """, (user_id,))

        result = cursor.fetchone()

        if result:
            login_time_str = result[0]
            try:
                login_time = datetime.strptime(login_time_str, '%Y-%m-%d %H:%M:%S')
                duration = logout_time - login_time

                # Formatierung der Dauer (z.B. 1h 5m 30s)
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                duration_str = ""
                if hours > 0: duration_str += f"{hours}h "
                if minutes > 0: duration_str += f"{minutes}m "
                duration_str += f"{seconds}s"

                # Die Dauer wird explizit in das Detailfeld geschrieben, um später extrahiert zu werden.
                log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer: {duration_str.strip()}.'
            except ValueError:
                log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer konnte nicht berechnet werden (Login-Zeitpunkt Fehler).'
        else:
            log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer konnte nicht berechnet werden (kein Login-Eintrag gefunden).'

        _log_activity(cursor, user_id, 'USER_LOGOUT', log_details)

        conn.commit()
    except Exception as e:
        print(f"Fehler beim Protokollieren des Logouts: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def register_user(vorname, name, password, role="Benutzer"):
    """Registriert einen neuen Benutzer."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        entry_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, entry_date) VALUES (%s, %s, %s, %s, %s)",
            (vorname, name, password_hash, role, entry_date)
        )
        _log_activity(cursor, None, 'USER_REGISTRATION', f'Benutzer {vorname} {name} hat sich registriert.')
        conn.commit()
        return True, "Benutzer erfolgreich registriert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler bei der Registrierung: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def authenticate_user(vorname, name, password):
    """Authentifiziert einen Benutzer und gibt dessen Daten zurück."""
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        password_hash = hash_password(password)
        cursor.execute(
            "SELECT * FROM users WHERE vorname = %s AND name = %s AND password_hash = %s",
            (vorname, name, password_hash)
        )
        user = cursor.fetchone()
        return user
    except Exception as e:
        print(f"Fehler bei der Authentifizierung: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_user_by_id(user_id):
    """Holt einen Benutzer anhand seiner ID."""
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        return user
    except Exception as e:
        print(f"Fehler beim Abrufen des Benutzers (ID: {user_id}): {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_users():
    """Holt alle Benutzer aus der Datenbank."""
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, vorname, name, role FROM users")
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"Fehler beim Abrufen aller Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_users_with_details():
    """Holt alle Benutzer mit allen Details aus der Datenbank."""
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"Fehler beim Abrufen der Benutzerdetails: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_ordered_users_for_schedule(include_hidden=False):
    """Holt die Benutzer in der festgelegten Reihenfolge."""
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)

        query = """
                SELECT u.*, COALESCE(uo.is_visible, 1) as is_visible
                FROM users u
                         LEFT JOIN user_order uo ON u.id = uo.user_id \
                """
        if not include_hidden:
            query += " WHERE COALESCE(uo.is_visible, 1) = 1"

        query += " ORDER BY uo.sort_order ASC, u.id ASC"

        cursor.execute(query)
        users = cursor.fetchall()
        return users
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der sortierten Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_user_order(user_order_list):
    """Speichert die neue Reihenfolge und Sichtbarkeit der Benutzer."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        for index, user_info in enumerate(user_order_list):
            user_id = user_info['id']
            is_visible = user_info.get('is_visible', 1)
            query = """
                    INSERT INTO user_order (user_id, sort_order, is_visible)
                    VALUES (%s, %s, %s) ON DUPLICATE KEY \
                    UPDATE sort_order = \
                    VALUES (sort_order), is_visible = \
                    VALUES (is_visible) \
                    """
            cursor.execute(query, (user_id, index, is_visible))
        conn.commit()
        return True, "Reihenfolge erfolgreich gespeichert."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Speichern der Benutzerreihenfolge: {e}")
        return False, f"Fehler beim Speichern: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_user_participation():
    """Holt die Teilnahme-Daten für alle Benutzer."""
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, vorname, name, last_ausbildung, last_schiessen FROM users")
        return cursor.fetchall()
    except Exception as e:
        print(f"Fehler beim Abrufen der Teilnahme-Daten: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_user_details(user_id, details, current_user_id):
    """Aktualisiert die Daten eines Benutzers."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        valid_details = {k: v for k, v in details.items() if k != 'password'}
        fields = ', '.join([f"`{key}` = %s" for key in valid_details])
        values = list(valid_details.values()) + [user_id]

        query = f"UPDATE users SET {fields} WHERE id = %s"
        cursor.execute(query, tuple(values))

        _log_activity(cursor, current_user_id, 'USER_UPDATE', f'Daten für Benutzer-ID {user_id} aktualisiert.')
        conn.commit()
        return True, "Benutzerdaten erfolgreich aktualisiert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Aktualisieren der Benutzerdaten: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_user(user_id, current_user_id):
    """Löscht einen Benutzer aus der Datenbank."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data['vorname']} {user_data['name']}" if user_data else f"ID {user_id}"

        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        _log_activity(cursor, current_user_id, 'USER_DELETION', f'Benutzer {user_fullname} (ID: {user_id}) gelöscht.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde gelöscht.')
        conn.commit()
        return True, "Benutzer erfolgreich gelöscht."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Löschen des Benutzers: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_user_role(user_id):
    """Gibt die Rolle eines Benutzers zurück."""
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        role = cursor.fetchone()
        return role[0] if role else None
    except Exception as e:
        print(f"Fehler beim Abrufen der Benutzerrolle: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_user_password(user_id, new_password):
    """Aktualisiert das Passwort eines Benutzers."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        new_password_hash = hash_password(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s, password_changed = 1 WHERE id = %s",
            (new_password_hash, user_id)
        )
        _log_activity(cursor, user_id, 'PASSWORD_UPDATE', f'Benutzer-ID {user_id} hat das Passwort geändert.')
        conn.commit()
        return True, "Passwort erfolgreich aktualisiert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Aktualisieren des Passworts: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def mark_tutorial_seen(user_id):
    """Markiert, dass der Benutzer das Tutorial gesehen hat."""
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def check_tutorial_seen(user_id):
    """Überprüft, ob der Benutzer das Tutorial gesehen hat."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT has_seen_tutorial FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def set_password_changed_status(user_id, status):
    """Setzt den Status, ob das Passwort geändert wurde (0 oder 1)."""
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_changed = %s WHERE id = %s", (status, user_id))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_password_changed_status(user_id):
    """Überprüft, ob der Benutzer sein initiales Passwort geändert hat."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_changed FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_last_event_date(user_id, event_type, date_str):
    """Aktualisiert das Datum des letzten Ereignisses (z.B. Schießen, Ausbildung)."""
    conn = create_connection()
    if conn is None: return

    allowed_columns = {"ausbildung": "last_ausbildung", "schiessen": "last_schiessen"}
    if event_type not in allowed_columns:
        print(f"Ungültiger Ereignistyp: {event_type}")
        return

    column_name = allowed_columns[event_type]

    try:
        cursor = conn.cursor()
        query = f"UPDATE users SET {column_name} = %s WHERE id = %s"
        cursor.execute(query, (date_str, user_id))
        conn.commit()
    except Exception as e:
        print(f"Fehler beim Aktualisieren des Ereignisdatums: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()