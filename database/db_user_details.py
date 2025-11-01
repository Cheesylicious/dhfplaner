# database/db_user_details.py
# NEU: Ausgelagerte Funktionen für Benutzerdetails (Urlaubsanspruch, Teilnahme)

from .db_core import create_connection, _log_activity, _create_admin_notification, get_vacation_days_for_tenure
from datetime import datetime
import mysql.connector

# Import der Cache-Clear-Funktion aus dem Management-Modul, um Abhängigkeiten zu synchronisieren
try:
    from .db_user_management import clear_user_order_cache
except ImportError:
    # Fallback, falls die Reihenfolge der Erstellung nicht stimmt
    def clear_user_order_cache():
        print("WARNUNG: clear_user_order_cache konnte nicht aus db_user_management importiert werden.")
        pass


def get_all_user_participation():
    """ Holt die Teilnahme-Daten (Ausbildung, Schießen) für alle aktiven Benutzer. """
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Wählt nur Benutzer aus, die aktuell als aktiv gelten
        cursor.execute(f"""
            SELECT id, vorname, name, last_ausbildung, last_schiessen
            FROM users
            WHERE is_approved = 1 
            AND (is_archived = 0 OR (is_archived = 1 AND archived_date > '{now_str}'))
            AND (activation_date IS NULL OR activation_date <= '{now_str}')
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Fehler beim Abrufen der Teilnahme-Daten: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_last_event_date(user_id, event_type, date_str):
    """ Aktualisiert das Datum der letzten Teilnahme (Ausbildung/Schießen) für einen Benutzer. """
    conn = create_connection()
    if conn is None: return

    allowed_columns = {"ausbildung": "last_ausbildung", "schiessen": "last_schiessen"}
    if event_type not in allowed_columns:
        print(f"Ungültiger Ereignistyp: {event_type}")
        return

    column_name = allowed_columns[event_type]

    try:
        cursor = conn.cursor()
        query = f"UPDATE users SET {column_name} = %s WHERE id = %s"
        cursor.execute(query, (date_str, user_id))
        conn.commit()
    except Exception as e:
        print(f"Fehler beim Aktualisieren des Ereignisdatums: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def admin_batch_update_vacation_entitlements(current_user_id):
    """
    Aktualisiert den Urlaubsanspruch (gesamt und rest) für ALLE aktiven Benutzer
    basierend auf den in der DB gespeicherten Regeln (VACATION_RULES_CONFIG_KEY).
    Berücksichtigt activation_date und archived_date.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Alle aktiven Benutzer holen (inkl. zukünftig archivierte, exkl. zukünftig aktivierte)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(f"""
            SELECT id, vorname, name, entry_date, urlaub_gesamt, urlaub_rest
            FROM users
            WHERE is_approved = 1 
            AND (is_archived = 0 OR (is_archived = 1 AND archived_date > '{now_str}'))
            AND (activation_date IS NULL OR activation_date <= '{now_str}')
        """)
        all_users = cursor.fetchall()

        if not all_users:
            return False, "Keine aktiven Benutzer gefunden."

        updated_count = 0
        logs = []

        for user in all_users:
            user_id = user['id']
            old_total = user['urlaub_gesamt']
            old_rest = user['urlaub_rest']
            entry_date = user['entry_date']  # Ist bereits ein date-Objekt oder None

            # 2. Neuen Anspruch berechnen
            # Wir nutzen old_total als Fallback, falls die Regeln nicht greifen
            new_total = get_vacation_days_for_tenure(entry_date, default_days=old_total)

            if new_total != old_total:
                # 3. Differenz berechnen und Resturlaub anpassen
                # Konvertiere sicherheitshalber zu int
                try:
                    old_total_int = int(old_total)
                    old_rest_int = int(old_rest)
                except (ValueError, TypeError):
                    print(f"Warnung: Ungültige Urlaubswerte für User {user_id}. Überspringe.")
                    continue

                diff = new_total - old_total_int
                new_rest = old_rest_int + diff

                # 4. Update durchführen
                cursor.execute(
                    "UPDATE users SET urlaub_gesamt = %s, urlaub_rest = %s WHERE id = %s",
                    (new_total, new_rest, user_id)
                )
                updated_count += 1
                logs.append(
                    f"Benutzer {user['vorname']} {user['name']} (ID {user_id}): Anspruch von {old_total} auf {new_total} Tage geändert (Rest: {old_rest} -> {new_rest}).")

        if updated_count > 0:
            log_details = f"Batch-Update für Urlaubsanspruch durchgeführt. {updated_count} Mitarbeiter aktualisiert.\nDetails:\n" + "\n".join(
                logs)
            _log_activity(cursor, current_user_id, 'VACATION_BATCH_UPDATE', log_details)
            _create_admin_notification(cursor,
                                       f"Urlaubsansprüche für {updated_count} Mitarbeiter erfolgreich aktualisiert.")
            conn.commit()
            # Cache leeren, da sich Benutzerdaten (Urlaub) geändert haben
            clear_user_order_cache()
            return True, f"Erfolgreich {updated_count} Mitarbeiter aktualisiert."
        else:
            conn.rollback()
            return True, "Keine Änderungen erforderlich. Alle Ansprüche sind bereits aktuell."

    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Batch-Update des Urlaubsanspruchs: {e}")
        return False, f"Fehler beim Update: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()