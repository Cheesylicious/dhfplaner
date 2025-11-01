# database/db_shift_types.py
# NEU: Ausgelagerte Funktionen für Schichtarten und deren Reihenfolge

from .db_core import create_connection
import mysql.connector

_SHIFT_TYPES_CACHE = None
_SHIFT_ORDER_CACHE = None


def clear_shift_types_cache():
    """ Leert den Cache für Schichtarten. """
    global _SHIFT_TYPES_CACHE
    _SHIFT_TYPES_CACHE = None


def clear_shift_order_cache():
    """ Leert den Cache für die Schichtreihenfolge. """
    global _SHIFT_ORDER_CACHE
    _SHIFT_ORDER_CACHE = None


def get_all_shift_types():
    """ Holt alle definierten Schichtarten aus der Datenbank (mit Cache). """
    global _SHIFT_TYPES_CACHE
    if _SHIFT_TYPES_CACHE is not None:
        return _SHIFT_TYPES_CACHE

    conn = create_connection()
    if conn is None:
        return []

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, abbreviation, hours, description, color, start_time, end_time, check_for_understaffing "
            "FROM shift_types ORDER BY abbreviation"
        )
        results = cursor.fetchall()
        _SHIFT_TYPES_CACHE = results
        return results
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der Schichtarten: {e}")
        _SHIFT_TYPES_CACHE = []
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def add_shift_type(data):
    """ Fügt eine neue Schichtart hinzu. """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()
        query = (
            "INSERT INTO shift_types (name, abbreviation, hours, description, color, start_time, end_time, check_for_understaffing) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")

        check_int = 1 if data.get('check_for_understaffing', False) else 0
        params = (data['name'], data['abbreviation'], data['hours'], data.get('description', ''), data['color'],
                  data.get('start_time') or None, data.get('end_time') or None, check_int)

        cursor.execute(query, params)
        conn.commit()

        clear_shift_types_cache()
        clear_shift_order_cache()

        return True, "Schichtart erfolgreich hinzugefügt."
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Hinzufügen: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_shift_type(shift_type_id, data):
    """ Aktualisiert eine bestehende Schichtart. """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()
        query = ("UPDATE shift_types SET name=%s, abbreviation=%s, hours=%s, description=%s, color=%s, "
                 "start_time=%s, end_time=%s, check_for_understaffing=%s WHERE id=%s")

        check_int = 1 if data.get('check_for_understaffing', False) else 0
        params = (data['name'], data['abbreviation'], data['hours'], data.get('description', ''), data['color'],
                  data.get('start_time') or None, data.get('end_time') or None, check_int, shift_type_id)

        cursor.execute(query, params)
        conn.commit()

        clear_shift_types_cache()
        clear_shift_order_cache()

        return True, "Schichtart erfolgreich aktualisiert."
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, "Die neue Abkürzung wird bereits von einer anderer Schichtart verwendet."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Aktualisieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_shift_type(shift_type_id):
    """ Löscht eine Schichtart. """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor(dictionary=True)

        # Erst Abkürzung holen, um sie aus shift_order löschen zu können
        cursor.execute("SELECT abbreviation FROM shift_types WHERE id = %s", (shift_type_id,))
        result = cursor.fetchone()

        # Aus shift_types löschen
        cursor.execute("DELETE FROM shift_types WHERE id = %s", (shift_type_id,))

        # Aus shift_order löschen
        if result:
            cursor.execute("DELETE FROM shift_order WHERE abbreviation = %s", (result['abbreviation'],))

        conn.commit()

        clear_shift_types_cache()
        clear_shift_order_cache()

        return True, "Schichtart erfolgreich gelöscht."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Löschen: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


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
    if conn is None:
        return []

    try:
        cursor = conn.cursor(dictionary=True)

        # Holen aller Typen (inkl. der Check-Info aus shift_types)
        all_shift_types_list = get_all_shift_types()  # Nutzt _SHIFT_TYPES_CACHE
        if not all_shift_types_list:
            print("[WARNUNG] get_all_shift_types lieferte keine Daten in get_ordered_shift_abbrevs.")
            all_shift_types_map = {}
        else:
            all_shift_types_map = {st['abbreviation']: st for st in all_shift_types_list}

        cursor.execute("SELECT abbreviation, sort_order, is_visible FROM shift_order")
        order_map = {row['abbreviation']: row for row in cursor.fetchall()}

        ordered_list = []
        # KORREKTUR: 'QA' zur hardcodierten Liste hinzugefügt, falls es nicht in shift_types ist
        all_known_abbrevs = set(all_shift_types_map.keys()) | set(order_map.keys()) | {'T.', '6', 'N.', '24', 'QA'}

        for abbrev in sorted(list(all_known_abbrevs)):
            if abbrev in all_shift_types_map:
                # Daten aus shift_types holen (ist jetzt die Quelle für check_for_understaffing)
                item = all_shift_types_map[abbrev].copy()
                # Stelle sicher, dass der Key existiert, auch wenn er in der DB NULL ist
                item['check_for_understaffing'] = item.get('check_for_understaffing', 0)
            else:
                # Harte Regel oder nur in shift_order vorhanden
                # KORREKTUR: 'start_time' und 'end_time' als None hinzufügen
                # Dies behebt die [WARNUNG] in _check_time_overlap, da die Keys existieren.
                item = {'abbreviation': abbrev,
                        'name': f"({abbrev})", 'hours': 0,
                        'description': "", 'color': '#FFFFFF',
                        'check_for_understaffing': 0,
                        'start_time': None,  # NEU
                        'end_time': None  # NEU
                        }
                # ENDE KORREKTUR

            order_data = order_map.get(abbrev)

            if order_data:
                # Nur sort_order und is_visible aus shift_order übernehmen
                item['sort_order'] = order_data.get('sort_order', 999999)
                item['is_visible'] = order_data.get('is_visible', 1)
            else:
                # Nicht in shift_order, setze Defaults
                item['sort_order'] = 999999
                item['is_visible'] = 1

            # Korrigiere Name für harte Regeln
            if abbrev in ['T.', '6', 'N.', '24', 'QA'] and item['name'] == f"({abbrev})":
                # 'QA' hier hinzugefügt für Konsistenz
                item['name'] = abbrev

            if include_hidden or item.get('is_visible', 1) == 1:
                ordered_list.append(item)

        ordered_list.sort(key=lambda x: x.get('sort_order', 999999))

        # Cache füllen
        if _SHIFT_ORDER_CACHE is None:
            _SHIFT_ORDER_CACHE = {}
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
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shift_order")

        if order_data_list:
            processed_list = []
            for item_tuple in order_data_list:
                if len(item_tuple) == 3:
                    abbrev, sort_order, is_visible = item_tuple
                    is_visible_int = 1 if is_visible else 0
                    processed_list.append((abbrev, sort_order, is_visible_int))
                else:
                    print(
                        f"[WARNUNG] Ungültiges Tupel in save_shift_order ignoriert (erwartet 3 Elemente): {item_tuple}")

            if processed_list:
                query = """
                        INSERT INTO shift_order (abbreviation, sort_order, is_visible)
                        VALUES (%s, %s, %s)
                        """
                cursor.executemany(query, processed_list)

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