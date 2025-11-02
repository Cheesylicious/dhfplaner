# database/db_locks.py
from datetime import date, datetime
# --- KORREKTUR: Fehlenden Import hinzugefügt ---
import calendar
# --- ENDE KORREKTUR ---
from .db_core import create_connection, _log_activity
import mysql.connector
# --- KORREKTUR: Import für defaultdict hinzugefügt (wird in get_locked_shifts_for_month verwendet) ---
from collections import defaultdict


# --- ENDE KORREKTUR ---


def set_shift_lock_status(user_id, date_str, shift_abbrev, is_locked, admin_id):
    """
    Setzt den Lock-Status für eine bestimmte Schicht an einem Datum.
    Wenn is_locked=True, wird die Schicht in die Sicherungstabelle eingefügt.
    Wenn is_locked=False, wird der Eintrag gelöscht.
    """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None

    try:
        cursor = conn.cursor()

        user_id_int = int(user_id)

        if is_locked:
            # Einfügen/Aktualisieren der gesicherten Schicht
            query = """
                    INSERT INTO shift_locks (user_id, shift_date, shift_abbrev, secured_by_admin_id)
                    VALUES (%s, %s, %s, %s) ON DUPLICATE KEY \
                    UPDATE \
                        shift_abbrev = \
                    VALUES (shift_abbrev), secured_by_admin_id = \
                    VALUES (secured_by_admin_id) \
                    """
            cursor.execute(query, (user_id_int, date_str, shift_abbrev, admin_id))
            action_type = 'SHIFT_SECURED'
            log_msg = f"Admin {admin_id} sicherte Schicht {shift_abbrev} für User {user_id} am {date_str}."
        else:
            # Entfernen der Sicherung
            query = "DELETE FROM shift_locks WHERE user_id = %s AND shift_date = %s"
            cursor.execute(query, (user_id_int, date_str))
            action_type = 'SHIFT_UNLOCKED'
            log_msg = f"Admin {admin_id} gab Schicht von User {user_id} am {date_str} wieder frei."

        _log_activity(cursor, admin_id, action_type, log_msg)
        conn.commit()

        return True, "Status erfolgreich gespeichert."

    except Exception as e:
        conn.rollback()
        print(f"DB Fehler in set_shift_lock_status: {e}")
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None: cursor.close()
            conn.close()


def get_locked_shifts_for_month(year, month):
    """
    Holt alle gesicherten Schichten für den gegebenen Monat.
    Gibt ein Dictionary zurück: {user_id_str: {date_str: shift_abbrev}}
    """
    conn = create_connection()
    if conn is None: return {}
    cursor = None

    try:
        cursor = conn.cursor(dictionary=True)
        # Berechne Monatsgrenzen
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        # --- HIER WIRD calendar BENÖTIGT ---
        _, last_day = calendar.monthrange(year, month)
        # --- ENDE ---
        end_date = date(year, month, last_day).strftime('%Y-%m-%d')

        query = "SELECT user_id, shift_date, shift_abbrev FROM shift_locks WHERE shift_date BETWEEN %s AND %s"
        cursor.execute(query, (start_date, end_date))

        # --- defaultdict verwenden ---
        locked_shifts = defaultdict(dict)
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            # --- Sicherstellen, dass row['shift_date'] ein date/datetime Objekt ist ---
            db_date = row['shift_date']
            if isinstance(db_date, (date, datetime)):
                date_str = db_date.strftime('%Y-%m-%d')  # Sicherstellen, dass es ein String ist
                locked_shifts[user_id_str][date_str] = row['shift_abbrev']
            else:
                print(f"[WARNUNG] Ungültiger Datumstyp aus DB in get_locked_shifts_for_month: {type(db_date)}")
            # --- ENDE ---

        return dict(locked_shifts)  # Zurück als normales Dict

    except Exception as e:
        print(f"DB Fehler in get_locked_shifts_for_month: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            if cursor is not None: cursor.close()
            conn.close()


# --- NEUE FUNKTION ---
def delete_all_locks_for_month(year, month, admin_id):
    """
    Löscht ALLE Schichtsicherungen (Locks) für einen gesamten Monat.
    """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    cursor = None

    try:
        cursor = conn.cursor()

        # Monatsgrenzen berechnen (performant, keine unnötigen Abfragen)
        start_date = date(year, month, 1).strftime('%Y-%m-%d')
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day).strftime('%Y-%m-%d')

        # SQL-Query zum Löschen aller Einträge im Datumsbereich
        query = "DELETE FROM shift_locks WHERE shift_date BETWEEN %s AND %s"
        cursor.execute(query, (start_date, end_date))

        affected_rows = cursor.rowcount

        log_msg = f"Admin {admin_id} hat {affected_rows} Schichtsicherungen für {month:02d}/{year} global aufgehoben."
        _log_activity(cursor, admin_id, 'ALL_SHIFTS_UNLOCKED', log_msg)

        conn.commit()

        return True, f"{affected_rows} Sicherungen für {month:02d}/{year} erfolgreich aufgehoben."

    except Exception as e:
        if conn: conn.rollback()
        print(f"DB Fehler in delete_all_locks_for_month: {e}")
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            if cursor is not None: cursor.close()
            conn.close()
# --- ENDE NEUE FUNKTION ---