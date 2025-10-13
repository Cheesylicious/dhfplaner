import calendar
import json
from datetime import date, datetime
from .db_core import create_connection
import mysql.connector


def save_shift_entry(user_id, shift_date_str, shift_abbrev, keep_request_record=False):
    """Speichert einen Schichteintrag in der MySQL-Datenbank."""
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        if shift_abbrev in ["", "FREI"]:
            # Lösche den Eintrag, wenn die Schicht auf "FREI" gesetzt wird
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s",
                           (user_id, shift_date_str))
        else:
            # Füge einen neuen Eintrag hinzu oder aktualisiere den bestehenden
            query = """
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE shift_abbrev = VALUES(shift_abbrev)
            """
            cursor.execute(query, (user_id, shift_date_str, shift_abbrev))

        # Prüfe, ob es sich um ein Event-Datum handelt (Ausbildung/Schießen)
        if shift_abbrev and shift_abbrev not in ["", "FREI"]:
            try:
                with open('events_config.json', 'r', encoding='utf-8') as f:
                    all_events = json.load(f)

                date_obj = datetime.strptime(shift_date_str, '%Y-%m-%d').date()
                year_str = str(date_obj.year)

                if year_str in all_events and shift_date_str in all_events[year_str]:
                    event_type = all_events[year_str][shift_date_str]
                    if event_type == "Quartals Ausbildung":
                        cursor.execute("UPDATE users SET last_ausbildung = %s WHERE id = %s", (shift_date_str, user_id))
                    elif event_type == "Schießen":
                        cursor.execute("UPDATE users SET last_schiessen = %s WHERE id = %s", (shift_date_str, user_id))
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                pass  # Fehler ignorieren, wenn die Event-Datei nicht existiert

        if not keep_request_record and shift_abbrev != 'X':
            # Lösche offene Wunschfrei-Anfragen für diesen Tag
            cursor.execute("DELETE FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s",
                           (user_id, shift_date_str))

        conn.commit()
        return True, "Schicht gespeichert."

    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schicht: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_shifts_for_month(year, month):
    """Holt alle Schichten für einen gegebenen Monat."""
    conn = create_connection()
    if conn is None: return {}
    try:
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT user_id, shift_date, shift_abbrev
            FROM shift_schedule
            WHERE shift_date BETWEEN %s AND %s
        """, (start_date, end_date))

        shifts = {}
        for row in cursor.fetchall():
            user_id = str(row['user_id'])
            if user_id not in shifts:
                shifts[user_id] = {}
            shifts[user_id][row['shift_date']] = row['shift_abbrev']
        return shifts

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen des Schichtplans: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_daily_shift_counts_for_month(year, month):
    """Holt die tägliche Anzahl der Schichten für einen gegebenen Monat."""
    conn = create_connection()
    if conn is None: return {}
    try:
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                ss.shift_date,
                ss.shift_abbrev,
                COUNT(ss.shift_abbrev) as count
            FROM shift_schedule ss
            LEFT JOIN user_order uo ON ss.user_id = uo.user_id
            WHERE ss.shift_date BETWEEN %s AND %s AND COALESCE(uo.is_visible, 1) = 1
            GROUP BY ss.shift_date, ss.shift_abbrev
        """, (start_date, end_date))

        daily_counts = {}
        for row in cursor.fetchall():
            shift_date = row['shift_date']
            if shift_date not in daily_counts:
                daily_counts[shift_date] = {}
            daily_counts[shift_date][row['shift_abbrev']] = row['count']
        return daily_counts

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_shift_types():
    """Holt alle Schichtarten."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, abbreviation, hours, description, color, start_time, end_time FROM shift_types ORDER BY abbreviation")
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtarten: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def add_shift_type(data):
    """Fügt eine neue Schichtart hinzu."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO shift_types (name, abbreviation, hours, description, color, start_time, end_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (
        data['name'], data['abbreviation'], data['hours'], data['description'], data['color'], data['start_time'],
        data['end_time'])
        cursor.execute(query, params)
        conn.commit()
        return True, "Schichtart erfolgreich hinzugefügt."
    except mysql.connector.IntegrityError:
        return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_shift_type(shift_type_id, data):
    """Aktualisiert eine Schichtart."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        query = """
            UPDATE shift_types
            SET name = %s, abbreviation = %s, hours = %s, description = %s, 
                color = %s, start_time = %s, end_time = %s
            WHERE id = %s
        """
        params = (
        data['name'], data['abbreviation'], data['hours'], data['description'], data['color'], data['start_time'],
        data['end_time'], shift_type_id)
        cursor.execute(query, params)
        conn.commit()
        return True, "Schichtart erfolgreich aktualisiert."
    except mysql.connector.IntegrityError:
        return False, "Die neue Abkürzung wird bereits von einer anderen Schichtart verwendet."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_shift_type(shift_type_id):
    """Löscht eine Schichtart."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT abbreviation FROM shift_types WHERE id = %s", (shift_type_id,))
        result = cursor.fetchone()

        cursor.execute("DELETE FROM shift_types WHERE id = %s", (shift_type_id,))

        if result:
            abbrev = result['abbreviation']
            cursor.execute("DELETE FROM shift_order WHERE abbreviation = %s", (abbrev,))

        conn.commit()
        return True, "Schichtart erfolgreich gelöscht."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_ordered_shift_abbrevs(include_hidden=False):
    """Holt die sortierten Schicht-Abkürzungen."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM shift_types")
        shift_types_data = {st['abbreviation']: st for st in cursor.fetchall()}

        cursor.execute("SELECT abbreviation, sort_order, is_visible, check_for_understaffing FROM shift_order")
        order_map = {row['abbreviation']: row for row in cursor.fetchall()}

        ordered_list = []
        all_abbrevs = set(shift_types_data.keys()) | {'T.', '6', 'N.', '24'}
        for abbrev in sorted(list(all_abbrevs)):
            if abbrev in shift_types_data:
                item = shift_types_data[abbrev]
            else:
                item = {'abbreviation': abbrev,
                        'name': f"({abbrev} - Regel)" if abbrev not in ['T.', '6', 'N.', '24'] else abbrev, 'hours': 0,
                        'description': f"Harte Regel für {abbrev}.", 'color': '#FFFFFF'}
            order_data = order_map.get(abbrev, {'sort_order': 999999, 'is_visible': 1, 'check_for_understaffing': 0})
            item.update(order_data)
            if include_hidden or item['is_visible'] == 1:
                ordered_list.append(item)

        ordered_list.sort(key=lambda x: x.get('sort_order', 999999))
        return ordered_list
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtreihenfolge: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_shift_order(order_data_list):
    """Speichert die Reihenfolge der Schichten."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_order")

        if order_data_list:
            query = """
                INSERT INTO shift_order (abbreviation, sort_order, is_visible, check_for_understaffing)
                VALUES (%s, %s, %s, %s)
            """
            cursor.executemany(query, order_data_list)

        conn.commit()
        return True, "Schichtreihenfolge erfolgreich gespeichert."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Schichtreihenfolge: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()