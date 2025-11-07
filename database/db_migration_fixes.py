# database/db_migration_fixes.py
from .db_connection import create_connection
import traceback


# (Alle Ihre vorhandenen Migrationsfunktionen wie run_db_fix_approve_all_users, etc. bleiben hier)
# ...

def run_db_fix_approve_all_users():
    """Setzt alle 'is_approved' auf 1 (Nur für alte DBs)"""
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_approved = 1 WHERE is_approved = 0")
        conn.commit()
        return True, f"{cursor.rowcount} Benutzer wurden auf 'freigegeben' gesetzt."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


def run_db_update_is_approved():
    """Fügt die Spalte 'is_approved' zur 'users'-Tabelle hinzu, falls nicht vorhanden."""
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."
    try:
        cursor = conn.cursor()
        # Prüfen, ob die Spalte existiert
        cursor.execute("SHOW COLUMNS FROM users LIKE 'is_approved'")
        result = cursor.fetchone()
        if result:
            return True, "Spalte 'is_approved' existiert bereits."

        # Spalte hinzufügen
        cursor.execute("ALTER TABLE users ADD COLUMN is_approved TINYINT(1) DEFAULT 0")
        conn.commit()
        return True, "Spalte 'is_approved' erfolgreich hinzugefügt."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


def run_db_update_v1():
    """Fügt die Spalte 'approved_by' zur 'users'-Tabelle hinzu, falls nicht vorhanden."""
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."
    try:
        cursor = conn.cursor()
        # Prüfen, ob die Spalte existiert
        cursor.execute("SHOW COLUMNS FROM users LIKE 'approved_by'")
        result = cursor.fetchone()
        if result:
            return True, "Spalte 'approved_by' existiert bereits."

        # Spalte hinzufügen
        cursor.execute("ALTER TABLE users ADD COLUMN approved_by INT DEFAULT NULL")
        conn.commit()
        return True, "Spalte 'approved_by' erfolgreich hinzugefügt."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


def run_db_update_add_is_archived():
    """Fügt 'is_archived' zur 'users'-Tabelle hinzu."""
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM users LIKE 'is_archived'")
        if cursor.fetchone():
            return True, "Spalte 'is_archived' existiert bereits."

        cursor.execute("ALTER TABLE users ADD COLUMN is_archived TINYINT(1) DEFAULT 0")
        conn.commit()
        return True, "Spalte 'is_archived' erfolgreich hinzugefügt."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


def run_db_update_add_archived_date():
    """Fügt 'archived_date' zur 'users'-Tabelle hinzu."""
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM users LIKE 'archived_date'")
        if cursor.fetchone():
            return True, "Spalte 'archived_date' existiert bereits."

        cursor.execute("ALTER TABLE users ADD COLUMN archived_date DATETIME DEFAULT NULL")
        conn.commit()
        return True, "Spalte 'archived_date' erfolgreich hinzugefügt."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


def run_db_update_activation_date():
    """Fügt 'activation_date' zur 'users'-Tabelle hinzu."""
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM users LIKE 'activation_date'")
        if cursor.fetchone():
            return True, "Spalte 'activation_date' existiert bereits."

        cursor.execute("ALTER TABLE users ADD COLUMN activation_date DATE DEFAULT NULL")
        conn.commit()
        return True, "Spalte 'activation_date' erfolgreich hinzugefügt."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


# --- NEUE FUNKTION (FÜR BERECHTIGUNGEN) ---
def run_db_migration_add_role_permissions():
    """
    Fügt die Spalten 'hierarchy_level' und 'permissions' zur 'roles'-Tabelle hinzu,
    falls sie noch nicht existieren.
    """
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."

    try:
        cursor = conn.cursor()
        messages = []

        # 1. Prüfen und Hinzufügen von 'hierarchy_level'
        cursor.execute("SHOW COLUMNS FROM `roles` LIKE 'hierarchy_level'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE `roles` ADD COLUMN `hierarchy_level` INT DEFAULT 99")
            messages.append("'hierarchy_level' Spalte hinzugefügt.")
        else:
            messages.append("'hierarchy_level' existiert bereits.")

        # 2. Prüfen und Hinzufügen von 'permissions'
        cursor.execute("SHOW COLUMNS FROM `roles` LIKE 'permissions'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE `roles` ADD COLUMN `permissions` TEXT DEFAULT NULL")
            messages.append("'permissions' Spalte hinzugefügt.")
        else:
            messages.append("'permissions' existiert bereits.")

        conn.commit()
        return True, "Rollen-Migration erfolgreich. " + " ".join(messages)

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return False, f"Fehler bei Rollen-Migration: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()


# --- ENDE NEUE FUNKTION ---

# --- NEUE FUNKTION (FÜR FENSTERTYP) ---
def run_db_migration_add_role_window_type():
    """
    Fügt die Spalte 'window_type' zur 'roles'-Tabelle hinzu.
    Setzt 'admin' für Admin (ID 1) und 'user' für alle anderen als Standard.
    """
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."

    try:
        cursor = conn.cursor()
        messages = []

        # 1. Prüfen und Hinzufügen von 'window_type'
        cursor.execute("SHOW COLUMNS FROM `roles` LIKE 'window_type'")
        if not cursor.fetchone():
            # Standard 'user' für alle
            cursor.execute("ALTER TABLE `roles` ADD COLUMN `window_type` VARCHAR(20) DEFAULT 'user'")
            messages.append("'window_type' Spalte hinzugefügt.")

            # Admins (ID 1) und SuperAdmins (ID 4, falls vorhanden) auf 'admin' setzen
            # (IDs basierend auf der alten statischen ROLE_HIERARCHY)
            cursor.execute("UPDATE `roles` SET `window_type` = 'admin' WHERE `id` IN (1, 4)")
            messages.append(f"{cursor.rowcount} Master-Rollen auf 'admin' gesetzt.")
        else:
            messages.append("'window_type' existiert bereits.")

        conn.commit()
        return True, "Fenstertyp-Migration erfolgreich. " + " ".join(messages)

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return False, f"Fehler bei Fenstertyp-Migration: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()
# --- ENDE NEUE FUNKTION ---

# --- INNOVATION (Regel 2 & 4): NEUE FUNKTION FÜR ROLLEN-FARBEN ---
def run_db_migration_add_role_color():
    """
    (INNOVATION Regel 2 & 4)
    Fügt die Spalte 'color_hex' zur 'roles'-Tabelle hinzu,
    um die UI-Farbe für Rollen zu speichern.
    Verwendet die gleiche "SHOW COLUMNS"-Logik wie die anderen Funktionen in dieser Datei.
    """
    conn = create_connection()
    if not conn:
        return False, "Keine DB-Verbindung."

    try:
        cursor = conn.cursor()
        messages = []

        # 1. Prüfen und Hinzufügen von 'color_hex'
        cursor.execute("SHOW COLUMNS FROM `roles` LIKE 'color_hex'")
        if not cursor.fetchone():
            # Standard Hellgrün (kann hier geändert werden)
            cursor.execute("ALTER TABLE `roles` ADD COLUMN `color_hex` VARCHAR(7) DEFAULT '#E8F5E9'")
            messages.append("'color_hex' Spalte hinzugefügt.")
        else:
            messages.append("'color_hex' existiert bereits.")

        conn.commit()
        return True, "Rollen-Farb-Migration erfolgreich. " + " ".join(messages)

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return False, f"Fehler bei Rollen-Farb-Migration: {e}"
    finally:
        if conn and conn.is_connected():
            conn.close()
# --- ENDE INNOVATION ---