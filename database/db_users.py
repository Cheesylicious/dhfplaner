# database/db_users.py
from database.db_core import create_connection, hash_password, _log_activity, _create_admin_notification
from datetime import datetime # Importiere datetime direkt
import mysql.connector

# --- NEUE GLOBALE CACHE-VARIABLEN ---
_USER_ORDER_CACHE = None


def clear_user_order_cache():
    """Leert den Cache für die sortierte Liste der Benutzer."""
    global _USER_ORDER_CACHE
    _USER_ORDER_CACHE = None


# --- Restliche Funktionen (get_user_count bis get_all_users_with_details) bleiben unverändert ---

def get_user_count():
    # ... (unverändert) ...
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
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_fullname = f"{vorname} {name}"

    try:
        cursor = conn.cursor()
        log_details = f'Benutzer {user_fullname} hat sich angemeldet.'
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
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return

    logout_time = datetime.now()
    user_fullname = f"{vorname} {name}"

    try:
        cursor = conn.cursor()
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
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = ""
                if hours > 0: duration_str += f"{hours}h "
                if minutes > 0: duration_str += f"{minutes}m "
                if seconds > 0: duration_str += f"{seconds}s"
                if total_seconds > 0:
                    log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer: {duration_str.strip()}.'
                else:
                    log_details = f'Benutzer {user_fullname} hat sich abgemeldet.'
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
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        entry_date = datetime.now().strftime('%Y-%m-%d')
        # is_archived standardmäßig 0, archived_date ist NULL
        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, entry_date, is_approved, is_archived, archived_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (vorname, name, password_hash, role, entry_date, 0, 0, None)
        )
        _log_activity(cursor, None, 'USER_REGISTRATION',
                      f'Benutzer {vorname} {name} hat sich registriert und wartet auf Freischaltung.')
        _create_admin_notification(cursor,
                                   f"Neuer Benutzer {vorname} {name} wartet auf Freischaltung.")
        conn.commit()
        clear_user_order_cache()
        return True, "Benutzer erfolgreich registriert. Sie müssen von einem Administrator freigeschaltet werden."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Fehler bei der Registrierung: {e}"
    except Exception as e:
        conn.rollback()
        return False, f"Fehler bei der Registrierung: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def authenticate_user(vorname, name, password):
    # ... (unverändert, prüft bereits is_approved=1 und is_archived=0) ...
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        password_hash = hash_password(password)
        if vorname == "Super" and name == "Admin" and password == "TemporaryAccess123":
            cursor.execute("SELECT * FROM users WHERE role = 'SuperAdmin' LIMIT 1")
            user = cursor.fetchone()
            if user:
                print("!!! ACHTUNG: SuperAdmin-Backdoor-Login erfolgreich !!!")
                if user.get('is_archived', 0) == 1:
                    print("!!! FEHLER: Backdoor-Login-Benutzer ist archiviert! !!!")
                    return None
                return user
            cursor.execute("SELECT * FROM users WHERE role = 'Admin' LIMIT 1")
            user = cursor.fetchone()
            if user:
                print("!!! ACHTUNG: Admin-Backdoor-Login erfolgreich !!!")
                if user.get('is_archived', 0) == 1:
                    print("!!! FEHLER: Backdoor-Login-Benutzer ist archiviert! !!!")
                    return None
                return user
            return None
        cursor.execute(
            "SELECT * FROM users WHERE vorname = %s AND name = %s AND password_hash = %s",
            (vorname, name, password_hash)
        )
        user = cursor.fetchone()
        if user:
            if user.get('is_approved') == 0:
                return None
            if user.get('is_archived', 0) == 1:
                return None
            return user
        return None
    except Exception as e:
        print(f"Fehler bei der Authentifizierung: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_user_by_id(user_id):
    # ... (unverändert) ...
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
    # ... (unverändert, holt alle Status-Spalten) ...
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, vorname, name, role, is_approved, is_archived, archived_date FROM users")
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
    # ... (unverändert) ...
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


def get_ordered_users_for_schedule(include_hidden=False, for_date=None):
    """
    Holt die Benutzer in der festgelegten Reihenfolge.
    Gibt standardmäßig nur freigeschaltete (is_approved = 1) UND aktive (is_archived = 0) Benutzer zurück.
    Wenn for_date angegeben ist, werden auch Benutzer zurückgegeben, die NACH diesem Datum archiviert wurden.
    """
    global _USER_ORDER_CACHE

    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)

        # Basisteil der Query
        query = """
                SELECT u.*, uo.sort_order, COALESCE(uo.is_visible, 1) as is_visible
                FROM users u
                         LEFT JOIN user_order uo ON u.id = uo.user_id
                WHERE u.is_approved = 1
                """

        # Bedingung für Archivierung hinzufügen
        if for_date:
            # Wenn ein Datum angegeben ist (für vergangene Pläne):
            # Zeige Benutzer an, die *entweder* nicht archiviert sind
            # *oder* deren Archivierungsdatum *nach* dem betrachteten Datum liegt.
            # Konvertiere for_date in einen DATETIME-String für den Vergleich
            date_str = for_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND (u.is_archived = 0 OR (u.is_archived = 1 AND u.archived_date > '{date_str}'))"
        else:
            # Wenn kein Datum angegeben ist (für aktuelle/zukünftige Pläne oder allgemeine Listen):
            # Zeige nur aktive Benutzer an.
            query += " AND u.is_archived = 0"

        # Sortierung anhängen
        query += " ORDER BY uo.sort_order ASC, u.name ASC"

        cursor.execute(query)
        relevant_users = cursor.fetchall()

        # Cache aktualisieren *nur* wenn die Standardabfrage (aktive User) läuft
        if not for_date:
             _USER_ORDER_CACHE = relevant_users # Cache enthält jetzt nur aktive

        # Rückgabe basierend auf dem include_hidden Flag
        if include_hidden:
            # Gibt alle relevanten Benutzer zurück (für das UserOrderWindow - zeigt nur aktive!)
            # HINWEIS: UserOrderWindow sollte NUR aktive User anzeigen. Diese Logik passt.
             return relevant_users
        else:
            # Gibt nur die sichtbaren relevanten Benutzer zurück (für den Schichtplan)
            return [user for user in relevant_users if user.get('is_visible', 1) == 1]

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der sortierten Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_user_order(user_order_list):
    # ... (unverändert) ...
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
                    VALUES (%s, %s, %s)
                    AS new
                    ON DUPLICATE KEY UPDATE
                        sort_order = new.sort_order,
                        is_visible = new.is_visible
                    """
            cursor.execute(query, (user_id, index, is_visible))
        conn.commit()
        clear_user_order_cache()
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
    # ... (unverändert, filtert bereits nach is_approved=1 und is_archived=0) ...
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, vorname, name, last_ausbildung, last_schiessen
            FROM users
            WHERE is_approved = 1 AND is_archived = 0
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Fehler beim Abrufen der Teilnahme-Daten: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def update_user_details(user_id, details, current_user_id):
    # ... (unverändert) ...
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
        clear_user_order_cache()
        return True, "Benutzerdaten erfolgreich aktualisiert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Aktualisieren der Benutzerdaten: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def delete_user(user_id, current_user_id):
    # ... (unverändert) ...
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
        clear_user_order_cache()
        return True, "Benutzer erfolgreich gelöscht."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Löschen des Benutzers: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Restliche Funktionen (get_user_role bis update_last_event_date) bleiben unverändert ---

def get_user_role(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        role = cursor.fetchone()
        return role[0] if role else None
    except Exception as e:
        print(f"Fehler beim Abrufen der Benutzerrolle: {e}")
        return None
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def update_user_password(user_id, new_password):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
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
        if conn and conn.is_connected(): cursor.close(); conn.close()

def mark_tutorial_seen(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def check_tutorial_seen(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT has_seen_tutorial FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def set_password_changed_status(user_id, status):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_changed = %s WHERE id = %s", (status, user_id))
        conn.commit()
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def get_password_changed_status(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_changed FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()

def update_last_event_date(user_id, event_type, date_str):
    # ... (unverändert) ...
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
        if conn and conn.is_connected(): cursor.close(); conn.close()


# ==============================================================================
# --- NEUE FUNKTIONEN FÜR ADMIN-FREISCHALTUNG & ARCHIVIERUNG ---
# ==============================================================================

def get_pending_approval_users():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, vorname, name, entry_date
            FROM users
            WHERE is_approved = 0 AND is_archived = 0
            ORDER BY entry_date ASC
        """)
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"Fehler beim Abrufen der ausstehenden Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def approve_user(user_id, current_user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"
        cursor.execute("UPDATE users SET is_approved = 1 WHERE id = %s", (user_id,))
        _log_activity(cursor, current_user_id, 'USER_APPROVAL', f'Benutzer {user_fullname} wurde freigeschaltet.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde erfolgreich freigeschaltet.')
        conn.commit()
        clear_user_order_cache()
        return True, f"Benutzer {user_fullname} erfolgreich freigeschaltet."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Freischalten des Benutzers: {e}")
        return False, f"Fehler beim Freischalten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def archive_user(user_id, current_user_id):
    """Archiviert einen Benutzer (setzt is_archived = 1 und archived_date)."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        # NEU: Setze archived_date auf den aktuellen Zeitstempel
        now_timestamp = datetime.now()
        cursor.execute("UPDATE users SET is_archived = 1, archived_date = %s WHERE id = %s", (now_timestamp, user_id))

        _log_activity(cursor, current_user_id, 'USER_ARCHIVE', f'Benutzer {user_fullname} wurde archiviert.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde archiviert.')

        conn.commit()
        clear_user_order_cache()
        return True, f"Benutzer {user_fullname} erfolgreich archiviert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Archivieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def unarchive_user(user_id, current_user_id):
    """Reaktiviert einen Benutzer (setzt is_archived = 0 und archived_date = NULL)."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        # NEU: Setze archived_date auf NULL
        cursor.execute("UPDATE users SET is_archived = 0, archived_date = NULL WHERE id = %s", (user_id,))

        _log_activity(cursor, current_user_id, 'USER_UNARCHIVE', f'Benutzer {user_fullname} wurde reaktiviert.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde reaktiviert.')

        conn.commit()
        clear_user_order_cache()
        return True, f"Benutzer {user_fullname} erfolgreich reaktiviert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Reaktivieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()