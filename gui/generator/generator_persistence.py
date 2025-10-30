# gui/generator/generator_persistence.py
# NEUE DATEI
import mysql.connector
from database.db_core import create_connection
from datetime import datetime, timedelta


def save_generation_batch_to_db(live_shifts_data, year, month):
    """
    Speichert den gesamten generierten Plan (aus dem live_shifts_data)
    in einem einzigen, schnellen Batch-Vorgang in der Datenbank.
    """

    # 1. Daten "platt machen" (Flatten)
    # Wandelt das Diktionär {user_id_str: {date_str: shift}}
    # in eine Liste von Tupeln [(user_id, date, shift), ...] um.

    data_to_save = []

    # Sicherstellen, dass wir nur Daten für den relevanten Monat speichern,
    # falls live_shifts_data aus irgendeinem Grund mehr enthält.
    start_day = 1
    # Finde den letzten Tag des Monats
    try:
        end_day = (datetime(year, month + 1, 1) - timedelta(days=1)).day
    except ValueError:  # Wenn Monat 12 ist
        end_day = 31

    relevant_dates = {datetime(year, month, day).strftime('%Y-%m-%d') for day in range(start_day, end_day + 1)}

    for user_id_str, day_data in live_shifts_data.items():
        try:
            user_id_int = int(user_id_str)
        except ValueError:
            continue  # Ungültige User-ID überspringen

        for date_str, shift in day_data.items():
            # Nur Daten speichern, die zu diesem Monat gehören UND
            # die nicht leer sind (leere Einträge müssen nicht gespeichert werden).
            if date_str in relevant_dates and shift:
                data_to_save.append((
                    user_id_int,
                    date_str,
                    shift
                ))

    if not data_to_save:
        print("[GeneratorPersistence] Nichts zu speichern.")
        return True, 0, None  # Erfolg, 0 Zeilen gespeichert

    # 2. Datenbank-Batch-Operation
    conn = create_connection()
    if conn is None:
        return False, 0, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor()

        # Hocheffizienter Befehl: Füge alle ein. Wenn ein Schlüssel (user_id, shift_date)
        # bereits existiert, aktualisiere nur die Schicht (shift_abbrev).
        query = """
                INSERT INTO shift_schedule (user_id, shift_date, shift_abbrev)
                VALUES (%s, %s, %s) ON DUPLICATE KEY \
                UPDATE shift_abbrev = \
                VALUES (shift_abbrev) \
                """

        # Alle Daten auf einmal an die DB senden
        cursor.executemany(query, data_to_save)

        conn.commit()

        # rowcount bei executemany ist oft unzuverlässig, aber wir melden die Anzahl der Einträge
        affected_rows = len(data_to_save)
        print(f"[GeneratorPersistence] Batch-Speichern erfolgreich. {affected_rows} Einträge verarbeitet.")

        return True, affected_rows, None

    except mysql.connector.Error as e:
        print(f"DB Error on batch save_generation_batch_to_db: {e}")
        conn.rollback()
        return False, 0, str(e)
    except Exception as e:
        print(f"Genereller Fehler in save_generation_batch_to_db: {e}")
        conn.rollback()
        return False, 0, str(e)
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()