# database/db_core.py
#
# ==============================================================================
# --- 🐞 KORREKTUR: PROXY-IMPORTE (FASSADE) ---
# ==============================================================================
#
# Diese Datei dient NUR NOCH als Fassade, um Abwärtskompatibilität
# für den Rest der Anwendung zu gewährleisten (Regel 1).
# Die ECHTE Logik liegt in db_connection.py und den anderen db_*.py Modulen.

# --- Aus db_connection (NEU) ---
try:
    # Wir importieren das Modul selbst, um dynamisch darauf zugreifen zu können
    from . import db_connection

    # Importieren der Funktionen (diese sind sicher)
    from .db_connection import (
        DB_CONFIG,
        create_connection,
        prewarm_connection_pool,
        close_pool,
        initialize_db
        # db_pool und _db_initialized werden absichtlich NICHT mehr direkt importiert
    )
except ImportError as e:
    print(f"KRITISCHER FEHLER beim Import von db_connection: {e}")
    # Diese sind essenziell, daher bei Fehler laut stoppen
    raise


# --- KORREKTUR: Dynamische Getter-Funktionen statt fehlerhafter Variablen ---
# Diese Funktionen holen IMMER den aktuellen Wert aus db_connection,
# anstatt den veralteten, beim Start importierten Wert zu verwenden.

def get_db_pool():
    """Gibt das aktuelle DB-Pool-Objekt (oder None) zurück."""
    return db_connection.db_pool


def is_db_initialized():
    """Gibt den aktuellen Initialisierungsstatus (True/False) zurück."""
    return db_connection._db_initialized


# --- Aus db_helpers ---
try:
    from .db_helpers import (
        ROLE_HIERARCHY,
        MIN_STAFFING_RULES_CONFIG_KEY,
        REQUEST_LOCKS_CONFIG_KEY,
        ADMIN_MENU_CONFIG_KEY,
        USER_TAB_ORDER_CONFIG_KEY,
        ADMIN_TAB_ORDER_CONFIG_KEY,
        VACATION_RULES_CONFIG_KEY,
        hash_password,
        _log_activity,
        _create_admin_notification,
        get_vacation_days_for_tenure
    )
except ImportError as e:
    print(f"FEHLER beim Re-Import von db_helpers: {e}")

# --- Aus db_config_manager ---
try:
    from .db_config_manager import (
        save_config_json,
        load_config_json,
        clear_config_cache
    )
except ImportError as e:
    print(f"FEHLER beim Re-Import von db_config_manager: {e}")

# --- Aus db_meta_manager ---
try:
    from .db_meta_manager import (
        save_shift_frequency,
        load_shift_frequency,
        reset_shift_frequency,
        save_special_appointment,
        delete_special_appointment,
        get_special_appointments
    )
except ImportError as e:
    print(f"FEHLER beim Re-Import von db_meta_manager: {e}")

# --- Aus db_migration_fixes ---
try:
    from .db_migration_fixes import (
        run_db_fix_approve_all_users,
        run_db_update_is_approved,
        run_db_update_v1,
        run_db_update_add_is_archived,
        run_db_update_add_archived_date,
        run_db_update_activation_date
    )
except ImportError as e:
    print(f"FEHLER beim Re-Import von db_migration_fixes: {e}")