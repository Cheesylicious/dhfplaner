# database/db_helpers.py
import hashlib
from datetime import datetime, date
from .db_config_manager import load_config_json # Importiert aus der neuen Datei

# ==============================================================================
# --- KONSTANTEN UND HILFSFUNKTIONEN ---
# ==============================================================================

ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}
MIN_STAFFING_RULES_CONFIG_KEY = "MIN_STAFFING_RULES"
REQUEST_LOCKS_CONFIG_KEY = "REQUEST_LOCKS"
ADMIN_MENU_CONFIG_KEY = "ADMIN_MENU_CONFIG"
USER_TAB_ORDER_CONFIG_KEY = "USER_TAB_ORDER"
ADMIN_TAB_ORDER_CONFIG_KEY = "ADMIN_TAB_ORDER"
VACATION_RULES_CONFIG_KEY = "VACATION_RULES"


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


def get_vacation_days_for_tenure(entry_date_obj, default_days=30):
    """
    Berechnet den Urlaubsanspruch basierend auf der Betriebszugehörigkeit.
    Nutzt (jetzt gecachtes) load_config_json.
    """
    if not entry_date_obj:
        return default_days
    if isinstance(entry_date_obj, str):
        try:
            entry_date_obj = datetime.strptime(entry_date_obj, '%Y-%m-%d').date()
        except ValueError:
            print(f"Warnung: Ungültiges entry_date-Format: {entry_date_obj}. Verwende Standard-Urlaubstage.")
            return default_days
    elif isinstance(entry_date_obj, datetime):
        entry_date_obj = entry_date_obj.date()
    elif not isinstance(entry_date_obj, date):
        print(f"Warnung: Ungültiger entry_date-Typ: {type(entry_date_obj)}. Verwende Standard-Urlaubstage.")
        return default_days

    # Nutzt die gecachte Ladefunktion aus db_config_manager
    rules_config = load_config_json(VACATION_RULES_CONFIG_KEY)
    if not rules_config or not isinstance(rules_config, list):
        return default_days

    try:
        rules = sorted(
            [{"years": int(r["years"]), "days": int(r["days"])} for r in rules_config],
            key=lambda x: x["years"],
            reverse=True
        )
    except (ValueError, KeyError, TypeError) as e:
        print(f"Fehler beim Parsen der Urlaubsregeln: {e}. Verwende Standard-Urlaubstage.")
        return default_days

    today = date.today()
    tenure_years = today.year - entry_date_obj.year
    if (today.month, today.day) < (entry_date_obj.month, entry_date_obj.day):
        tenure_years -= 1

    for rule in rules:
        if tenure_years >= rule["years"]:
            return rule["days"]

    return default_days