# database/db_plan_loader.py
# NEU: Ausgelagerte Batch-Ladefunktionen für die Schichtplan-Anzeige

import calendar
from datetime import date, datetime, timedelta
from .db_core import create_connection
import mysql.connector
import traceback
# --- KORREKTUR: defaultdict importiert (wird für Locks benötigt) ---
from collections import defaultdict


# --- ENDE KORREKTUR ---


def get_consolidated_month_data(year, month):
    """
    (Alte Funktion, für Abwärtskompatibilität)
    Holt Schichtdaten, Anträge, Zählungen für Haupt-, Vor- und Folgemonat.
    """
    conn = create_connection()
    if conn is None:
        return None
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_data_for_plan_display(year, month, for_date):
    """
    (INNOVATION)
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

        # --- KORREKTUR: Falsche Datenstruktur für Locks ---
        # Stellt sicher, dass die Struktur {user_id_str: {date_str: abbrev}} ist

        locks_dict = defaultdict(dict)
        for row in locks_result:
            user_id_str = str(row['user_id'])  # Wichtig: String-ID
            lock_date = row['shift_date']

            if not isinstance(lock_date, date):
                try:
                    lock_date = datetime.strptime(str(lock_date), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    print(f"WARNUNG (neu): Ungültiges Datumsformat in Locks ignoriert: {row['shift_date']}")
                    continue

            date_str = lock_date.strftime('%Y-%m-%d')
            locks_dict[user_id_str][date_str] = row['shift_abbrev']

        result_data['locks'] = dict(locks_dict)  # Zurück zu normalem dict
        # --- ENDE KORREKTUR ---

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
        traceback.print_exc()
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()