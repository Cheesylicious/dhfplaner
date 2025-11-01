# database/db_month_locking.py
# NEU: Ausgelagerte Funktionen für die Sperrung von Monaten

from .db_core import create_connection
import mysql.connector


def lock_month(year, month):
    """ Sperrt einen Monat für die Bearbeitung. """
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        # Annahme: 'locked_months' Tabelle existiert
        cursor.execute("INSERT IGNORE INTO locked_months (year, month) VALUES (%s, %s)", (year, month))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        if e.errno == 1146:
            print("FEHLER: Tabelle 'locked_months' existiert nicht.")
        else:
            print(f"DB Error on lock_month: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def unlock_month(year, month):
    """ Entsperrt einen Monat für die Bearbeitung. """
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        # Annahme: 'locked_months' Tabelle existiert
        cursor.execute("DELETE FROM locked_months WHERE year = %s AND month = %s", (year, month))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        if e.errno == 1146:
            print("FEHLER: Tabelle 'locked_months' existiert nicht.")
        else:
            print(f"DB Error on unlock_month: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def is_month_locked(year, month):
    """ Prüft, ob ein Monat gesperrt ist. """
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        # Annahme: 'locked_months' Tabelle existiert
        cursor.execute("SELECT 1 FROM locked_months WHERE year = %s AND month = %s", (year, month))
        return cursor.fetchone() is not None
    except mysql.connector.Error as e:
        if e.errno == 1146:
            print("FEHLER: Tabelle 'locked_months' existiert nicht.")
            return False
        print(f"DB Error on is_month_locked: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()