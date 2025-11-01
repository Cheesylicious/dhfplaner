# database/db_shifts.py
# BEREINIGTE VERSION: Konzentriert sich auf das Speichern,
# Löschen und Abrufen einzelner Schicht-Einträge.

import calendar
from datetime import date, datetime, timedelta
from .db_core import create_connection, _log_activity
import mysql.connector

# NEU: Import des EventManagers für DB-basierte Event-Prüfung
from gui.event_manager import EventManager

# NEU: Konstante für auszuschließende Schichten bei einer Planlöschung
EXCLUDED_SHIFTS_ON_DELETE = ["X", "S", "QA", "EU", "WF"]


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


def save_shift_entry(user_id, shift_date_str, shift_abbrev, keep_request_record=False):
    """Speichert oder aktualisiert einen einzelnen Schichteintrag."""

    if _check_for_event_conflict_db(shift_date_str, user_id, shift_abbrev):
        return False, f"Konflikt: An diesem Tag findet ein Event statt, das die Schicht '{shift_abbrev}' verhindert."

    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        if shift_abbrev in ["", "FREI"]:
            cursor.execute("DELETE FROM shift_schedule WHERE user_id = %s AND shift_date = %s",
                           (user_id, shift_date_str))
        else:
            cursor.execute(
                "INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE shift_abbrev = %s",
                (user_id, shift_date_str, shift_abbrev, shift_abbrev))

        if not keep_request_record and shift_abbrev != 'X':
            cursor.execute(
                "DELETE FROM wunschfrei_requests WHERE user_id = %s AND request_date = %s", (user_id, shift_date_str))
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
    """ Holt alle reinen Schicht-Einträge (user_id, datum, kürzel) für einen Monat. """
    conn = create_connection()
    if conn is None:
        return {}
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
            if user_id not in shifts:
                shifts[user_id] = {}
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
        print(f"Fehler beim Abrufen des Schichtplans: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_daily_shift_counts_for_month(year, month):
    """ Holt die Zählung der Schichten pro Tag für einen Monat (für sichtbare Benutzer). """
    conn = create_connection()
    if conn is None:
        return {}
    try:
        cursor = conn.cursor(dictionary=True)
        start_date = date(year, month, 1).strftime('%Y-%m-01')
        end_date = date(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT ss.shift_date, ss.shift_abbrev, COUNT(ss.shift_abbrev) as count "
            "FROM shift_schedule ss "
            "LEFT JOIN user_order uo ON ss.user_id = uo.user_id "
            "WHERE ss.shift_date BETWEEN %s AND %s AND COALESCE(uo.is_visible, 1) = 1 "
            "GROUP BY ss.shift_date, ss.shift_abbrev",
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

            if shift_date_str_count not in daily_counts:
                daily_counts[shift_date_str_count] = {}
            daily_counts[shift_date_str_count][row['shift_abbrev']] = row['count']
        return daily_counts
    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der täglichen Schichtzählungen: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


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


# --- RE-IMPORT DER AUSGELAGERTEN FUNKTIONEN (FÜR ABWÄRTSKOMPATIBILITÄT) ---

# 1. Funktionen für Schichtarten und Reihenfolge
try:
    from .db_shift_types import (
        clear_shift_types_cache,
        clear_shift_order_cache,
        get_all_shift_types,
        add_shift_type,
        update_shift_type,
        delete_shift_type,
        get_ordered_shift_abbrevs,
        save_shift_order
    )
except ImportError as e:
    print(f"WARNUNG: Konnte ausgelagerte Schichttyp-Funktionen (db_shift_types) nicht importieren: {e}")


    # Dummy-Funktionen, falls db_shift_types.py fehlt
    def _dummy_func(*args, **kwargs):
        return False, "Importfehler db_shift_types"


    def _dummy_func_list(*args, **kwargs):
        return []


    clear_shift_types_cache = lambda: None
    clear_shift_order_cache = lambda: None
    get_all_shift_types = _dummy_func_list
    add_shift_type = _dummy_func
    update_shift_type = _dummy_func
    delete_shift_type = _dummy_func
    get_ordered_shift_abbrevs = _dummy_func_list
    save_shift_order = _dummy_func

# 2. Funktionen für das Laden von Plandaten (Batch-Loader)
try:
    from .db_plan_loader import (
        get_consolidated_month_data,
        get_all_data_for_plan_display
    )
except ImportError as e:
    print(f"WARNUNG: Konnte ausgelagerte Ladefunktionen (db_plan_loader) nicht importieren: {e}")


    # Dummy-Funktionen, falls db_plan_loader.py fehlt
    def _dummy_func_data(*args, **kwargs):
        print("FEHLER: db_plan_loader.py fehlt!")
        return None


    get_consolidated_month_data = _dummy_func_data
    get_all_data_for_plan_display = _dummy_func_data

# --- ENDE RE-IMPORT ---