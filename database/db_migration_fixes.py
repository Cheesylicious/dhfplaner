# database/db_migration_fixes.py
import mysql.connector
from .db_connection import create_connection, DB_CONFIG

# KORREKTUR: Importiert die Helfer aus der neuen, sauberen Datei
from .db_schema_helpers import _add_column_if_not_exists


# ==============================================================================
# --- DB-FIX-FUNKTIONEN (unverändert) ---
# ==============================================================================

def run_db_fix_approve_all_users():
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_approved = 1 WHERE is_approved = 0")
        updated_rows = cursor.rowcount
        conn.commit()
        return True, f"{updated_rows} bestehende Benutzer wurden erfolgreich freigeschaltet."
    except mysql.connector.Error as e:
        conn.rollback();
        return False, f"Ein Datenbankfehler ist aufgetreten: {e}"
    except Exception as e:
        conn.rollback();
        return False, f"Ein unerwarteter Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_is_approved():
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        db_name = DB_CONFIG.get('database') if DB_CONFIG else None
        if not db_name: raise ValueError("DB-Name nicht gefunden")

        _add_column_if_not_exists(cursor, db_name, "users", "is_approved", "TINYINT(1) DEFAULT 0")
        conn.commit()
        return True, "DB-Update (is_approved Spalte) erfolgreich."
    except (mysql.connector.Error, ValueError) as e:
        conn.rollback();
        return False, f"Ein Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_v1():
    conn = create_connection()
    if not conn: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        db_name = DB_CONFIG.get('database') if DB_CONFIG else None
        if not db_name: raise ValueError("DB-Name nicht gefunden")

        _add_column_if_not_exists(cursor, db_name, "users", "last_seen", "DATETIME DEFAULT NULL")
        conn.commit()
        return True, "DB-Update für Chat erfolgreich."
    except (mysql.connector.Error, ValueError) as e:
        conn.rollback();
        return False, f"Ein Fehler ist aufgetreten: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_add_is_archived():
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        db_name = DB_CONFIG.get('database') if DB_CONFIG else None
        if not db_name: raise ValueError("DB-Name nicht gefunden")

        _add_column_if_not_exists(cursor, db_name, "users", "is_archived", "TINYINT(1) DEFAULT 0")
        conn.commit()
        return True, "DB-Update (is_archived Spalte) erfolgreich."
    except Exception as e:
        conn.rollback();
        print(f"Fehler: {e}");
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_add_archived_date():
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        db_name = DB_CONFIG.get('database') if DB_CONFIG else None
        if not db_name: raise ValueError("DB-Name nicht gefunden")

        _add_column_if_not_exists(cursor, db_name, "users", "archived_date", "DATETIME DEFAULT NULL")
        conn.commit()
        return True, "DB-Update (archived_date Spalte) erfolgreich."
    except Exception as e:
        conn.rollback();
        print(f"Fehler: {e}");
        return False, f"Fehler: {e}"
    finally:
        if conn and conn.is_connected(): cursor.close(); conn.close()


def run_db_update_activation_date():
    """
    Fügt die Spalte 'activation_date' zur 'users'-Tabelle hinzu,
    um zukünftige Aktivierungen zu steuern.
    """
    conn = create_connection()
    if conn is None:
        return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        db_name = DB_CONFIG.get('database') if DB_CONFIG else None
        if not db_name: raise ValueError("DB-Name nicht gefunden")

        _add_column_if_not_exists(cursor, db_name, "users", "activation_date",
                                  "DATETIME NULL DEFAULT NULL AFTER entry_date")
        conn.commit()
        return True, "Datenbank-Update für 'activation_date' erfolgreich durchgeführt."
    except mysql.connector.Error as e:
        conn.rollback()
        if e.errno == 1060:  # Duplicate column name
            return True, "Spalte 'activation_date' existiert bereits. Keine Aktion erforderlich."
        print(f"Fehler beim Hinzufügen von activation_date: {e}")
        return False, f"Fehler beim Update: {e}"
    except Exception as e:
        conn.rollback()
        print(f"Allgemeiner Fehler beim Hinzufügen von activation_date: {e}")
        return False, f"Allgemeiner Fehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()