# database/db_users.py
# --- ANGEPASSTE IMPORTE ---
from database.db_core import create_connection, hash_password, _log_activity, _create_admin_notification, \
    get_vacation_days_for_tenure
from datetime import datetime
import calendar  # NEUER IMPORT
# --- ENDE ANPASSUNG ---
import mysql.connector

# --- NEUE GLOBALE CACHE-VARIABLEN ---
_USER_ORDER_CACHE = None


def clear_user_order_cache():
    """Leert den Cache für die sortierte Liste der Benutzer."""
    global _USER_ORDER_CACHE
    _USER_ORDER_CACHE = None


# --- Restliche Funktionen (get_user_count bis log_user_logout) bleiben unverändert ---

def get_user_count():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None:
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        print(f"Fehler beim Zählen der Benutzer: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def log_user_login(user_id, vorname, name):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_fullname = f"{vorname} {name}"

    try:
        cursor = conn.cursor()
        log_details = f'Benutzer {user_fullname} hat sich angemeldet.'
        _log_activity(cursor, user_id, 'USER_LOGIN', log_details)
        conn.commit()
    except Exception as e:
        print(f"Fehler beim Protokollieren des Logins: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def log_user_logout(user_id, vorname, name):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return

    logout_time = datetime.now()
    user_fullname = f"{vorname} {name}"

    try:
        cursor = conn.cursor()
        cursor.execute("""
                       SELECT timestamp
                       FROM activity_log
                       WHERE user_id = %s AND action_type = 'USER_LOGIN'
                       ORDER BY id DESC LIMIT 1
                       """, (user_id,))
        result = cursor.fetchone()
        if result:
            login_time_str = result[0]
            try:
                login_time = datetime.strptime(login_time_str, '%Y-%m-%d %H:%M:%S')
                duration = logout_time - login_time
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = ""
                if hours > 0: duration_str += f"{hours}h "
                if minutes > 0: duration_str += f"{minutes}m "
                if seconds > 0: duration_str += f"{seconds}s"
                if total_seconds > 0:
                    log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer: {duration_str.strip()}.'
                else:
                    log_details = f'Benutzer {user_fullname} hat sich abgemeldet.'
            except ValueError:
                log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer konnte nicht berechnet werden (Login-Zeitpunkt Fehler).'
        else:
            log_details = f'Benutzer {user_fullname} hat sich abgemeldet. Sitzungsdauer konnte nicht berechnet werden (kein Login-Eintrag gefunden).'
        _log_activity(cursor, user_id, 'USER_LOGOUT', log_details)
        conn.commit()
    except Exception as e:
        print(f"Fehler beim Protokollieren des Logouts: {e}")
        conn.rollback()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def register_user(vorname, name, password, role="Benutzer"):
    # ... (verändert) ...
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        entry_date = datetime.now().strftime('%Y-%m-%d')

        # --- NEUE LOGIK FÜR URLAUBSBERECHNUNG ---
        # (Standard 30 wird von der Funktion als Fallback genutzt)
        urlaub_gesamt = get_vacation_days_for_tenure(entry_date)
        # --- ENDE NEUE LOGIK ---

        # is_archived standardmäßig 0, archived_date ist NULL
        # activation_date standardmäßig NULL (NEU)
        # urlaub_gesamt und urlaub_rest werden jetzt dynamisch gesetzt
        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, entry_date, is_approved, is_archived, archived_date, urlaub_gesamt, urlaub_rest, activation_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (vorname, name, password_hash, role, entry_date, 0, 0, None, urlaub_gesamt, urlaub_gesamt, None)
        )
        _log_activity(cursor, None, 'USER_REGISTRATION',
                      f'Benutzer {vorname} {name} hat sich registriert und wartet auf Freischaltung.')
        _create_admin_notification(cursor,
                                   f"Neuer Benutzer {vorname} {name} wartet auf Freischaltung.")
        conn.commit()
        clear_user_order_cache()
        return True, "Benutzer erfolgreich registriert. Sie müssen von einem Administrator freigeschaltet werden."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Fehler bei der Registrierung: {e}"
    except Exception as e:
        conn.rollback()
        return False, f"Fehler bei der Registrierung: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def authenticate_user(vorname, name, password):
    # ... (verändert, prüft jetzt auch activation_date) ...
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        password_hash = hash_password(password)
        if vorname == "Super" and name == "Admin" and password == "TemporaryAccess123":
            cursor.execute("SELECT * FROM users WHERE role = 'SuperAdmin' LIMIT 1")
            user = cursor.fetchone()
            if user:
                print("!!! ACHTUNG: SuperAdmin-Backdoor-Login erfolgreich !!!")
                if user.get('is_archived', 0) == 1:
                    print("!!! FEHLER: Backdoor-Login-Benutzer ist archiviert! !!!")
                    return None
                return user
            cursor.execute("SELECT * FROM users WHERE role = 'Admin' LIMIT 1")
            user = cursor.fetchone()
            if user:
                print("!!! ACHTUNG: Admin-Backdoor-Login erfolgreich !!!")
                if user.get('is_archived', 0) == 1:
                    print("!!! FEHLER: Backdoor-Login-Benutzer ist archiviert! !!!")
                    return None
                return user
            return None

        cursor.execute(
            "SELECT * FROM users WHERE vorname = %s AND name = %s AND password_hash = %s",
            (vorname, name, password_hash)
        )
        user = cursor.fetchone()
        if user:
            # 1. Check Freischaltung
            if user.get('is_approved') == 0:
                return None

            # 2. Check Archivierung
            if user.get('is_archived', 0) == 1:
                # Prüfe, ob das Archivierungsdatum in der Zukunft liegt
                archived_date = user.get('archived_date')
                if archived_date and archived_date > datetime.now():
                    pass  # Zukünftige Archivierung, Login noch erlaubt, weiter prüfen
                else:
                    return None  # Bereits archiviert

            # 3. Check Aktivierung (NEU)
            activation_date = user.get('activation_date')
            if activation_date and activation_date > datetime.now():
                return None  # Zukünftige Aktivierung, Login noch nicht erlaubt

            # Wenn alle Prüfungen bestanden, User zurückgeben
            return user

        return None
    except Exception as e:
        print(f"Fehler bei der Authentifizierung: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_user_by_id(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        return user
    except Exception as e:
        print(f"Fehler beim Abrufen des Benutzers (ID: {user_id}): {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_users():
    # ... (unverändert, holt alle Status-Spalten) ...
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        # NEU: activation_date hinzugefügt
        cursor.execute(
            "SELECT id, vorname, name, role, is_approved, is_archived, archived_date, activation_date FROM users")
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"Fehler beim Abrufen aller Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_users_with_details():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"Fehler beim Abrufen der Benutzerdetails: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_ordered_users_for_schedule(include_hidden=False, for_date=None):
    """
    Holt die Benutzer in der festgelegten Reihenfolge.
    Gibt standardmäßig nur freigeschaltete (is_approved = 1) UND aktive Benutzer zurück.
    Wenn for_date angegeben ist (Stichtag ist der *Beginn des Monats*),
    werden Benutzer basierend auf ihrem Aktivierungs- und Archivierungsdatum gefiltert.
    """
    global _USER_ORDER_CACHE

    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)

        # Basisteil der Query
        query = """
                SELECT u.*, uo.sort_order, COALESCE(uo.is_visible, 1) as is_visible
                FROM users u
                         LEFT JOIN user_order uo ON u.id = uo.user_id
                WHERE u.is_approved = 1
                """

        # Bedingung für Archivierung und Aktivierung hinzufügen
        if for_date:
            # 'for_date' ist der *Start des aktuellen Monats* (z.B. 2025-10-01 00:00:00)
            date_str = for_date.strftime('%Y-%m-%d %H:%M:%S')

            # Ende des Monats berechnen (für Aktivierungs-Check)
            days_in_month = calendar.monthrange(for_date.year, for_date.month)[1]
            end_of_month_date = for_date.replace(day=days_in_month, hour=23, minute=59, second=59)
            end_of_month_date_str = end_of_month_date.strftime('%Y-%m-%d %H:%M:%S')

            # LOGIK ARCHIVIERUNG (unverändert):
            # Zeige Benutzer, die (nicht archiviert sind)
            # ODER (deren Archivierungsdatum *NACH* dem Start des Monats liegt)
            query += f" AND (u.is_archived = 0 OR (u.is_archived = 1 AND u.archived_date > '{date_str}'))"

            # LOGIK AKTIVIERUNG (NEU):
            # Zeige Benutzer, die (kein Aktivierungsdatum haben)
            # ODER (deren Aktivierungsdatum *VOR* dem Ende des Monats liegt)
            query += f" AND (u.activation_date IS NULL OR u.activation_date <= '{end_of_month_date_str}')"

        else:
            # Wenn kein Datum angegeben ist (für allgemeine Listen wie UserOrderWindow):
            # Zeige nur *aktuell* aktive Benutzer an
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # (Archivierung: nicht archiviert ODER Archivierung in Zukunft)
            query += f" AND (u.is_archived = 0 OR (u.is_archived = 1 AND u.archived_date > '{now_str}'))"

            # (Aktivierung: kein Datum ODER Datum in Vergangenheit) (NEU)
            query += f" AND (u.activation_date IS NULL OR u.activation_date <= '{now_str}')"

        # Sortierung anhängen
        query += " ORDER BY uo.sort_order ASC, u.name ASC"

        cursor.execute(query)
        relevant_users = cursor.fetchall()

        # Cache aktualisieren *nur* wenn die Standardabfrage (aktive User) läuft
        if not for_date:
            _USER_ORDER_CACHE = relevant_users  # Cache enthält jetzt nur aktive

        # Rückgabe basierend auf dem include_hidden Flag
        if include_hidden:
            return relevant_users
        else:
            # Gibt nur die sichtbaren relevanten Benutzer zurück (für den Schichtplan)
            return [user for user in relevant_users if user.get('is_visible', 1) == 1]

    except mysql.connector.Error as e:
        print(f"Fehler beim Abrufen der sortierten Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_user_order(user_order_list):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        for index, user_info in enumerate(user_order_list):
            user_id = user_info['id']
            is_visible = user_info.get('is_visible', 1)
            query = """
                    INSERT INTO user_order (user_id, sort_order, is_visible)
                    VALUES (%s, %s, %s) AS new
                    ON DUPLICATE KEY \
                    UPDATE \
                        sort_order = new.sort_order, \
                        is_visible = new.is_visible
                    """
            cursor.execute(query, (user_id, index, is_visible))
        conn.commit()
        clear_user_order_cache()
        return True, "Reihenfolge erfolgreich gespeichert."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Speichern der Benutzerreihenfolge: {e}")
        return False, f"Fehler beim Speichern: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_user_participation():
    # ... (verändert, prüft activation_date) ...
    conn = create_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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


def update_user_details(user_id, details, current_user_id):
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()

        # --- NEU: Leere Strings für Datumsfelder in None umwandeln ---
        # (Wird von user_edit_window jetzt als None übergeben, aber doppelt sicher)
        for date_field in ['geburtstag', 'entry_date', 'activation_date', 'archived_date']:
            if date_field in details and details[date_field] == "":
                details[date_field] = None
        # --- ENDE NEU ---

        valid_details = {k: v for k, v in details.items() if k != 'password'}

        # --- ANPASSUNG FÜR URLAUBSBERECHNUNG BEI DATUMSÄNDERUNG ---
        if 'entry_date' in valid_details:
            new_entry_date = valid_details['entry_date']
            default_days = 30  # Standardwert

            # Wenn urlaub_gesamt im Update-Paket ist, nutze diesen als neuen Basiswert (falls Datum leer)
            # Konvertiere sicherheitshalber zu int
            if 'urlaub_gesamt' in valid_details:
                try:
                    default_days = int(valid_details['urlaub_gesamt'])
                except (ValueError, TypeError):
                    print(
                        f"Warnung: Ungültiger Wert für urlaub_gesamt in details: {valid_details['urlaub_gesamt']}. Fallback auf 30.")
                    default_days = 30
            else:
                # Wenn urlaub_gesamt NICHT geändert wird, hole aktuellen Wert aus DB als Basis
                cursor.execute("SELECT urlaub_gesamt FROM users WHERE id = %s", (user_id,))
                current_total_result = cursor.fetchone()
                if current_total_result:
                    try:
                        default_days = int(current_total_result[0])
                    except (ValueError, TypeError):
                        print(
                            f"Warnung: Ungültiger Wert für urlaub_gesamt in DB: {current_total_result[0]}. Fallback auf 30.")
                        default_days = 30

            # Berechne neuen Gesamtanspruch
            new_total_vacation = get_vacation_days_for_tenure(new_entry_date, default_days)

            # Hole alten Gesamtanspruch und Resturlaub
            cursor.execute("SELECT urlaub_gesamt, urlaub_rest FROM users WHERE id = %s", (user_id,))
            current_vacation = cursor.fetchone()
            if current_vacation:
                try:
                    # --- KORREKTUR: Explizite Konvertierung zu int ---
                    old_total = int(current_vacation[0])
                    old_rest = int(current_vacation[1])
                    # --- ENDE KORREKTUR ---

                    diff = new_total_vacation - old_total  # Jetzt sollte es int - int sein
                    new_rest = old_rest + diff

                    valid_details['urlaub_gesamt'] = new_total_vacation
                    valid_details[
                        'urlaub_rest'] = new_rest if new_rest >= 0 else 0  # Sicherstellen, dass Rest nicht negativ wird

                except (ValueError, TypeError) as e:
                    print(
                        f"Fehler bei Konvertierung der Urlaubstage für User {user_id}: {e}. Urlaubstage werden nicht automatisch angepasst.")
                    # Entferne die automatisch berechneten Werte, falls Konvertierung fehlschlägt
                    if 'urlaub_gesamt' in valid_details and valid_details['urlaub_gesamt'] == new_total_vacation:
                        del valid_details['urlaub_gesamt']
                    if 'urlaub_rest' in valid_details:
                        del valid_details['urlaub_rest']
            else:
                print(
                    f"Warnung: Konnte alte Urlaubstage für User {user_id} nicht abrufen. Automatische Anpassung übersprungen.")
                # Entferne die automatisch berechneten Werte
                if 'urlaub_gesamt' in valid_details and valid_details['urlaub_gesamt'] == new_total_vacation:
                    del valid_details['urlaub_gesamt']
                if 'urlaub_rest' in valid_details:
                    del valid_details['urlaub_rest']

        # --- ENDE ANPASSUNG ---

        # Nur fortfahren, wenn noch Felder zum Aktualisieren übrig sind
        if not valid_details:
            return True, "Keine Änderungen zum Speichern vorhanden (nach Berechnungsprüfung)."  # Oder eine passendere Meldung

        fields = ', '.join([f"`{key}` = %s" for key in valid_details])
        values = list(valid_details.values()) + [user_id]
        query = f"UPDATE users SET {fields} WHERE id = %s"
        cursor.execute(query, tuple(values))
        _log_activity(cursor, current_user_id, 'USER_UPDATE', f'Daten für Benutzer-ID {user_id} aktualisiert.')
        conn.commit()
        clear_user_order_cache()
        return True, "Benutzerdaten erfolgreich aktualisiert."
    except mysql.connector.Error as db_err:
        conn.rollback()
        print(f"DB Fehler beim Aktualisieren von User {user_id}: {db_err}")
        return False, f"Datenbankfehler: {db_err}"
    except Exception as e:
        conn.rollback()
        print(f"Allgemeiner Fehler beim Aktualisieren von User {user_id}: {e}")
        # Gib die spezifische Fehlermeldung zurück, die der Nutzer gesehen hat
        return False, f"Fehler beim Aktualisieren der Benutzerdaten: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_user(user_id, current_user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data['vorname']} {user_data['name']}" if user_data else f"ID {user_id}"
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        _log_activity(cursor, current_user_id, 'USER_DELETION', f'Benutzer {user_fullname} (ID: {user_id}) gelöscht.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde gelöscht.')
        conn.commit()
        clear_user_order_cache()
        return True, "Benutzer erfolgreich gelöscht."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Löschen des Benutzers: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- Restliche Funktionen (get_user_role bis update_last_event_date) bleiben unverändert ---

def get_user_role(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        role = cursor.fetchone()
        return role[0] if role else None
    except Exception as e:
        print(f"Fehler beim Abrufen der Benutzerrolle: {e}")
        return None
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def update_user_password(user_id, new_password):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        new_password_hash = hash_password(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s, password_changed = 1 WHERE id = %s",
            (new_password_hash, user_id)
        )
        _log_activity(cursor, user_id, 'PASSWORD_UPDATE', f'Benutzer-ID {user_id} hat das Passwort geändert.')
        conn.commit()
        return True, "Passwort erfolgreich aktualisiert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Aktualisieren des Passworts: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def mark_tutorial_seen(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def check_tutorial_seen(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT has_seen_tutorial FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def set_password_changed_status(user_id, status):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_changed = %s WHERE id = %s", (status, user_id))
        conn.commit()
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def get_password_changed_status(user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_changed FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def update_last_event_date(user_id, event_type, date_str):
    # ... (unverändert) ...
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
        if conn and conn.is_connected(): cursor.close(); conn.close()


# ==============================================================================
# --- FUNKTIONEN FÜR ADMIN-FREISCHALTUNG & ARCHIVIERUNG ---
# ==============================================================================

def get_pending_approval_users():
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
                       SELECT id, vorname, name, entry_date
                       FROM users
                       WHERE is_approved = 0
                         AND is_archived = 0
                       ORDER BY entry_date ASC
                       """)
        users = cursor.fetchall()
        return users
    except Exception as e:
        print(f"Fehler beim Abrufen der ausstehenden Benutzer: {e}")
        return []
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def approve_user(user_id, current_user_id):
    # ... (unverändert) ...
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"
        cursor.execute("UPDATE users SET is_approved = 1 WHERE id = %s", (user_id,))
        _log_activity(cursor, current_user_id, 'USER_APPROVAL', f'Benutzer {user_fullname} wurde freigeschaltet.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde erfolgreich freigeschaltet.')
        conn.commit()
        clear_user_order_cache()
        return True, f"Benutzer {user_fullname} erfolgreich freigeschaltet."
    except Exception as e:
        conn.rollback()
        print(f"Fehler beim Freischalten des Benutzers: {e}")
        return False, f"Fehler beim Freischalten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def archive_user(user_id, current_user_id, archive_date=None):
    """
    Archiviert einen Benutzer (setzt is_archived = 1).
    Wenn archive_date None ist, wird sofort archiviert.
    Wenn archive_date angegeben ist, wird dieses Datum gesetzt.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        # Bestimme den Zeitstempel für die Archivierung
        if archive_date:
            archive_timestamp = archive_date
            log_msg = f'Benutzer {user_fullname} wird zum {archive_date.strftime("%Y-%m-%d")} archiviert.'
            notification_msg = f'Benutzer {user_fullname} wird zum {archive_date.strftime("%Y-%m-%d")} archiviert.'
        else:
            archive_timestamp = datetime.now()
            log_msg = f'Benutzer {user_fullname} wurde sofort archiviert.'
            notification_msg = f'Benutzer {user_fullname} wurde archiviert.'

        cursor.execute("UPDATE users SET is_archived = 1, archived_date = %s WHERE id = %s",
                       (archive_timestamp, user_id))

        _log_activity(cursor, current_user_id, 'USER_ARCHIVE', log_msg)
        _create_admin_notification(cursor, notification_msg)

        conn.commit()
        clear_user_order_cache()
        return True, notification_msg
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Archivieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def unarchive_user(user_id, current_user_id):
    """
    Reaktiviert einen Benutzer.
    Setzt is_archived = 0, archived_date = NULL.
    Setzt activation_date auf NULL, um sofortigen Login zu ermöglichen (wenn approved).
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT vorname, name FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        user_fullname = f"{user_data[0]} {user_data[1]}" if user_data else f"ID {user_id}"

        # NEU: Setze archived_date UND activation_date auf NULL
        cursor.execute("UPDATE users SET is_archived = 0, archived_date = NULL, activation_date = NULL WHERE id = %s",
                       (user_id,))

        _log_activity(cursor, current_user_id, 'USER_UNARCHIVE', f'Benutzer {user_fullname} wurde reaktiviert.')
        _create_admin_notification(cursor, f'Benutzer {user_fullname} wurde reaktiviert.')

        conn.commit()
        clear_user_order_cache()
        return True, f"Benutzer {user_fullname} erfolgreich reaktiviert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Reaktivieren: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- NEUE FUNKTION FÜR BATCH-UPDATE URLAUB ---

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
                diff = new_total - old_total
                new_rest = old_rest + diff

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

# --- ENDE NEU ---