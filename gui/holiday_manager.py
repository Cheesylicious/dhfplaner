# gui/holiday_manager.py
import os
import json
from datetime import date, datetime
from database.db_core import create_connection, save_config_json, load_config_json
import mysql.connector

# KORREKTUR: Cache zurück in den globalen Scope (wie im Original)
# Speichert Feiertage pro Jahr: {2024: {"2024-01-01": "Neujahr", ...}, 2025: {...}}
_holidays_cache = {}
# ---------------------------------

# Der Dateiname der alten JSON-Datei (nur für Migration)
HOLIDAY_JSON_FILE = 'holidays.json'


class HolidayManager:
    """
    Verwaltet Feiertage durch Laden und Speichern in der Datenbank (config_storage).
    KORREKTUR: Verwendet nur noch @staticmethods (gemäß Original-Design),
    um Kompatibilität mit event_manager.py zu wahren (Regel 1).
    """

    CONFIG_KEY = "HOLIDAYS_NEW"

    @staticmethod
    def _migrate_json_to_db():
        """
        Versucht, die alte holidays.json-Datei zu lesen und in die Datenbank
        zu migrieren. (Wieder Static)
        """
        print(f"[Migration] Prüfe auf alte {HOLIDAY_JSON_FILE}...")
        all_holidays = {}

        # Pfad relativ zu dieser Datei finden
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, HOLIDAY_JSON_FILE)

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    all_holidays = json.load(f)
                print(f"[Migration] Alte {HOLIDAY_JSON_FILE} gefunden. Migriere nach DB...")

                # Ruft die globale DB-Funktion auf
                if save_config_json(HolidayManager.CONFIG_KEY, all_holidays):
                    print(f"[Migration] Erfolgreich zu DB-Key '{HolidayManager.CONFIG_KEY}' migriert.")
                    os.rename(json_path, json_path + '.migrated')
                    print(f"[Migration] Alte Datei zu '{json_path}.migrated' umbenannt.")
                else:
                    print(f"[Migration] FEHLER beim Speichern der migrierten Daten in der DB.")
            except (IOError, json.JSONDecodeError) as e:
                print(f"[Migration] FEHLER beim Lesen der {HOLIDAY_JSON_FILE}: {e}")
        else:
            print(f"[Migration] Keine alte {HOLIDAY_JSON_FILE} gefunden. Starte mit leerer Konfiguration.")
            save_config_json(HolidayManager.CONFIG_KEY, {})

        return all_holidays

    @staticmethod
    def get_holidays_for_year(year_int):
        """
        Gibt ein Dictionary der Feiertage für ein bestimmtes Jahr zurück.
        Format: {"YYYY-MM-DD": "Feiertagsname"}
        Nutzt jetzt den globalen Cache. (Wieder Static)
        """
        global _holidays_cache
        year_str = str(year_int)

        # 1. Prüfe den Cache
        if year_str in _holidays_cache:
            print(f"[DEBUG] Lade Feiertage für {year_str} aus dem Cache.")
            return _holidays_cache[year_str]

        # 2. Lade aus DB (oder migriere)
        print(f"[DEBUG] Lade Feiertage für {year_str} aus der DB.")
        all_holidays = load_config_json(HolidayManager.CONFIG_KEY)
        if all_holidays is None:
            all_holidays = HolidayManager._migrate_json_to_db()

        # 3. Filtere das gewünschte Jahr
        year_holidays = {}
        if all_holidays and year_str in all_holidays:
            year_holidays = all_holidays[year_str]

        # 4. Speichere im Cache
        _holidays_cache[year_str] = year_holidays
        return year_holidays

    @staticmethod
    def get_all_holidays():
        """Lädt alle Feiertage aus der DB. (Wieder Static)"""
        all_holidays = load_config_json(HolidayManager.CONFIG_KEY)
        if all_holidays is None:
            all_holidays = HolidayManager._migrate_json_to_db()
        return all_holidays

    @staticmethod
    def save_holidays(all_holidays_data):
        """
        Speichert die komplette Feiertagsstruktur in der DB.
        Leert jetzt den globalen Cache. (Wieder Static)
        """
        if save_config_json(HolidayManager.CONFIG_KEY, all_holidays_data):
            HolidayManager.clear_cache()
            return True
        return False

    @staticmethod
    def clear_cache():
        """Externe Methode, um den globalen Cache bei Bedarf zu leeren."""
        global _holidays_cache
        _holidays_cache.clear()
        print("[DEBUG] Feiertags-Cache (Global) geleert.")

    @staticmethod
    def is_holiday(date_obj):
        """
        Prüft, ob ein gegebenes date-Objekt ein Feiertag ist.
        (NEUE FUNKTION, aber @staticmethod, um Regel 1 zu erfüllen)
        """
        global _holidays_cache
        if not isinstance(date_obj, date):
            try:
                # Versuch, das Objekt in ein Datum umzuwandeln (z.B. von datetime)
                date_obj = date_obj.date()
            except Exception:
                print(f"[FEHLER] is_holiday erhielt ungültiges Objekt: {type(date_obj)}")
                return False

        year_str = str(date_obj.year)
        date_str = date_obj.strftime('%Y-%m-%d')

        # 1. Prüfen, ob das Jahr bereits im Cache ist. Wenn nicht, laden.
        if year_str not in _holidays_cache:
            print(f"[HolidayManager] Lade Feiertage für {year_str} (on-demand für is_holiday).")
            # Ruft die STATISCHE Methode auf
            HolidayManager.get_holidays_for_year(date_obj.year)

        # 2. Im Cache für das Jahr nach dem Datum-String suchen
        year_holidays = _holidays_cache.get(year_str, {})
        return date_str in year_holidays