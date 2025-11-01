# database/db_vacation_rules.py
# KORRIGIERTE VERSION: Nutzt load_config_json und save_config_json

# KORREKTUR: Importiert die korrekten Funktionsnamen aus db_config_manager
from .db_config_manager import load_config_json, save_config_json
from datetime import date, datetime
import json
import warnings

# Versuch, dateutil für präzise Dienstjahrberechnung zu importieren
try:
    from dateutil.relativedelta import relativedelta

    _DATEUTIL_AVAILABLE = True
except ImportError:
    _DATEUTIL_AVAILABLE = False
    warnings.warn(
        "Modul 'python-dateutil' nicht gefunden. Urlaubsanspruchsberechnung ist ungenauer (nutzt reinen Jahresvergleich).")

# Schlüssel für die Speicherung der Regeln in der DB-Konfiguration
VACATION_RULES_CONFIG_KEY = "VACATION_TENURE_RULES"

# Standardregeln (Falls nichts in der DB gespeichert ist)
DEFAULT_VACATION_RULES = [
    {"years_min": 0, "years_max": 4, "days": 30},
    {"years_min": 5, "years_max": 9, "days": 31},
    {"years_min": 10, "years_max": 14, "days": 32},
    {"years_min": 15, "years_max": 99, "days": 33}
]


def _parse_rules_from_json(rules_json, default_rules):
    """
    Versucht, Regeln aus einem JSON-String zu parsen.
    Gibt bei Erfolg die geparste Liste zurück, sonst die Standardregeln.
    """
    if not rules_json:
        return default_rules

    try:
        rules_list = json.loads(rules_json)
        if (isinstance(rules_list, list) and all(isinstance(item, dict) for item in rules_list)):
            rules_list.sort(key=lambda x: x.get('years_min', 0))
            return rules_list
        else:
            print(
                f"Warnung: Gespeicherte Urlaubsregeln sind kein gültiges Listenformat. Verwende Standards. Inhalt: {rules_json}")
            return default_rules
    except json.JSONDecodeError as e:
        print(f"Fehler beim Parsen der Urlaubsregeln: {e}. Verwende Standards.")
        return default_rules
    except Exception as e:
        print(f"Unerwarteter Fehler beim Verarbeiten der Urlaubsregeln: {e}. Verwende Standards.")
        return default_rules


def get_vacation_rules():
    """
    Holt die Urlaubsanspruchsregeln (Dienstzugehörigkeit) aus der DB.
    """
    # KORREKTUR: Verwendet load_config_json
    rules_json_str = load_config_json(
        VACATION_RULES_CONFIG_KEY)  # load_config_json gibt bereits das geparste Dict/Liste zurück

    # KORREKTUR 2: Da load_config_json bereits parst, prüfen wir den Typ
    if isinstance(rules_json_str, list):
        # Wenn es bereits eine Liste ist (aus dem Cache oder DB)
        rules_json_str.sort(key=lambda x: x.get('years_min', 0))
        return rules_json_str
    elif isinstance(rules_json_str, str):
        # Wenn es ein String ist (sollte durch load_config_json nicht passieren, aber sicher ist sicher)
        return _parse_rules_from_json(rules_json_str, DEFAULT_VACATION_RULES)
    elif rules_json_str is None:
        # Nichts in der DB gefunden
        return DEFAULT_VACATION_RULES
    else:
        # Unerwarteter Typ
        print(f"Warnung: Unerwarteter Typ für Urlaubsregeln empfangen: {type(rules_json_str)}. Verwende Standards.")
        return DEFAULT_VACATION_RULES


def save_vacation_rules(rules_list):
    """
    Speichert die Urlaubsanspruchsregeln (Liste von Dictionaries) als JSON in der DB.
    """
    try:
        rules_list.sort(key=lambda x: x.get('years_min', 0))
        # KORREKTUR: Verwendet save_config_json (erwartet ein Dict/Liste)
        success = save_config_json(VACATION_RULES_CONFIG_KEY, rules_list)
        if success:
            return True, "Regeln erfolgreich gespeichert."
        else:
            return False, "Fehler beim Speichern der Regeln (save_config_json fehlgeschlagen)."
    except Exception as e:
        return False, f"Fehler beim Speichern der Regeln: {e}"


def get_vacation_days_for_tenure(entry_date_str_or_obj, default_days=30):
    """
    Berechnet den Urlaubsanspruch basierend auf der Dienstzugehörigkeit (entry_date).
    Nutzt die Regeln aus der Datenbank (via get_vacation_rules).
    """

    # 1. Eintrittsdatum validieren und parsen
    entry_date = None
    if isinstance(entry_date_str_or_obj, date):
        entry_date = entry_date_str_or_obj
    elif isinstance(entry_date_str_or_obj, str):
        try:
            entry_date = datetime.strptime(entry_date_str_or_obj, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    elif isinstance(entry_date_str_or_obj, datetime):
        entry_date = entry_date_str_or_obj.date()

    if entry_date is None:
        return default_days

    # 2. Dienstjahre berechnen
    today = date.today()
    tenure = 0

    try:
        if _DATEUTIL_AVAILABLE:
            tenure = relativedelta(today, entry_date).years
        else:
            tenure = today.year - entry_date.year
            if (today.month, today.day) < (entry_date.month, entry_date.day):
                tenure -= 1

    except Exception as e:
        print(f"Fehler bei Berechnung der Dienstjahre: {e}. Verwende Standardanspruch ({default_days}).")
        return default_days

    # 3. Regeln abrufen und anwenden
    rules = get_vacation_rules()

    for rule in rules:
        try:
            min_y = int(rule.get("years_min", 0))
            max_y = int(rule.get("years_max", 99))
            days = int(rule.get("days", default_days))

            if min_y <= tenure <= max_y:
                return days

        except (ValueError, TypeError):
            print(f"Warnung: Ungültige Urlaubsregel ignoriert: {rule}")
            continue

    return rules[0].get('days', default_days) if rules else default_days