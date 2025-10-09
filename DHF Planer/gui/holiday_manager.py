# gui/holiday_manager.py (KORRIGIERT: Liest Konfiguration aus DB)
import json
from datetime import date
from dateutil.easter import easter
from holidays import country_holidays
from database.db_manager import load_holiday_config  # Wird jetzt in MainAdminWindow verwendet


class HolidayManager:
    @staticmethod
    def is_holiday_for_state(check_date, state):
        """Prüft, ob ein Datum ein Feiertag für ein bestimmtes Bundesland ist."""
        # Wir verwenden country_holidays, das Bundesländer unterstützt, um Feiertage dynamisch zu ermitteln
        # ohne eine lokale holidays.json
        holidays_year = country_holidays('DE', subdiv=state, years=check_date.year)

        # holidays.country_holidays gibt ein Dictionary zurück, das ein Datumsobjekt als Schlüssel hat.
        return check_date in holidays_year

    @staticmethod
    def get_holidays_for_year(year, config_data=None):
        """
        Gibt eine Liste von Feiertagen für ein bestimmtes Jahr und Bundesland zurück.
        :param year: Das Jahr.
        :param config_data: Dictionary mit der Schlüssel 'state'.
        :return: Set von Feiertags-Date-Objekten.
        """
        if config_data is None:
            # Fallback, falls config_data nicht übergeben wird (sollte nicht passieren)
            config_data = load_holiday_config()

        state = config_data.get('state', 'BB')

        # Wir verwenden country_holidays, das Bundesländer unterstützt, um Feiertage dynamisch zu ermitteln.
        # years kann eine einzelne Zahl oder eine Liste sein.
        holidays_year = country_holidays('DE', subdiv=state, years=year)

        # Konvertiert das Ergebnis in ein Set von date-Objekten
        return set(holidays_year.keys())