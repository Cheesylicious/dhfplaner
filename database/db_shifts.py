# database/db_shifts.py
import calendar
# import json # Nicht mehr benötigt
from datetime import date, datetime, timedelta
# ANPASSUNG: _log_activity zu Imports hinzugefügt
from .db_core import create_connection, _log_activity
import mysql.connector
# import os # Nicht mehr benötigt

# NEU: Import des EventManagers für DB-basierte Event-Prüfung
from gui.event_manager import EventManager

_SHIFT_TYPES_CACHE = None
_SHIFT_ORDER_CACHE = None

# NEU: Konstante für auszuschließende Schichten bei einer Planlöschung
EXCLUDED_SHIFTS_ON_DELETE = ["X", "S", "QA", "EU", "WF"]


def clear_shift_types_cache():
    global _SHIFT_TYPES_CACHE
    _SHIFT_TYPES_CACHE = None


def clear_shift_order_cache():
    global _SHIFT_ORDER_CACHE
    _SHIFT_ORDER_CACHE = None


# --- NEUE Hilfsfunktion zur DB-basierten Event-Prüfung ---
def _check_for_event_conflict_db(date_str, user_id, shift_abbrev):
    """
    Prüft, ob der geplante Dienst an einem Datum mit einem globalen Event
    aus der Datenbank kollidiert (z.B. Ausbildung, Schießen).
    Gibt True zurück, wenn ein Konflikt besteht, sonst False.

    KORREKTUR (INNOVATION): "T.", "N." und "6" werden von dieser Prüfung ausgenommen,
    damit der Generator diese Schichten an Event-Tagen planen kann,
    solange nicht "QA" oder "S" manuell eingetragen ist.
    """
    try:
        year = int(date_str.split('-')[0])
        # Nutze EventManager, um Events für das Jahr aus der DB zu holen
        # get_events_for_year gibt ein Dict {date_str: type} zurück (im MySQL Fall)
        events_this_year_by_str = EventManager.get_events_for_year(year)

        event_type = events_this_year_by_str.get(date_str)

        # Logik zur Konfliktprüfung:
        if event_type and event_type in ["Ausbildung", "Schießen"]:

            # Schichten, die der Generator planen darf, werden ignoriert (KEIN KONFLIKT)
            generator_planned_shifts = {"T.", "N.", "6"}
            if shift_abbrev in generator_planned_shifts:
                return False  # Generator darf T/N/6 planen, kein Konflikt

            # Prüfe, ob die zuzuweisende Schicht eine *andere* Arbeitsschicht ist
            # (z.B. ein manuell eingetragenes "F", aber auch QA/S, falls sie hier landen)
            if shift_abbrev not in ["", "FREI", "U", "X", "EU", "WF", "U?"]:
                # Diese Prüfung blockiert jetzt nur noch manuelle Einträge,
                # aber nicht mehr T/N/6 vom Generator.
                print(
                    f"[INFO] Event-Konflikt verhindert: User {user_id} kann Schicht '{shift_abbrev}' am Event-Tag '{date_str}' ({event_type}) nicht übernehmen.")
                return True  # Konflikt gefunden!

    except ValueError:
        print(f"[WARNUNG] Ungültiges Datumsformat bei Event-Prüfung: {date_str}")
        return False
    except Exception as e:
        print(f"[FEHLER] Unerwarteter Fehler bei der Event-Konfliktprüfung (DB): {e}")
        return False

    return False


# --- ENDE NEUE Hilfsfunktion ---


# --- get_consolidated_month_data (Alte Funktion, jetzt auch FEHLERBEHOBEN) ---
# (Wird von der neuen Funktion nicht mehr genutzt, aber für Abwärtskompatibilität)
def get_consolidated_month_data(year, month):
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Datumsbereiche berechnen
        month_start_date = date(year, month, 1)
        month_last_day = date(year, month, calendar.monthrange(year, month)[1])

        # Vormonat (für Schichten UND Anträge)
        prev_month_last_day = month_start_date - timedelta(days=1)
        prev_month_start_date = prev_month_last_day.replace(day=1)

        # Folgemonat (nur die ersten 2 Tage für Konfliktprüfung)
        next_month_first_day = month_last_day + timedelta(days=1)
        next_month_second_day = month_last_day + timedelta(days=2)

        # String-Konvertierung
        start_date_str = month_start_date.strftime('%Y-%m-%d')
        end_date_str = month_last_day.strftime('%Y-%m-%d')

        prev_start_str = prev_month_start_date.strftime('%Y-%m-%d')
        prev_end_str = prev_month_last_day.strftime('%Y-%m-%d')

        next_date_1_str = next_month_first_day.strftime('%Y-%m-%d')
        next_date_2_str = next_month_second_day.strftime('%Y-%m-%d')

        # 2. Ergebnis-Struktur vorbereiten
        result_data = {
            'shifts': {},
            'daily_counts': {},
            'vacation_requests': [],
            'wunschfrei_requests': {},
            'prev_month_shifts': {},
            'next_month_shifts': {},
            'prev_month_vacations': [],
            'prev_month_wunschfrei': {}
        }

        # 3. EINE Abfrage für ALLE Schichtdaten (Vormonat, Hauptmonat, Folgemonat)
        cursor.execute(
            """
            SELECT user_id, shift_date, shift_abbrev
            FROM shift_schedule
            WHERE (shift_date BETWEEN %s AND %s) -- Hauptmonat
               OR (shift_date BETWEEN %s AND %s) -- Vormonat
               OR shift_date = %s                -- Folgetag 1
               OR shift_date = %s -- Folgetag 2
            """,
            (start_date_str, end_date_str, prev_start_str, prev_end_str, next_date_1_str, next_date_2_str)
        )

        # 4. Daten in die richtigen Caches sortieren (FEHLERBEHOBEN)
        for row in cursor.fetchall():
            user_id, abbrev = str(row['user_id']), row['shift_abbrev']

            # --- FIX (selber Fehler wie in der neuen Funktion) ---
            current_date_obj = row['shift_date']
            if not isinstance(current_date_obj, date):
                try:
                    current_date_obj = datetime.strptime(str(current_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    print(f"WARNUNG (alt): Ungültiges Datumsformat in Schichtdaten ignoriert: {row['shift_date']}")
                    continue
            date_str = current_date_obj.strftime('%Y-%m-%d')
            # --- END FIX ---

            if current_date_obj.month == prev_month_last_day.month:
                target_dict = result_data['prev_month_shifts']
            elif current_date_obj.month == next_month_first_day.month:
                target_dict = result_data['next_month_shifts']
            else:
                target_dict = result_data['shifts']

            if user_id not in target_dict:
                target_dict[user_id] = {}
            target_dict[user_id][date_str] = abbrev

        # 5. Restliche Abfragen (Hauptmonat) (FEHLERBEHOBEN)
        cursor.execute(
            "SELECT ss.shift_date, ss.shift_abbrev, COUNT(ss.shift_abbrev) as count FROM shift_schedule ss LEFT JOIN user_order uo ON ss.user_id = uo.user_id WHERE ss.shift_date BETWEEN %s AND %s AND COALESCE (uo.is_visible, 1) = 1 GROUP BY ss.shift_date, ss.shift_abbrev",
            (start_date_str, end_date_str))
        for row in cursor.fetchall():
            # --- FIX ---
            shift_date_obj = row['shift_date']
            if not isinstance(shift_date_obj, date):
                try:
                    shift_date_obj = datetime.strptime(str(shift_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            shift_date_str_count = shift_date_obj.strftime('%Y-%m-%d')
            # --- END FIX ---
            if shift_date_str_count not in result_data['daily_counts']: result_data['daily_counts'][
                shift_date_str_count] = {}
            result_data['daily_counts'][shift_date_str_count][row['shift_abbrev']] = row['count']

        cursor.execute("SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0",
                       (end_date_str, start_date_str))
        result_data['vacation_requests'] = cursor.fetchall()

        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (start_date_str, end_date_str))
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            # --- FIX ---
            request_date_obj = row['request_date']
            if not isinstance(request_date_obj, date):
                try:
                    request_date_obj = datetime.strptime(str(request_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            request_date_str = request_date_obj.strftime('%Y-%m-%d')
            # --- END FIX ---
            if user_id_str not in result_data['wunschfrei_requests']: result_data['wunschfrei_requests'][
                user_id_str] = {}
            result_data['wunschfrei_requests'][user_id_str][request_date_str] = (row['status'],
                                                                                 row['requested_shift'],
                                                                                 row['requested_by'], None)

        # 6. NEU: Abfragen für Vormonats-Anträge (FEHLERBEHOBEN)
        cursor.execute("SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0",
                       (prev_end_str, prev_start_str))
        result_data['prev_month_vacations'] = cursor.fetchall()

        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (prev_start_str, prev_end_str))
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            # --- FIX ---
            request_date_obj = row['request_date']
            if not isinstance(request_date_obj, date):
                try:
                    request_date_obj = datetime.strptime(str(request_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            request_date_str = request_date_obj.strftime('%Y-%m-%d')
            # --- END FIX ---
            if user_id_str not in result_data['prev_month_wunschfrei']: result_data['prev_month_wunschfrei'][
                user_id_str] = {}
            result_data['prev_month_wunschfrei'][user_id_str][request_date_str] = (row['status'],
                                                                                   row['requested_shift'],
                                                                                   row['requested_by'], None)

        return result_data
    except mysql.connector.Error as e:
        print(f"KRITISCHER FEHLER beim konsolidierten Abrufen der Daten: {e}");
        return None
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


# --- INNOVATION: NEUE BATCH-LADEFUNKTION (JETZT MIT FEHLERBEHEBUNG) ---
def get_all_data_for_plan_display(year, month, for_date):
    """
    Holt ALLE Daten (Benutzer, Locks, Schichten, Anträge) für das Schichtplan-Tab
    über eine EINZIGE Datenbankverbindung, um die Latenz zu minimieren.
    """
    conn = create_connection()
    if conn is None:
        return None

    # Das finale Datenpaket
    result_data = {
        'users': [],
        'locks': {},
        'shifts': {},
        'daily_counts': {},
        'vacation_requests': [],
        'wunschfrei_requests': {},
        'prev_month_shifts': {},
        'next_month_shifts': {},
        'prev_month_vacations': [],
        'prev_month_wunschfrei': {}
    }

    try:
        cursor = conn.cursor(dictionary=True)

        # === 1. Abfrage: Benutzer (Logik aus db_users.get_ordered_users_for_schedule) ===
        print("[Batch Load] 1/7: Lade Benutzer...")
        user_query = """
                     SELECT u.*, uo.sort_order, COALESCE(uo.is_visible, 1) as is_visible
                     FROM users u
                              LEFT JOIN user_order uo ON u.id = uo.user_id
                     WHERE u.is_approved = 1 \
                     """

        start_of_month = for_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_in_month_user = calendar.monthrange(for_date.year, for_date.month)[1]
        end_of_month_date = for_date.replace(day=days_in_month_user, hour=23, minute=59, second=59)
        start_of_month_str = start_of_month.strftime('%Y-%m-%d %H:%M:%S')
        end_of_month_date_str = end_of_month_date.strftime('%Y-%m-%d %H:%M:%S')

        user_query += f" AND (u.is_archived = 0 OR (u.is_archived = 1 AND u.archived_date > '{start_of_month_str}'))"
        user_query += f" AND (u.activation_date IS NULL OR u.activation_date <= '{end_of_month_date_str}')"
        user_query += " ORDER BY uo.sort_order ASC, u.name ASC"

        cursor.execute(user_query)
        result_data['users'] = cursor.fetchall()

        # === 2. Abfrage: Schichtsicherungen (Logik aus db_locks.get_locks_for_month) ===
        print("[Batch Load] 2/7: Lade Schichtsicherungen...")
        cursor.execute("""
                       SELECT user_id, shift_date, shift_abbrev
                       FROM shift_locks
                       WHERE YEAR (shift_date) = %s
                         AND MONTH (shift_date) = %s
                       """, (year, month))

        locks_result = cursor.fetchall()
        # --- FEHLERBEHEBUNG FÜR DATUM (falls es als str kommt) ---
        locks_dict = {}
        for row in locks_result:
            lock_date = row['shift_date']
            if not isinstance(lock_date, date):
                try:
                    lock_date = datetime.strptime(str(lock_date), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            locks_dict[(row['user_id'], lock_date.strftime('%Y-%m-%d'))] = row['shift_abbrev']
        result_data['locks'] = locks_dict
        # --- ENDE FEHLERBEHEBUNG ---

        # === 3. Abfrage: Schichtdaten (Logik aus get_consolidated_month_data) ===
        print("[Batch Load] 3/7: Lade Schichtdaten (Haupt, Vor-, Folgemonat)...")
        month_start_date = date(year, month, 1)
        month_last_day = date(year, month, calendar.monthrange(year, month)[1])
        prev_month_last_day = month_start_date - timedelta(days=1)
        prev_month_start_date = prev_month_last_day.replace(day=1)
        next_month_first_day = month_last_day + timedelta(days=1)
        next_month_second_day = month_last_day + timedelta(days=2)
        start_date_str = month_start_date.strftime('%Y-%m-%d')
        end_date_str = month_last_day.strftime('%Y-%m-%d')
        prev_start_str = prev_month_start_date.strftime('%Y-%m-%d')
        prev_end_str = prev_month_last_day.strftime('%Y-%m-%d')
        next_date_1_str = next_month_first_day.strftime('%Y-%m-%d')
        next_date_2_str = next_month_second_day.strftime('%Y-%m-%d')

        cursor.execute(
            """
            SELECT user_id, shift_date, shift_abbrev
            FROM shift_schedule
            WHERE (shift_date BETWEEN %s AND %s) -- Hauptmonat
               OR (shift_date BETWEEN %s AND %s) -- Vormonat
               OR shift_date = %s                -- Folgetag 1
               OR shift_date = %s -- Folgetag 2
            """,
            (start_date_str, end_date_str, prev_start_str, prev_end_str, next_date_1_str, next_date_2_str)
        )

        for row in cursor.fetchall():
            user_id, abbrev = str(row['user_id']), row['shift_abbrev']

            # --- FEHLERBEHEBUNG (DER GEMELDETE FEHLER) ---
            current_date_obj = row['shift_date']
            if not isinstance(current_date_obj, date):
                try:
                    # Versuche, es als String zu parsen
                    current_date_obj = datetime.strptime(str(current_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    # Wenn das Datum ungültig ist, überspringe diesen Eintrag
                    print(f"WARNUNG (neu): Ungültiges Datumsformat in Schichtdaten ignoriert: {row['shift_date']}")
                    continue

            date_str = current_date_obj.strftime('%Y-%m-%d')
            # --- ENDE FEHLERBEHEBUNG ---

            if current_date_obj.month == prev_month_last_day.month:
                target_dict = result_data['prev_month_shifts']
            elif current_date_obj.month == next_month_first_day.month:
                target_dict = result_data['next_month_shifts']
            else:
                target_dict = result_data['shifts']

            if user_id not in target_dict: target_dict[user_id] = {}
            target_dict[user_id][date_str] = abbrev

        # === 4. Abfrage: Tageszählungen (Hauptmonat) ===
        print("[Batch Load] 4/7: Lade Tageszählungen...")
        cursor.execute(
            "SELECT ss.shift_date, ss.shift_abbrev, COUNT(ss.shift_abbrev) as count FROM shift_schedule ss LEFT JOIN user_order uo ON ss.user_id = uo.user_id WHERE ss.shift_date BETWEEN %s AND %s AND COALESCE (uo.is_visible, 1) = 1 GROUP BY ss.shift_date, ss.shift_abbrev",
            (start_date_str, end_date_str))
        for row in cursor.fetchall():
            # --- FEHLERBEHEBUNG ---
            shift_date_obj = row['shift_date']
            if not isinstance(shift_date_obj, date):
                try:
                    shift_date_obj = datetime.strptime(str(shift_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            shift_date_str_count = shift_date_obj.strftime('%Y-%m-%d')
            # --- ENDE FEHLERBEHEBUNG ---
            if shift_date_str_count not in result_data['daily_counts']: result_data['daily_counts'][
                shift_date_str_count] = {}
            result_data['daily_counts'][shift_date_str_count][row['shift_abbrev']] = row['count']

        # === 5. Abfrage: Urlaub (Hauptmonat) ===
        print("[Batch Load] 5/7: Lade Urlaub (Hauptmonat)...")
        cursor.execute("SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0",
                       (end_date_str, start_date_str))
        result_data['vacation_requests'] = cursor.fetchall()

        # === 6. Abfrage: Wunschfrei (Hauptmonat) ===
        print("[Batch Load] 6/7: Lade Wunschfrei (Hauptmonat)...")
        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (start_date_str, end_date_str))
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            # --- FEHLERBEHEBUNG ---
            request_date_obj = row['request_date']
            if not isinstance(request_date_obj, date):
                try:
                    request_date_obj = datetime.strptime(str(request_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            request_date_str = request_date_obj.strftime('%Y-%m-%d')
            # --- ENDE FEHLERBEHEBUNG ---
            if user_id_str not in result_data['wunschfrei_requests']: result_data['wunschfrei_requests'][
                user_id_str] = {}
            result_data['wunschfrei_requests'][user_id_str][request_date_str] = (row['status'],
                                                                                 row['requested_shift'],
                                                                                 row['requested_by'], None)

        # === 7. Abfrage: Urlaub & Wunschfrei (Vormonat) ===
        print("[Batch Load] 7/7: Lade Anträge (Vormonat)...")
        cursor.execute("SELECT * FROM vacation_requests WHERE (start_date <= %s AND end_date >= %s) AND archived = 0",
                       (prev_end_str, prev_start_str))
        result_data['prev_month_vacations'] = cursor.fetchall()

        cursor.execute(
            "SELECT user_id, request_date, status, requested_shift, requested_by FROM wunschfrei_requests WHERE request_date BETWEEN %s AND %s",
            (prev_start_str, prev_end_str))
        for row in cursor.fetchall():
            user_id_str = str(row['user_id'])
            # --- FEHLERBEHEBUNG ---
            request_date_obj = row['request_date']
            if not isinstance(request_date_obj, date):
                try:
                    request_date_obj = datetime.strptime(str(request_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            request_date_str = request_date_obj.strftime('%Y-%m-%d')
            # --- ENDE FEHLERBEHEBUNG ---
            if user_id_str not in result_data['prev_month_wunschfrei']: result_data['prev_month_wunschfrei'][
                user_id_str] = {}
            result_data['prev_month_wunschfrei'][user_id_str][request_date_str] = (row['status'],
                                                                                   row['requested_shift'],
                                                                                   row['requested_by'], None)

        print("[Batch Load] Alle 7 Abfragen über eine Verbindung abgeschlossen.")
        return result_data

    except mysql.connector.Error as e:
        print(f"KRITISCHER FEHLER beim konsolidierten Abrufen (get_all_data_for_plan_display): {e}");
        return None
    except Exception as e:
        print(f"ALLGEMEINER FEHLER bei get_all_data_for_plan_display: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- ENDE INNOVATION ---


def save_shift_entry(user_id, shift_date_str, shift_abbrev, keep_request_record=False):
    """Speichert oder aktualisiert einen einzelnen Schichteintrag."""

    if _check_for_event_conflict_db(shift_date_str, user_id, shift_abbrev):
        return False, f"Konflikt: An diesem Tag findet ein Event statt, das die Schicht '{shift_abbrev}' verhindert."

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

        if not keep_request_record and shift_abbrev != 'X': cursor.execute(
            "DELETE FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s", (user_id, shift_date_str))
        conn.commit()
        return True, "Schicht gespeichert."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Datenbankfehler beim Speichern der Schicht: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_shifts_for_month(year, month):
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
            # --- FEHLERBEHEBUNG ---
            shift_date_obj = row['shift_date']
            if not isinstance(shift_date_obj, date):
                try:
                    shift_date_obj = datetime.strptime(str(shift_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            shifts[user_id][shift_date_obj.strftime('%Y-%m-%d')] = row['shift_abbrev']
            # --- ENDE FEHLERBEHEBUNG ---
        return shifts
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen des Schichtplans: {e}");
        return {}
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_daily_shift_counts_for_month(year, month):
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
            # --- FEHLERBEHEBUNG ---
            shift_date_obj = row['shift_date']
            if not isinstance(shift_date_obj, date):
                try:
                    shift_date_obj = datetime.strptime(str(shift_date_obj), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue
            shift_date_str_count = shift_date_obj.strftime('%Y-%m-%d')
            # --- ENDE FEHLERBEHEBUNG ---
            if shift_date_str_count not in daily_counts: daily_counts[shift_date_str_count] = {}
            daily_counts[shift_date_str_count][row['shift_abbrev']] = row['count']
        return daily_counts
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}");
        return {}
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


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
        print(f"Fehler beim Abrufen der Schichtarten: {e}");
        _SHIFT_TYPES_CACHE = [];
        return []
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
        conn.rollback();
        return False, "Eine Schichtart mit dieser Abkürzung existiert bereits."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Datenbankfehler beim Hinzufügen: {e}"
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
        conn.rollback();
        return False, "Die neue Abkürzung wird bereits von einer anderer Schichtart verwendet."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Datenbankfehler beim Aktualisieren: {e}"
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
        conn.rollback();
        return False, f"Datenbankfehler beim Löschen: {e}"
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

        cursor.execute("SELECT abbreviation, sort_order, is_visible FROM shift_order")
        order_map = {row['abbreviation']: row for row in cursor.fetchall()}

        ordered_list = []
        # --- KORREKTUR: 'QA' zur hardcodierten Liste hinzugefügt, falls es nicht in shift_types ist ---
        all_known_abbrevs = set(all_shift_types_map.keys()) | set(order_map.keys()) | {'T.', '6', 'N.', '24', 'QA'}

        for abbrev in sorted(list(all_known_abbrevs)):
            if abbrev in all_shift_types_map:
                # Daten aus shift_types holen (ist jetzt die Quelle für check_for_understaffing)
                item = all_shift_types_map[abbrev].copy()
                # Stelle sicher, dass der Key existiert, auch wenn er in der DB NULL ist
                item['check_for_understaffing'] = item.get('check_for_understaffing', 0)
            else:
                # Harte Regel oder nur in shift_order vorhanden
                # --- KORREKTUR: 'start_time' und 'end_time' als None hinzufügen ---
                # Dies behebt die [WARNUNG] in _check_time_overlap, da die Keys existieren.
                item = {'abbreviation': abbrev,
                        'name': f"({abbrev})", 'hours': 0,
                        'description': "", 'color': '#FFFFFF',
                        'check_for_understaffing': 0,
                        'start_time': None,  # NEU
                        'end_time': None  # NEU
                        }
                # --- ENDE KORREKTUR ---

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
                        VALUES (%s, %s, %s) \
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


# --- KORRIGIERTE UND ZURÜCKBENANNTE FUNKTION ---
def delete_all_shifts_for_month(year, month, current_user_id):
    """
    Löscht alle planbaren Schicht-Einträge aus 'shift_schedule' für einen Monat und ein Jahr,
    schließt jedoch bestimmte genehmigte Kürzel (X, S, QA, EU, WF) UND gesicherte Schichten
    (aus shift_locks) aus.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()

        # INNOVATIV: Verwendung von Platzhaltern für die dynamische Liste
        placeholders = ', '.join(['%s'] * len(EXCLUDED_SHIFTS_ON_DELETE))

        # --- KORREKTUR: SQL-Anweisung ---
        # Fügt eine "NOT EXISTS" Klausel hinzu, um Einträge zu schützen,
        # die in 'shift_locks' vorhanden sind.
        query = f"""
            DELETE FROM shift_schedule 
            WHERE YEAR(shift_date) = %s 
              AND MONTH(shift_date) = %s
              AND shift_abbrev NOT IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1 FROM shift_locks sl
                  WHERE sl.user_id = shift_schedule.user_id
                    AND sl.shift_date = shift_schedule.shift_date
              )
        """
        # --- ENDE KORREKTUR ---

        # Die Werte für die Query: (year, month, 'X', 'S', 'QA', 'EU', 'WF')
        query_values = (year, month,) + tuple(EXCLUDED_SHIFTS_ON_DELETE)

        cursor.execute(query, query_values)

        deleted_rows = cursor.rowcount

        month_str = f"{year:04d}-{month:02d}"

        # Protokollierung mit Admin-ID
        log_msg = f'Plan für {month_str} (ohne {", ".join(EXCLUDED_SHIFTS_ON_DELETE)} u. Locks) gelöscht. {deleted_rows} Zeilen entfernt.'
        _log_activity(cursor, current_user_id, 'SHIFTPLAN_DELETE', log_msg)

        conn.commit()

        return True, f"Schichtplan für {month_str} erfolgreich gelöscht. {deleted_rows} Einträge wurden entfernt (Ausgenommen: {', '.join(EXCLUDED_SHIFTS_ON_DELETE)} und gesicherte Schichten)."

    except mysql.connector.Error as e:
        conn.rollback()
        print(f"Fehler beim Löschen des Schichtplans für {year}-{month}: {e}")
        return False, f"Datenbankfehler beim Löschen: {e}"
    except Exception as e:
        conn.rollback()
        print(f"Allgemeiner Fehler beim Löschen des Schichtplans für {year}-{month}: {e}")
        return False, f"Unerwarteter Fehler beim Löschen: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
# --- ENDE KORRIGIERTE FUNKTION ---