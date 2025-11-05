# database/db_helpers.py
import hashlib
from datetime import datetime, date
from .db_config_manager import load_config_json  # Importiert aus der neuen Datei

# --- NEUER IMPORT für dynamische Rollen ---
# (Wir importieren die Funktion, die wir im letzten Schritt erstellt haben)
try:
    from .db_roles import get_all_roles_details
except ImportError:
    print("WARNUNG: db_roles.py nicht gefunden. Fallback für Hierarchie wird verwendet.")
    get_all_roles_details = None
# --- ENDE NEUER IMPORT ---

# ==============================================================================
# --- KONSTANTEN UND HILFSFUNKTIONEN ---
# ==============================================================================

# --- KORREKTUR: Statische Hierarchie entfernt ---
# ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4} # ENTFERNT
# --- ENDE KORREKTUR ---

# Fallback-Daten, falls die DB-Migration noch nicht erfolgt ist
_FALLBACK_HIERARCHY = {"Gast": 1, "Mitarbeiter": 2, "Admin": 3}


def get_dynamic_role_hierarchy():
    """
    (NEUE FUNKTION)
    Ersetzt die alte statische ROLE_HIERARCHY-Variable.
    Lädt die Hierarchie-Level dynamisch aus der Datenbank.
    Gibt ein Dict im alten Format zurück: {'Admin': 1, 'Mitarbeiter': 2, ...}
    """
    if get_all_roles_details is None:
        return _FALLBACK_HIERARCHY

    try:
        # 1. Ruft die Liste ab: [{'name': 'Admin', 'hierarchy_level': 1}, ...]
        roles_list = get_all_roles_details()

        if not roles_list:
            print("WARNUNG: get_dynamic_role_hierarchy: Keine Rollen von DB empfangen. Nutze Fallback.")
            return _FALLBACK_HIERARCHY

        # 2. Konvertiert in das alte Map-Format: {'Admin': 1, ...}
        roles_map = {role['name']: role['hierarchy_level'] for role in roles_list}
        return roles_map

    except Exception as e:
        print(f"FEHLER bei get_dynamic_role_hierarchy: {e}. Nutze Fallback.")
        return _FALLBACK_HIERARCHY


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