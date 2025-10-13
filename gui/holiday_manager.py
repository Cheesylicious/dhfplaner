# gui/holiday_manager.py
import json
from datetime import date
import holidays
# NEUE IMPORTS
from database.db_core import load_config_json, save_config_json


class HolidayManager:
    # Der Schlüssel in der config_storage Tabelle
    CONFIG_KEY = 'HOLIDAYS_CONFIG'

    @staticmethod
    def get_holidays_from_db_raw():
        """Holt die Feiertagsdaten im Rohformat (JSON-kompatibles Dict) aus der Datenbank."""
        # Nutzt die zentrale DB-Funktion
        return load_config_json(HolidayManager.CONFIG_KEY) or {}

    @staticmethod
    def get_holidays_for_year(year):
        """
        Lädt Feiertage aus der Datenbank.
        Andernfalls generiert es die Standard-Feiertage für MV und speichert sie.
        """
        # Lade alle Feiertage aus der DB
        all_holidays = HolidayManager.get_holidays_from_db_raw()

        # Wenn Daten vorhanden sind, versuche das spezifische Jahr zu laden
        if all_holidays is not None:
            year_str = str(year)
            if year_str in all_holidays:
                # Konvertiere ISO-Format-String zurück zu date-Objekten
                return {date.fromisoformat(dt): name for dt, name in all_holidays[year_str].items()}

        # Wenn nicht gefunden oder DB leer, generiere und speichere Standard-Feiertage
        return HolidayManager._generate_and_save_holidays(year)

    @staticmethod
    def _generate_and_save_holidays(year):
        """Generiert die Standard-Feiertage für MV für ein Jahr und speichert sie."""
        mv_holidays = holidays.Germany(prov='MV', years=year)

        # Lade vorhandene Daten aus der DB, falls vorhanden
        all_holidays = HolidayManager.get_holidays_from_db_raw()

        # Füge die neu generierten Feiertage hinzu
        all_holidays[str(year)] = {dt.isoformat(): name for dt, name in mv_holidays.items()}

        HolidayManager.save_holidays(all_holidays)

        return mv_holidays

    @staticmethod
    def save_holidays(all_holidays_data):
        """Speichert das gesamte Feiertags-Wörterbuch in der Datenbank."""
        # Nutze die zentrale DB-Funktion
        return save_config_json(HolidayManager.CONFIG_KEY, all_holidays_data)