# database/db_admin.py
# BEREINIGTE VERSION: Konzentriert sich auf Admin-Benachrichtigungen
# und die Admin-Erstellung von Benutzern.

from datetime import datetime
# --- ANGEPASSTE IMPORTE ---
from .db_core import create_connection, hash_password, _create_admin_notification, get_vacation_days_for_tenure, \
    _log_activity
# --- ENDE ANPASSUNG ---
import mysql.connector
import warnings  # NEU


# --- ENTFERNT ---
# Die Funktionen lock_month, unlock_month, is_month_locked
# wurden nach 'db_month_locking.py' verschoben.

# --- ENTFERNT ---
# Die Funktionen admin_reset_password, request_password_reset,
# get_pending_password_resets, approve_password_reset,
# reject_password_reset, get_pending_password_resets_count
# wurden nach 'db_password_reset.py' verschoben.


def get_unread_admin_notifications():
    """ Holt alle ungelesenen Admin-Benachrichtigungen. """
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, message FROM admin_notifications WHERE is_read = 0 ORDER BY timestamp ASC")
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def mark_admin_notifications_as_read(notification_ids):
    """ Markiert Admin-Benachrichtigungen als gelesen. """
    if not notification_ids:
        return
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(notification_ids))
        query = f"UPDATE admin_notifications SET is_read = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(notification_ids))
        conn.commit()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def create_user_by_admin(data, admin_id):
    """
    Erstellt einen neuen Benutzer durch einen Admin, setzt is_approved=1 und
    führt die Urlaubsanspruchsberechnung durch.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        # --- URLAUBSBERECHNUNG ---
        entry_date_str = data.get('entry_date')
        default_days = 30
        try:
            default_days = int(data.get('urlaub_gesamt', 30))
        except (ValueError, TypeError):
            default_days = 30

        urlaub_gesamt = get_vacation_days_for_tenure(entry_date_str, default_days)
        # --- ENDE URLAUBSBERECHNUNG ---

        user_fullname = f"{data['vorname']} {data['name']}"

        cursor.execute(
            """INSERT INTO users (vorname, name, password_hash, role, geburtstag, telefon, diensthund,
                                  urlaub_gesamt, urlaub_rest, entry_date, is_approved, is_archived,
                                  password_changed, has_seen_tutorial)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data['vorname'], data['name'], hash_password(data['password']), data['role'],
             data.get('geburtstag', None), data.get('telefon', None), data.get('diensthund', None),
             urlaub_gesamt, urlaub_gesamt, entry_date_str,
             1, 0,  # is_approved=1, is_archived=0 (Benutzer ist freigeschaltet und aktiv)
             data.get('password_changed', 0),
             data.get('has_seen_tutorial', 0))
        )

        user_id = cursor.lastrowid

        _log_activity(cursor, admin_id, 'USER_CREATION',
                      f'Benutzer {user_fullname} (ID: {user_id}) wurde durch Admin {admin_id} erstellt.')
        _create_admin_notification(cursor, f"Neuer Benutzer {user_fullname} wurde durch Admin {admin_id} angelegt.")

        conn.commit()

        # Cache leeren (wird aus db_users importiert, welches es aus db_user_management importiert)
        # Um eine zirkuläre Abhängigkeit zu vermeiden, importieren wir es hier nicht direkt,
        # sondern gehen davon aus, dass der Aufrufer (z.B. User Management Tab) den Cache leert
        # oder wir importieren es aus db_user_management.
        # UPDATE: Wir importieren es am Ende.

        return True, f"Mitarbeiter {user_fullname} erfolgreich hinzugefügt und freigeschaltet."
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, "Ein Mitarbeiter mit diesem Namen existiert bereits."
    except Exception as e:
        conn.rollback()
        print(f"Error in create_user_by_admin: {e}")
        return False, f"Ein unerwarteter Datenbankfehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- RE-IMPORT DER AUSGELAGERTEN FUNKTIONEN (FÜR ABWÄRTSKOMPATIBILITÄT) ---

# 1. Funktionen für Monatssperrung
try:
    from .db_month_locking import (
        lock_month,
        unlock_month,
        is_month_locked
    )
except ImportError as e:
    warnings.warn(f"Konnte db_month_locking nicht importieren: {e}")

# 2. Funktionen für Passwort-Reset (DIES BEHEBT DEN 'token' FEHLER)
try:
    from .db_password_reset import (
        admin_reset_password,
        request_password_reset,
        get_pending_password_resets,
        approve_password_reset,
        reject_password_reset,
        get_pending_password_resets_count
    )
except ImportError as e:
    warnings.warn(f"Konnte db_password_reset nicht importieren: {e}")

# 3. Import der Cache-Clear-Funktion (benötigt von create_user_by_admin)
try:
    from .db_user_management import clear_user_order_cache
except ImportError as e:
    warnings.warn(f"Konnte clear_user_order_cache (benötigt von db_admin) nicht importieren: {e}")


    # Dummy-Funktion, damit create_user_by_admin nicht abstürzt
    def clear_user_order_cache():
        pass

# --- ENDE RE-IMPORT ---