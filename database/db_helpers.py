# database/db_helpers.py
# BEREINIGT: Urlaubslogik wurde nach db_vacation_rules.py ausgelagert.

import hashlib
from datetime import datetime

# ENTFERNT: from .db_config_manager import load_config_json (wird nicht mehr benötigt)
# ENTFERNT: 'date' (wird nicht mehr benötigt)

# ==============================================================================
# --- KONSTANTEN UND HILFSFUNKTIONEN ---
# ==============================================================================

ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}
MIN_STAFFING_RULES_CONFIG_KEY = "MIN_STAFFING_RULES"
REQUEST_LOCKS_CONFIG_KEY = "REQUEST_LOCKS"
ADMIN_MENU_CONFIG_KEY = "ADMIN_MENU_CONFIG"
USER_TAB_ORDER_CONFIG_KEY = "USER_TAB_ORDER"
ADMIN_TAB_ORDER_CONFIG_KEY = "ADMIN_TAB_ORDER"


# ENTFERNT: VACATION_RULES_CONFIG_KEY (nach db_vacation_rules.py verschoben)


def hash_password(password):
    """Hasht ein Passwort."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def _log_activity(cursor, user_id, action_type, details):
    """
    Protokolliert eine Benutzeraktion.
    Nimmt einen *existierenden* Cursor entgegen, um Transaktionen zu ermöglichen.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (%s, %s, %s, %s)",
                   (timestamp, user_id, action_type, details))


def _create_admin_notification(cursor, message):
    """
    Erstellt eine Admin-Benachrichtigung.
    Nimmt einen *existierenden* Cursor entgegen, um Transaktionen zu ermöglichen.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO admin_notifications (message, timestamp) VALUES (%s, %s)", (message, timestamp))


# ENTFERNT: get_vacation_days_for_tenure (nach db_vacation_rules.py verschoben)


# ==============================================================================
# --- RE-IMPORT FÜR ABWÄRTSKOMPATIBILITÄT ---
# ==============================================================================
import warnings

try:
    # Importiert die ausgelagerte Funktion und Konstante zurück in den Namespace
    from .db_vacation_rules import (
        VACATION_RULES_CONFIG_KEY,
        get_vacation_days_for_tenure
    )
except ImportError as e:
    warnings.warn(f"Konnte db_vacation_rules nicht importieren: {e}")

    # Fallback-Definitionen, falls der Import fehlschlägt
    VACATION_RULES_CONFIG_KEY = "VACATION_RULES"


    def get_vacation_days_for_tenure(entry_date_obj, default_days=30):
        print(f"FEHLER: db_vacation_rules.py fehlt! Fallback auf {default_days} Tage.")
        return default_days