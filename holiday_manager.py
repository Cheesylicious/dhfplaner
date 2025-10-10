# gui/holiday_manager.py
import json
import os
from datetime import date
import holidays


class HolidayManager:
    # KORREKTUR: Die Konstante wird Teil der Klasse
    HOLIDAYS_FILE = 'holidays_config.json'

    @staticmethod
    def get_holidays_for_year(year):
        """
        Lädt Feiertage aus der Speicher-Datei, falls vorhanden.
        Andernfalls generiert es die Standard-Feiertage für MV und speichert sie.
        """
        if os.path.exists(HolidayManager.HOLIDAYS_FILE):
            with open(HolidayManager.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                try:
                    all_holidays = json.load(f)
                    year_str = str(year)
                    if year_str in all_holidays:
                        return {date.fromisoformat(dt): name for dt, name in all_holidays[year_str].items()}
                except json.JSONDecodeError:
                    pass

        return HolidayManager._generate_and_save_holidays(year)

    @staticmethod
    def _generate_and_save_holidays(year):
        """Generiert die Standard-Feiertage für MV für ein Jahr und speichert sie."""
        mv_holidays = holidays.Germany(prov='MV', years=year)

        all_holidays = {}
        if os.path.exists(HolidayManager.HOLIDAYS_FILE):
            with open(HolidayManager.HOLIDAYS_FILE, 'r', encoding='utf-8') as f:
                try:
                    all_holidays = json.load(f)
                except json.JSONDecodeError:
                    all_holidays = {}

        all_holidays[str(year)] = {dt.isoformat(): name for dt, name in mv_holidays.items()}

        HolidayManager.save_holidays(all_holidays)

        return mv_holidays

    @staticmethod
    def save_holidays(all_holidays_data):
        """Speichert das gesamte Feiertags-Wörterbuch in der JSON-Datei."""
        with open(HolidayManager.HOLIDAYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_holidays_data, f, indent=4, ensure_ascii=False)