# database/db_meta_manager.py
import mysql.connector
from collections import defaultdict
# KORREKTUR: Import von der neuen Verbindungsdatei
from .db_connection import create_connection

# ==============================================================================
# --- FREQUENZ-FUNKTIONEN ---
# ==============================================================================

def save_shift_frequency(frequency_dict):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_frequency")
        if frequency_dict:
            query = "INSERT INTO shift_frequency (shift_abbrev, count) VALUES (%s, %s)"
            data_to_insert = list(frequency_dict.items())
            cursor.executemany(query, data_to_insert)
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on save_shift_frequency: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def load_shift_frequency():
    conn = create_connection()
    if conn is None: return defaultdict(int)
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT shift_abbrev, count FROM shift_frequency")
        results = cursor.fetchall()
        return defaultdict(int, {row['shift_abbrev']: row['count'] for row in results})
    except mysql.connector.Error as e:
        print(f"DB Error on load_shift_frequency: {e}")
        return defaultdict(int)
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def reset_shift_frequency():
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_frequency")
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on reset_shift_frequency: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


# ==============================================================================
# --- SPECIAL APPOINTMENTS FUNKTIONEN ---
# ==============================================================================

def save_special_appointment(date_str, appointment_type, description=""):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = "INSERT INTO special_appointments (appointment_date, appointment_type, description) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE appointment_type=VALUES(appointment_type), description=VALUES(description)"
        cursor.execute(query, (date_str, appointment_type, description))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        # Fehler 1146 (Tabelle existiert nicht) sollte durch db_schema behoben sein
        print(f"DB Error on save_special_appointment: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def delete_special_appointment(date_str, appointment_type):
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        query = "DELETE FROM special_appointments WHERE appointment_date = %s AND appointment_type = %s"
        cursor.execute(query, (date_str, appointment_type))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Error on delete_special_appointment: {e}")
        conn.rollback();
        return False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_special_appointments():
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM special_appointments")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"DB Error on get_special_appointments: {e}");
        return []
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()