# database/db_user_management.py
# NEU: Ausgelagerte Funktionen für die Benutzerverwaltung (Reihenfolge, Admin-Aktionen)

from .db_core import create_connection, _log_activity, _create_admin_notification
from datetime import datetime
import mysql.connector
import calendar

_USER_ORDER_CACHE = None


def clear_user_order_cache():
    """Leert den Cache für die sortierte Liste der Benutzer."""
    global _USER_ORDER_CACHE
    _USER_ORDER_CACHE = None


def get_ordered_users_for_schedule(include_hidden=False, for_date=None):
    """
    Holt die Benutzer in der festgelegten Reihenfolge.
    Gibt standardmäßig nur freigeschaltete (is_approved = 1) UND aktive Benutzer zurück.
    Wenn for_date angegeben ist (Stichtag ist der *Beginn des Monats*),
    werden Benutzer basierend auf ihrem Aktivierungs- und Archivierungsdatum gefiltert.
    """
    global _USER_ORDER_CACHE

    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)

        query = """
                SELECT u.*, uo.sort_order, COALESCE(uo.is_visible, 1) as is_visible
                FROM users u
                         LEFT JOIN user_order uo ON u.id = uo.user_id
                WHERE u.is_approved = 1
                """

        if for_date:
            start_of_month = for_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            days_in_month = calendar.monthrange(for_date.year, for_date.month)[1]
            end_of_month_date = for_date.replace(day=days_in_month, hour=23, minute=59, second=59)

            start_of_month_str = start_of_month.strftime('%Y-%m-%d %H:%M:%S')
            end_of_month_date_str = end_of_month_date.strftime('%Y-%m-%d %H:%M:%S')

            # LOGIK ARCHIVIERUNG:
            query += f" AND (u.is_archived = 0 OR (u.is_archived = 1 AND u.archived_date > '{start_of_month_str}'))"
            # LOGIK AKTIVIERUNG:
            query += f" AND (u.activation_date IS NULL OR u.activation_date <= '{end_of_month_date_str}')"

        else:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # (Archivierung: nicht archiviert ODER Archivierung in Zukunft)
            query += f" AND (u.is_archived = 0 OR (u.is_archived = 1 AND u.archived_date > '{now_str}'))"
            # (Aktivierung: kein Datum ODER Datum in Vergangenheit)
            query += f" AND (u.activation_date IS NULL OR u.activation_date <= '{now_str}')"

        query += " ORDER BY uo.sort_order ASC, u.name ASC"

        cursor.execute(query)
        relevant_users = cursor.fetchall()

        if not for_date:
            _USER_ORDER_CACHE = relevant_users  # Cache enthält jetzt nur aktive

        if include_hidden:
            return relevant_users
        else:
            return [user for user in relevant_users if user.get('is_visible', 1) == 1]

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der sortierten Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_user_order(user_order_list):
    """
    Speichert die Benutzerreihenfolge und Sichtbarkeit als schnelle Batch-Operation.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        # --- INNOVATION: Batch-Verarbeitung ---
        data_to_save = []
        for index, user_info in enumerate(user_order_list):
            user_id = user_info['id']
            is_visible = user_info.get('is_visible', 1)
            data_to_save.append((user_id, index, is_visible))

        query = """
                INSERT INTO user_order (user_id, sort_order, is_visible)
                VALUES (%s, %s, %s) ON DUPLICATE KEY \
                UPDATE \
                    sort_order = \
                VALUES (sort_order), is_visible = \
                VALUES (is_visible)
                """

        if data_to_save:
            cursor.executemany(query, data_to_save)
        # --- ENDE INNOVATION ---

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


# ==============================================================================
# --- FUNKTIONEN FÜR ADMIN-FREISCHALTUNG & ARCHIVIERUNG ---
# ==============================================================================

def get_pending_approval_users():
    """ Holt alle Benutzer, die auf Freischaltung warten. """
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
                       SELECT id, vorname, name, entry_date
                       FROM users
                       WHERE is_approved = 0
                         AND is_archived = 0
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
    """ Schaltet einen Benutzer frei (is_approved = 1). """
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
        clear_user_order_cache()  # Cache leeren, da freigeschaltete User nun relevant sind
        return True, f"Benutzer {user_fullname} erfolgreich freigeschaltet."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Freischalten des Benutzers: {e}")
        return False, f"Fehler beim Freischalten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def archive_user(user_id, current_user_id, archive_date=None):
    """
    Archiviert einen Benutzer (setzt is_archived = 1).
    Wenn archive_date None ist, wird sofort archiviert.
    Wenn archive_date angegeben ist, wird dieses Datum gesetzt.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        if archive_date:
            archive_timestamp = archive_date
            log_msg = f'Benutzer {user_fullname} wird zum {archive_date.strftime("%Y-%m-%d")} archiviert.'
            notification_msg = f'Benutzer {user_fullname} wird zum {archive_date.strftime("%Y-%m-%d")} archiviert.'
        else:
            archive_timestamp = datetime.now()
            log_msg = f'Benutzer {user_fullname} wurde sofort archiviert.'
            notification_msg = f'Benutzer {user_fullname} wurde archiviert.'

        cursor.execute("UPDATE users SET is_archived = 1, archived_date = %s WHERE id = %s",
                       (archive_timestamp, user_id))

        _log_activity(cursor, current_user_id, 'USER_ARCHIVE', log_msg)
        _create_admin_notification(cursor, notification_msg)

        conn.commit()
        clear_user_order_cache()
        return True, notification_msg
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Archivieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def unarchive_user(user_id, current_user_id):
    """
    Reaktiviert einen Benutzer.
    Setzt is_archived = 0, archived_date = NULL.
    Setzt activation_date auf NULL, um sofortigen Login zu ermöglichen (wenn approved).
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        cursor.execute("UPDATE users SET is_archived = 0, archived_date = NULL, activation_date = NULL WHERE id = %s",
                       (user_id,))

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