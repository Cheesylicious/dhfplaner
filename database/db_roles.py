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
    Ruft alle Rollen inkl. Hierarchie, Berechtigungen UND FENSTERTYP ab.
    """
    conn = create_connection()
    if not conn:
        print("Fehler: Konnte keine DB-Verbindung für get_all_roles_details herstellen.")
        return []

    try:
        cursor = conn.cursor(dictionary=True)

        # --- KORREKTUR: `window_type` hinzugefügt ---
        cursor.execute(
            "SELECT `id`, `role_name`, `hierarchy_level`, `permissions`, `window_type` "
            "FROM `roles` "
            "ORDER BY `hierarchy_level` ASC, `role_name` COLLATE utf8mb4_unicode_ci"
        )
        # --- ENDE KORREKTUR ---

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
                "name": role['role_name'],
                "hierarchy_level": role.get('hierarchy_level', 99),
                "permissions": permissions_dict,
                "window_type": role.get('window_type', 'user')  # NEU
            })

        return roles_for_gui

    except Exception as e:
        if "Unknown column" in str(e):
            print(f"DB FEHLER: {e}. Haben Sie die Migrationen (hierarchy, permissions, window_type) durchgeführt?")
            return get_all_roles_legacy()  # Fallback

        print(f"Fehler beim Abrufen aller Rollendetails: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_roles_legacy():
    """Fallback, falls Migration noch nicht erfolgt ist."""
    print("Führe Fallback aus: get_all_roles_legacy (nur Namen)")
    conn = create_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT `id`, `role_name` FROM `roles` ORDER BY `role_name` COLLATE utf8mb4_unicode_ci")
        roles_from_db = cursor.fetchall()
        return [{
            "id": role['id'],
            "name": role['role_name'],
            "hierarchy_level": 99,
            "permissions": {},
            "window_type": 'admin' if role['id'] in [1, 4] else 'user'  # Fallback-Logik
        } for role in roles_from_db]
    except Exception as e:
        print(f"Fehler im Legacy-Rollen-Fallback: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def create_role(role_name_input):
    """
    Erstellt eine neue Rolle mit Standard-Hierarchie (99),
    leeren Berechtigungen und Standard-Fenstertyp ('user').
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
        default_window_type = 'user'  # NEU

        # --- KORREKTUR: `window_type` beim Erstellen hinzugefügt ---
        cursor.execute(
            "INSERT INTO `roles` (`role_name`, `hierarchy_level`, `permissions`, `window_type`) VALUES (%s, %s, %s, %s)",
            (role_name_input.strip(), default_hierarchy, default_permissions, default_window_type)
        )
        # --- ENDE KORREKTUR ---

        conn.commit()
        return True
    except Exception as e:
        print(f"Fehler beim Erstellen der Rolle: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


# (delete_role bleibt unverändert)
def delete_role(role_id):
    """
    Löscht eine Rolle anhand ihrer ID.
    WICHTIG: Standardrollen (Admin, Mitarbeiter, Gast) werden blockiert.
    """
    # Feste IDs (Annahme basierend auf db_schema.py: 1=Admin, 2=Mitarbeiter, 3=Gast, 4=SuperAdmin)
    if role_id in [1, 2, 3, 4]:
        print("Fehler: Standardrollen (Admin, Mitarbeiter, Gast, SuperAdmin) können nicht gelöscht werden.")
        return False, "Standardrollen können nicht gelöscht werden."

    conn = create_connection()
    if not conn: return False, "DB-Verbindungsfehler."

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM `users` WHERE `role_id` = %s", (role_id,))
        user_count = cursor.fetchone()[0]

        if user_count > 0:
            msg = f"{user_count} Benutzer haben diese Rolle noch. Löschen nicht möglich."
            return False, msg

        cursor.execute("DELETE FROM `roles` WHERE `id` = %s", (role_id,))
        conn.commit()

        return (True, "Rolle gelöscht.") if cursor.rowcount > 0 else (False, "Rolle mit ID nicht gefunden.")

    except Exception as e:
        msg = f"Fehler beim Löschen der Rolle: {e}"
        conn.rollback()
        return False, msg
    finally:
        if conn and conn.is_connected():
            conn.close()


def save_roles_details(roles_data_list):
    """
    Speichert die komplette Hierarchie, Berechtigungen UND FENSTERTYP.
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

            # --- NEU: Fenstertyp holen ---
            window_type = role_data.get('window_type', 'user')
            # --- ENDE NEU ---

            update_queries.append(
                (new_level, permissions_json, window_type, role_id)  # NEU
            )

        # --- KORREKTUR: `window_type` im UPDATE hinzugefügt ---
        cursor.executemany(
            "UPDATE `roles` SET `hierarchy_level` = %s, `permissions` = %s, `window_type` = %s WHERE `id` = %s",
            update_queries
        )
        # --- ENDE KORREKTUR ---

        conn.commit()
        return True, "Hierarchie und Berechtigungen gespeichert."

    except Exception as e:
        msg = f"Fehler beim Speichern der Rollendetails: {e}"
        print(msg)
        conn.rollback()
        return False, msg
    finally:
        if conn and conn.is_connected():
            conn.close()