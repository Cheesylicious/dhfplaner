# database/db_roles.py
import json
from .db_connection import create_connection

# Liste aller Admin-Tabs (aus admin_tab_manager.py)
# Dies ist die Definitionshoheit für Berechtigungen.
ALL_ADMIN_TABS = [
    "Schichtplan", "Mitarbeiter", "Diensthunde", "Schichtarten",
    "Aufgaben", "Wunschanfragen", "Urlaubsanträge", "Antragssperre",
    "Bug-Reports", "Protokoll", "Wartung", "Einstellungen",
    "Chat", "Teilnahmen", "Passwort-Resets"
]


def get_all_roles_details():
    """
    Ruft alle Rollen inkl. Hierarchie, Berechtigungen, HAUPTFENSTER
    UND FARBE ab. (INNOVATION Regel 2)
    KORRIGIERT: Verwendet 'role_name' (gemäß DB-Schema).
    """
    conn = create_connection()
    if not conn:
        print("Fehler: Konnte keine DB-Verbindung für get_all_roles_details herstellen.")
        return []

    try:
        cursor = conn.cursor(dictionary=True)

        # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
        # --- INNOVATION (Regel 2): 'color_hex' hinzugefügt ---
        cursor.execute(
            "SELECT `id`, `role_name`, `hierarchy_level`, `permissions`, `main_window`, `color_hex` "
            "FROM `roles` "
            "ORDER BY `hierarchy_level` ASC, `role_name` COLLATE utf8mb4_unicode_ci"
        )
        # --- ENDE KORREKTUR & INNOVATION ---

        roles_from_db = cursor.fetchall()

        roles_for_gui = []
        for role in roles_from_db:
            permissions_dict = {}
            if role.get('permissions'):
                try:
                    permissions_dict = json.loads(role['permissions'])
                except json.JSONDecodeError:
                    print(f"Warnung: Ungültiges JSON in Berechtigungen für Rolle ID {role['id']}")

            roles_for_gui.append({
                "id": role['id'],
                # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
                "name": role['role_name'],
                "hierarchy_level": role.get('hierarchy_level', 99),
                "permissions": permissions_dict,
                # (main_window ist korrekt)
                "main_window": role.get('main_window', 'main_user_window'),
                # --- INNOVATION (Regel 2): Farbe aus DB lesen, Fallback Hellgrün ---
                "color": role.get('color_hex', '#E8F5E9')
                # --- ENDE INNOVATION ---
            })

        return roles_for_gui

    except Exception as e:
        if "Unknown column" in str(e) or "no such column" in str(e):
            print(f"DB FEHLER: {e}. Haben Sie die Migrationen (Schritt 1) durchgeführt? (ALTER TABLE ... ADD COLUMN color_hex)")
            # --- KORREKTUR (Fehlerbehebung): Fallback ruft sich selbst auf (korrekt) ---
            return get_all_roles_legacy()  # Fallback
            # --- ENDE KORREKTUR ---

        print(f"Fehler beim Abrufen aller Rollendetails: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_roles_legacy():
    """
    Fallback, falls Migration (Schema-Änderungen) noch nicht erfolgt ist.
    KORRIGIERT: Verwendet 'role_name'.
    """
    print("Führe Fallback aus: get_all_roles_legacy (nur Namen)")
    conn = create_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
        cursor.execute("SELECT `id`, `role_name` FROM `roles` ORDER BY `role_name` COLLATE utf8mb4_unicode_ci")
        roles_from_db = cursor.fetchall()

        admin_ids = [1, 2]  # Annahme: Admin=1, SuperAdmin=2 (oder [1, 4])

        return [{
            "id": role['id'],
            # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
            "name": role['role_name'],
            "hierarchy_level": 99,
            "permissions": {},
            "main_window": 'main_admin_window' if role['id'] in admin_ids else 'main_user_window',
            # --- INNOVATION (Regel 2): Fallback-Farbe ---
            "color": "#E8F5E9"
        } for role in roles_from_db]

    except Exception as e:
        # Dieser Block sollte jetzt überflüssig sein, da wir direkt 'role_name' abfragen
        print(f"Fehler im Legacy-Rollen-Fallback: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_role(role_name_input):
    """
    Erstellt eine neue Rolle mit Standard-Hierarchie (99),
    leeren Berechtigungen, Standard-Hauptfenster ('main_user_window')
    UND Standardfarbe (INNOVATION Regel 2).
    KORRIGIERT: Verwendet 'role_name'.
    """
    if not role_name_input or len(role_name_input.strip()) == 0:
        print("Fehler: Rollenname darf nicht leer sein.")
        return False

    conn = create_connection()
    if not conn:
        print("Fehler: Konnte keine DB-Verbindung für create_role herstellen.")
        return False

    try:
        cursor = conn.cursor()

        default_permissions = json.dumps({})
        default_hierarchy = 99
        default_window = 'main_user_window'
        # --- INNOVATION (Regel 2): Standardfarbe beim Erstellen ---
        default_color = '#E8F5E9'  # Hellgrün
        # --- ENDE INNOVATION ---

        # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
        # --- INNOVATION (Regel 2): 'color_hex' hinzugefügt ---
        cursor.execute(
            "INSERT INTO `roles` (`role_name`, `hierarchy_level`, `permissions`, `main_window`, `color_hex`) VALUES (%s, %s, %s, %s, %s)",
            (role_name_input.strip(), default_hierarchy, default_permissions, default_window, default_color)
        )
        # --- ENDE KORREKTUR & INNOVATION ---

        conn.commit()
        return True
    except Exception as e:
        print(f"Fehler beim Erstellen der Rolle: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def delete_role(role_id):
    """
    Löscht eine Rolle anhand ihrer ID.
    KORRIGIERT: Verwendet 'role_name'.
    """
    if role_id in [1, 2, 3, 4]:
        print("Fehler: Standardrollen (Admin, Mitarbeiter, Gast, SuperAdmin) können nicht gelöscht werden.")
        return False, "Standardrollen können nicht gelöscht werden."

    conn = create_connection()
    if not conn: return False, "DB-Verbindungsfehler."

    try:
        cursor = conn.cursor()

        # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
        # Hole den 'role_name' der Rolle (z.B. "Admin") aus der 'roles'-Tabelle
        cursor.execute("SELECT `role_name` FROM `roles` WHERE `id` = %s", (role_id,))
        role_result = cursor.fetchone()

        if not role_result:
            return False, "Rolle mit ID nicht gefunden."

        role_name_to_delete = role_result[0]

        # Prüfen, ob das 'role' (ENUM) in 'users' noch diesen Namen verwendet
        cursor.execute("SELECT COUNT(*) FROM `users` WHERE `role` = %s", (role_name_to_delete,))
        user_count = cursor.fetchone()[0]
        # --- ENDE KORREKTUR ---

        if user_count > 0:
            msg = f"{user_count} Benutzer haben diese Rolle noch (in users.role). Löschen nicht möglich."
            return False, msg

        cursor.execute("DELETE FROM `roles` WHERE `id` = %s", (role_id,))
        conn.commit()

        return (True, "Rolle gelöscht.") if cursor.rowcount > 0 else (False, "Rolle mit ID nicht gefunden.")

    except Exception as e:
        msg = f"Fehler beim Löschen der Rolle: {e}"
        print(msg)
        conn.rollback()
        return False, msg
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_roles_details(roles_data_list):
    """
    Speichert die komplette Hierarchie, Berechtigungen, HAUPTFENSTER
    UND FARBE (INNOVATION Regel 2).
    """
    conn = create_connection()
    if not conn:
        return False, "DB-Verbindungsfehler."

    try:
        cursor = conn.cursor()

        update_queries = []

        for index, role_data in enumerate(roles_data_list):
            role_id = role_data['id']
            new_level = index + 1
            permissions_json = json.dumps(role_data.get('permissions', {}))
            main_window = role_data.get('main_window', 'main_user_window')
            # --- INNOVATION (Regel 2): Farbe mitspeichern ---
            color_hex = role_data.get('color', '#E8F5E9')
            # --- ENDE INNOVATION ---

            update_queries.append(
                # --- INNOVATION (Regel 2): color_hex hinzugefügt ---
                (new_level, permissions_json, main_window, color_hex, role_id)
            )

        cursor.executemany(
            # --- INNOVATION (Regel 2): color_hex hinzugefügt ---
            "UPDATE `roles` SET `hierarchy_level` = %s, `permissions` = %s, `main_window` = %s, `color_hex` = %s WHERE `id` = %s",
            update_queries
        )
        # --- ENDE INNOVATION ---

        conn.commit()
        return True, "Hierarchie, Berechtigungen und Farben gespeichert."

    except Exception as e:
        msg = f"Fehler beim Speichern der Rollendetails: {e}"
        print(msg)
        conn.rollback()
        return False, msg
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_main_window_for_role(role_name):
    """
    Ruft effizient das zugewiesene Hauptfenster für einen bestimmten Rollennamen ab.
    KORRIGIERT: Verwendet 'role_name'.
    """
    conn = create_connection()
    if not conn:
        print(f"Fehler: Konnte keine DB-Verbindung für get_main_window_for_role (Rolle: {role_name}) herstellen.")
        return 'main_admin_window' if role_name in ["Admin", "SuperAdmin"] else 'main_user_window'

    try:
        cursor = conn.cursor(dictionary=True)

        # --- KORREKTUR (Fehlerbehebung): 'name' -> 'role_name' ---
        cursor.execute(
            "SELECT `main_window` FROM `roles` WHERE `role_name` = %s",
            (role_name,)
        )
        # --- ENDE KORREKTUR ---

        result = cursor.fetchone()

        if result and result.get('main_window'):
            return result['main_window']
        else:
            print(
                f"Warnung: Kein 'main_window' in Tabelle 'roles' für Rolle '{role_name}' gefunden. Verwende Fallback.")
            return 'main_admin_window' if role_name in ["Admin", "SuperAdmin"] else 'main_user_window'

    except Exception as e:
        print(f"Fehler beim Abrufen des Hauptfensters für Rolle '{role_name}': {e}")
        return 'main_admin_window' if role_name in ["Admin", "SuperAdmin"] else 'main_user_window'
    finally:
        if conn and conn.is_connected():
            conn.close()