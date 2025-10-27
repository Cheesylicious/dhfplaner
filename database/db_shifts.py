# database/db_shifts.py
import calendar
import json
from datetime import date, datetime, timedelta
from .db_core import create_connection
import mysql.connector
import os

_SHIFT_TYPES_CACHE = None
_SHIFT_ORDER_CACHE = None


def clear_shift_types_cache():
    global _SHIFT_TYPES_CACHE
    _SHIFT_TYPES_CACHE = None


def clear_shift_order_cache():
    global _SHIFT_ORDER_CACHE
    _SHIFT_ORDER_CACHE = None


# --- get_consolidated_month_data, save_shift_entry, get_shifts_for_month, get_daily_shift_counts_for_month ---
# --- bleiben unverändert ---
def get_consolidated_month_data(year, month):
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)
        month_start_date = date(year, month, 1)
        month_last_day = date(year, month, calendar.monthrange(year, month)[1])
        prev_month_last_day = month_start_date - timedelta(days=1)
        start_date_str = month_start_date.strftime('%Y-%m-%d')
        end_date_str = month_last_day.strftime('%Y-%m-%d')
        prev_date_str = prev_month_last_day.strftime('%Y-%m-%d')
        result_data = {'shifts': {}, 'daily_counts': {}, 'vacation_requests': [], 'wunschfrei_requests': {},
                       'prev_month_shifts': {}}
        cursor.execute(
            "SELECT user_id, shift_date, shift_abbrev FROM shift_schedule WHERE shift_date BETWEEN %s AND %s OR shift_date = %s",
            (start_date_str, end_date_str, prev_date_str))
        for row in cursor.fetchall():
            user_id, date_str, abbrev = str(row['user_id']), row['shift_date'], row['shift_abbrev']
            target_dict = result_data['prev_month_shifts'] if date_str == prev_date_str else result_data['shifts']
            if user_id not in target_dict: target_dict[user_id] = {}
            target_dict[user_id][date_str] = abbrev
        cursor.execute(
            "SELECT ss.shift_date, ss.shift_abbrev, COUNT(ss.shift_abbrev) as count FROM shift_schedule ss LEFT JOIN user_order uo ON ss.user_id = uo.user_id WHERE ss.shift_date BETWEEN %s AND %s AND COALESCE (uo.is_visible, 1) = 1 GROUP BY ss.shift_date, ss.shift_abbrev",
            (start_date_str, end_date_str))
        for row in cursor.fetchall():
            shift_date = row['shift_date']
            if shift_date not in result_data['daily_counts']: result_data['daily_counts'][shift_date] = {}
            result_data['daily_counts'][shift_date][row['shift_abbrev']] = row['count']
        cursor.execute("SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0",
                       (end_date_str, start_date_str))
        result_data['vacation_requests'] = cursor.fetchall()
        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (start_date_str, end_date_str))
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            if user_id_str not in result_data['wunschfrei_requests']: result_data['wunschfrei_requests'][
                user_id_str] = {}
            result_data['wunschfrei_requests'][user_id_str][row['request_date']] = (row['status'],
                                                                                    row['requested_shift'],
                                                                                    row['requested_by'], None)
        return result_data
    except mysql.connector.Error as e:
        print(f"KRITISCHER FEHLER beim konsolidierten Abrufen der Daten: {e}"); return None
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def save_shift_entry(user_id, shift_date_str, shift_abbrev, keep_request_record=False):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        if shift_abbrev in ["", "FREI"]:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s",
                           (user_id, shift_date_str))
        else:
            cursor.execute(
                "INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE shift_abbrev = %s",
                (user_id, shift_date_str, shift_abbrev, shift_abbrev))
        if shift_abbrev and shift_abbrev not in ["", "FREI"]:
            try:
                events_file_path = 'events_config.json'
                if not os.path.exists(events_file_path):
                    import sys
                    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
                    if 'database' in base_path: base_path = os.path.dirname(base_path)
                    events_file_path = os.path.join(base_path, 'events_config.json')
                with open(events_file_path, 'r', encoding='utf-8') as f:
                    all_events = json.load(f)
                date_obj = datetime.strptime(shift_date_str, '%Y-%m-%d').date()
                year_str = str(date_obj.year)
                if year_str in all_events and shift_date_str in all_events[year_str]:
                    event_info = all_events[year_str][shift_date_str]
                    event_type = event_info.get("type") if isinstance(event_info, dict) else event_info
                    if event_type == "Quartals Ausbildung":
                        cursor.execute("UPDATE users SET last_ausbildung = %s WHERE id = %s", (shift_date_str, user_id))
                    elif event_type == "Schießen":
                        cursor.execute("UPDATE users SET last_schiessen = %s WHERE id = %s", (shift_date_str, user_id))
            except (FileNotFoundError, json.JSONDecodeError, KeyError, ImportError, AttributeError, NameError) as e:
                print(f"[WARNUNG] Konnte Event-Daten für Schichteintrag nicht prüfen: {e}"); pass
        if not keep_request_record and shift_abbrev != 'X': cursor.execute(
            "DELETE FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s", (user_id, shift_date_str))
        conn.commit()
        return True, "Schicht gespeichert."
    except mysql.connector.Error as e:
        conn.rollback(); return False, f"Datenbankfehler beim Speichern der Schicht: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_shifts_for_month(year, month):
    # (Code unverändert)
    conn = create_connection()
    if conn is None: return {}
    try:
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT user_id, shift_date, shift_abbrev FROM shift_schedule WHERE shift_date BETWEEN %s AND %s",
            (start_date, end_date))
        shifts = {}
        for row in cursor.fetchall():
            user_id = str(row['user_id'])
            if user_id not in shifts: shifts[user_id] = {}
            shifts[user_id][row['shift_date']] = row['shift_abbrev']
        return shifts
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen des Schichtplans: {e}"); return {}
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_daily_shift_counts_for_month(year, month):
    # (Code unverändert)
    conn = create_connection()
    if conn is None: return {}
    try:
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT ss.shift_date, ss.shift_abbrev, COUNT(ss.shift_abbrev) as count FROM shift_schedule ss LEFT JOIN user_order uo ON ss.user_id = uo.user_id WHERE ss.shift_date BETWEEN %s AND %s AND COALESCE(uo.is_visible, 1) = 1 GROUP BY ss.shift_date, ss.shift_abbrev",
            (start_date, end_date))
        daily_counts = {}
        for row in cursor.fetchall():
            shift_date = row['shift_date']
            if shift_date not in daily_counts: daily_counts[shift_date] = {}
            daily_counts[shift_date][row['shift_abbrev']] = row['count']
        return daily_counts
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}"); return {}
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


# --- get_all_shift_types, add_shift_type, update_shift_type, delete_shift_type ---
# --- bleiben unverändert ---
def get_all_shift_types():
    global _SHIFT_TYPES_CACHE
    if _SHIFT_TYPES_CACHE is not None: return _SHIFT_TYPES_CACHE
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, abbreviation, hours, description, color, start_time, end_time, check_for_understaffing FROM shift_types ORDER BY abbreviation")
        results = cursor.fetchall()
        _SHIFT_TYPES_CACHE = results
        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtarten: {e}"); _SHIFT_TYPES_CACHE = []; return []
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def add_shift_type(data):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        query = "INSERT INTO shift_types (name, abbreviation, hours, description, color, start_time, end_time, check_for_understaffing) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        check_int = 1 if data.get('check_for_understaffing', False) else 0
        params = (data['name'], data['abbreviation'], data['hours'], data.get('description', ''), data['color'],
                  data.get('start_time') or None, data.get('end_time') or None, check_int)
        cursor.execute(query, params)
        conn.commit()
        clear_shift_types_cache();
        clear_shift_order_cache()
        return True, "Schichtart erfolgreich hinzugefügt."
    except mysql.connector.IntegrityError:
        conn.rollback(); return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except mysql.connector.Error as e:
        conn.rollback(); return False, f"Datenbankfehler beim Hinzufügen: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def update_shift_type(shift_type_id, data):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        query = "UPDATE shift_types SET name=%s, abbreviation=%s, hours=%s, description=%s, color=%s, start_time=%s, end_time=%s, check_for_understaffing=%s WHERE id=%s"
        check_int = 1 if data.get('check_for_understaffing', False) else 0
        params = (data['name'], data['abbreviation'], data['hours'], data.get('description', ''), data['color'],
                  data.get('start_time') or None, data.get('end_time') or None, check_int, shift_type_id)
        cursor.execute(query, params)
        conn.commit()
        clear_shift_types_cache();
        clear_shift_order_cache()
        return True, "Schichtart erfolgreich aktualisiert."
    except mysql.connector.IntegrityError:
        conn.rollback(); return False, "Die neue Abkürzung wird bereits von einer anderen Schichtart verwendet."
    except mysql.connector.Error as e:
        conn.rollback(); return False, f"Datenbankfehler beim Aktualisieren: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def delete_shift_type(shift_type_id):
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT abbreviation FROM shift_types WHERE id = %s", (shift_type_id,))
        result = cursor.fetchone()
        cursor.execute("DELETE FROM shift_types WHERE id = %s", (shift_type_id,))
        if result: cursor.execute("DELETE FROM shift_order WHERE abbreviation = %s", (result['abbreviation'],))
        conn.commit()
        clear_shift_types_cache();
        clear_shift_order_cache()
        return True, "Schichtart erfolgreich gelöscht."
    except mysql.connector.Error as e:
        conn.rollback(); return False, f"Datenbankfehler beim Löschen: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_ordered_shift_abbrevs(include_hidden=False):
    """
    Holt die sortierten Schicht-Abkürzungen.
    'check_for_understaffing' kommt jetzt NUR aus shift_types.
    Nutzt Caches.
    """
    global _SHIFT_ORDER_CACHE
    cache_key = include_hidden

    if _SHIFT_ORDER_CACHE is not None and cache_key in _SHIFT_ORDER_CACHE:
        return _SHIFT_ORDER_CACHE[cache_key]

    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)

        # Holen aller Typen (inkl. der Check-Info aus shift_types)
        all_shift_types_list = get_all_shift_types()  # Nutzt _SHIFT_TYPES_CACHE
        if not all_shift_types_list:
            print("[WARNUNG] get_all_shift_types lieferte keine Daten in get_ordered_shift_abbrevs.")
            all_shift_types_map = {}
        else:
            all_shift_types_map = {st['abbreviation']: st for st in all_shift_types_list}

        # --- KORREKTUR: check_for_understaffing NICHT mehr aus shift_order holen ---
        cursor.execute("SELECT abbreviation, sort_order, is_visible FROM shift_order")
        # --- ENDE KORREKTUR ---
        order_map = {row['abbreviation']: row for row in cursor.fetchall()}

        ordered_list = []
        all_known_abbrevs = set(all_shift_types_map.keys()) | set(order_map.keys()) | {'T.', '6', 'N.', '24'}

        for abbrev in sorted(list(all_known_abbrevs)):
            if abbrev in all_shift_types_map:
                # Daten aus shift_types holen (ist jetzt die Quelle für check_for_understaffing)
                item = all_shift_types_map[abbrev].copy()
                # Stelle sicher, dass der Key existiert, auch wenn er in der DB NULL ist
                item['check_for_understaffing'] = item.get('check_for_understaffing', 0)
            else:
                # Harte Regel oder nur in shift_order vorhanden
                item = {'abbreviation': abbrev,
                        'name': f"({abbrev})", 'hours': 0,
                        'description': "", 'color': '#FFFFFF',
                        'check_for_understaffing': 0}  # Default 0

            order_data = order_map.get(abbrev)

            if order_data:
                # Nur sort_order und is_visible aus shift_order übernehmen
                item['sort_order'] = order_data.get('sort_order', 999999)
                item['is_visible'] = order_data.get('is_visible', 1)
                # --- KORREKTUR: check_for_understaffing wird NICHT mehr überschrieben ---
            else:
                # Nicht in shift_order, setze Defaults
                item['sort_order'] = 999999
                item['is_visible'] = 1
                # check_for_understaffing bleibt der Wert aus shift_types (oder 0 falls harte Regel)

            # Korrigiere Name für harte Regeln
            if abbrev in ['T.', '6', 'N.', '24'] and item['name'] == f"({abbrev})":
                item['name'] = abbrev

            if include_hidden or item.get('is_visible', 1) == 1:
                ordered_list.append(item)

        ordered_list.sort(key=lambda x: x.get('sort_order', 999999))

        # Cache füllen
        if _SHIFT_ORDER_CACHE is None: _SHIFT_ORDER_CACHE = {}
        _SHIFT_ORDER_CACHE[cache_key] = ordered_list

        return ordered_list
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtreihenfolge: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_shift_order(order_data_list):
    """
    Speichert die Reihenfolge und Sichtbarkeit der Schichten.
    'check_for_understaffing' wird ignoriert.
    Leert den Cache.
    order_data_list: Liste von Tupeln: (abbreviation, sort_order, is_visible)
    """
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_order")

        if order_data_list:
            processed_list = []
            for item_tuple in order_data_list:
                # --- KORREKTUR: Erwartet jetzt 3 Elemente ---
                if len(item_tuple) == 3:
                    abbrev, sort_order, is_visible = item_tuple
                    is_visible_int = 1 if is_visible else 0
                    # --- KORREKTUR: Tupel für Query hat nur noch 3 Elemente ---
                    processed_list.append((abbrev, sort_order, is_visible_int))
                else:
                    print(
                        f"[WARNUNG] Ungültiges Tupel in save_shift_order ignoriert (erwartet 3 Elemente): {item_tuple}")

            if processed_list:
                # --- KORREKTUR: Query angepasst (ohne check_for_understaffing) ---
                query = """
                        INSERT INTO shift_order (abbreviation, sort_order, is_visible)
                        VALUES (%s, %s, %s) \
                        """
                cursor.executemany(query, processed_list)
            # --- ENDE KORREKTUREN ---

        conn.commit()
        clear_shift_order_cache()
        return True, "Schichtreihenfolge erfolgreich gespeichert."
    except mysql.connector.Error as e:
        conn.rollback()
        print(f"DB Fehler save_shift_order: {e}")
        return False, f"Datenbankfehler beim Speichern der Schichtreihenfolge: {e}"
    except Exception as e:
        conn.rollback()
        print(f"Allg. Fehler save_shift_order: {e}")
        return False, f"Allgemeiner Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- NEUE FUNKTION ---
def delete_all_shifts_for_month(year, month):
    """
    Löscht alle Einträge aus 'shift_schedule' für einen bestimmten Monat und ein bestimmtes Jahr.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()

        # SQL-Anweisung zum Löschen
        query = "DELETE FROM shift_schedule WHERE YEAR(shift_date) = %s AND MONTH(shift_date) = %s"
        cursor.execute(query, (year, month))

        deleted_rows = cursor.rowcount
        conn.commit()

        month_str = f"{year:04d}-{month:02d}"
        print(f"Schichtplan für {month_str} gelöscht. {deleted_rows} Einträge entfernt.")

        return True, f"Schichtplan für {month_str} erfolgreich gelöscht. {deleted_rows} Einträge entfernt."

    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Löschen des Schichtplans für {year}-{month}: {e}")
        return False, f"Datenbankfehler beim Löschen: {e}"
    except Exception as e:
        conn.rollback()
        print(f"Allgemeiner Fehler beim Löschen des Schichtplans für {year}-{month}: {e}")
        return False, f"Allgemeiner Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
# --- ENDE NEUE FUNKTION ---