# database/db_shifts.py
import sqlite3
import calendar
import json
from datetime import date, datetime
from .db_core import create_connection

def save_shift_entry(user_id, shift_date_str, shift_abbrev, keep_request_record=False):
    """Saves a shift entry."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        if shift_abbrev in ["", "FREI"]:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = ? AND shift_date = ?",
                           (user_id, shift_date_str))
        else:
            cursor.execute("""
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, shift_date) DO UPDATE SET shift_abbrev = ?
            """, (user_id, shift_date_str, shift_abbrev, shift_abbrev))

        if shift_abbrev and shift_abbrev not in ["", "FREI"]:
            try:
                with open('events_config.json', 'r', encoding='utf-8') as f:
                    all_events = json.load(f)

                date_obj = datetime.strptime(shift_date_str, '%Y-%m-%d').date()
                year_str = str(date_obj.year)

                if year_str in all_events and shift_date_str in all_events[year_str]:
                    event_type = all_events[year_str][shift_date_str]

                    if event_type == "Quartals Ausbildung":
                        cursor.execute("UPDATE users SET last_ausbildung = ? WHERE id = ?", (shift_date_str, user_id))
                    elif event_type == "Schießen":
                        cursor.execute("UPDATE users SET last_schiessen = ? WHERE id = ?", (shift_date_str, user_id))
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                pass

        if not keep_request_record:
            if shift_abbrev != 'X':
                cursor.execute("DELETE FROM wunschfrei_requests WHERE user_id = ? AND request_date = ?",
                               (user_id, shift_date_str))

        conn.commit()
        return True, "Schicht gespeichert."

    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schicht: {e}"
    finally:
        conn.close()


def get_shifts_for_month(year, month):
    """Fetches all shifts for a given month."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT user_id, shift_date, shift_abbrev
            FROM shift_schedule
            WHERE shift_date BETWEEN ? AND ?
        """, (start_date, end_date))

        shifts = {}
        for row in cursor.fetchall():
            user_id = str(row['user_id'])
            if user_id not in shifts:
                shifts[user_id] = {}
            shifts[user_id][row['shift_date']] = row['shift_abbrev']

        return shifts

    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen des Schichtplans: {e}")
        return {}
    finally:
        conn.close()


def get_daily_shift_counts_for_month(year, month):
    """Fetches the daily shift counts for a given month."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                ss.shift_date,
                ss.shift_abbrev,
                COUNT(ss.shift_abbrev) as count
            FROM shift_schedule ss
            LEFT JOIN user_order uo ON ss.user_id = uo.user_id
            WHERE ss.shift_date BETWEEN ? AND ? AND COALESCE(uo.is_visible, 1) = 1
            GROUP BY ss.shift_date, ss.shift_abbrev
        """, (start_date, end_date))

        daily_counts = {}
        for row in cursor.fetchall():
            shift_date = row['shift_date']
            if shift_date not in daily_counts:
                daily_counts[shift_date] = {}
            daily_counts[shift_date][row['shift_abbrev']] = row['count']

        return daily_counts

    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}")
        return {}
    finally:
        conn.close()


def get_all_shift_types():
    """Fetches all shift types."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, abbreviation, hours, description, color, start_time, end_time FROM shift_types ORDER BY abbreviation")
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der Schichtarten: {e}")
        return []
    finally:
        conn.close()


def add_shift_type(data):
    """Adds a new shift type."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO shift_types
               (name, abbreviation, hours, description, color, start_time, end_time)
               VALUES (:name, :abbreviation, :hours, :description, :color, :start_time, :end_time)""",
            data)
        conn.commit()
        return True, "Schichtart erfolgreich hinzugefügt."
    except sqlite3.IntegrityError:
        return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def update_shift_type(shift_type_id, data):
    """Updates a shift type."""
    data['id'] = shift_type_id
    conn = create_connection()
    try:
        cursor = conn.cursor()
        sql = """ UPDATE shift_types
                  SET name = :name,
                      abbreviation = :abbreviation,
                      hours = :hours,
                      description = :description,
                      color = :color,
                      start_time = :start_time,
                      end_time = :end_time
                  WHERE id = :id """

        data['id'] = shift_type_id

        cursor.execute(sql, data)
        conn.commit()
        return True, "Schichtart erfolgreich aktualisiert."
    except sqlite3.IntegrityError:
        return False, "Die neue Abkürzung wird bereits von einer anderen Schichtart verwendet."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def delete_shift_type(shift_type_id):
    """Deletes a shift type."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT abbreviation FROM shift_types WHERE id = ?", (shift_type_id,))
        abbrev = cursor.fetchone()
        cursor.execute("DELETE FROM shift_types WHERE id = ?", (shift_type_id,))
        if abbrev:
            cursor.execute("DELETE FROM shift_order WHERE abbreviation = ?", (abbrev['abbreviation'],))
        conn.commit()
        return True, "Schichtart erfolgreich gelöscht."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_ordered_shift_abbrevs(include_hidden=False):
    """Fetches ordered shift abbreviations."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shift_types")
        shift_types_data = {st['abbreviation']: dict(st) for st in cursor.fetchall()}
        cursor.execute("SELECT abbreviation, sort_order, is_visible, check_for_understaffing FROM shift_order")
        order_map = {row['abbreviation']: dict(row) for row in cursor.fetchall()}
        ordered_list = []
        all_relevant_abbrevs = set(shift_types_data.keys()) | {'T.', '6', 'N.', '24'}
        for abbrev in sorted(list(all_relevant_abbrevs)):
            if abbrev in shift_types_data:
                item = shift_types_data[abbrev]
            else:
                item = {'abbreviation': abbrev,
                        'name': f"({abbrev} - Regel)" if abbrev not in ['T.', '6', 'N.', '24'] else abbrev, 'hours': 0,
                        'description': f"Harte Regel für {abbrev}.", 'color': '#FFFFFF'}
            order_data = order_map.get(abbrev, {'sort_order': 999999, 'is_visible': 1, 'check_for_understaffing': 0})
            item['sort_order'] = order_data['sort_order']
            item['is_visible'] = order_data['is_visible']
            item['check_for_understaffing'] = order_data['check_for_understaffing']
            if include_hidden or item['is_visible'] == 1:
                ordered_list.append(item)
        ordered_list.sort(key=lambda x: x['sort_order'])
        return ordered_list
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der Schichtreihenfolge: {e}")
        return [dict(st, sort_order=999999, is_visible=1, check_for_understaffing=0) for st in get_all_shift_types()]


def save_shift_order(order_data_list):
    """Saves the shift order."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM shift_order")
        cursor.executemany(
            "INSERT INTO shift_order (abbreviation, sort_order, is_visible, check_for_understaffing) VALUES (?, ?, ?, ?)",
            order_data_list)
        conn.commit()
        return True, "Schichtreihenfolge erfolgreich gespeichert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schichtreihenfolge: {e}"
    finally:
        conn.close()