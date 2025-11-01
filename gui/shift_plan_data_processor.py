# gui/shift_plan_data_processor.py
from datetime import date, datetime, timedelta
import calendar
from collections import defaultdict


class ShiftPlanDataProcessor:
    """
    Verantwortlich für die Verarbeitung und inkrementelle Aktualisierung
    der Plandaten-Caches, die im DataManager gespeichert sind.
    """

    def __init__(self, data_manager):
        self.dm = data_manager  # Referenz auf den DataManager, um Caches zu lesen/schreiben

    def process_vacations(self, year, month, raw_vacations):
        """
        Verarbeitet rohe Urlaubsanträge aus der DB in eine
        schnell zugreifbare Datums-Map.
        (Verschoben von DataManager._process_vacations)
        """
        processed = defaultdict(dict);

        try:
            month_start = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            month_end = date(year, month, last_day)
        except ValueError as e:
            print(f"[FEHLER] Ungültiges Datum in process_vacations: Y={year} M={month}. Fehler: {e}")
            return {}  # Leeres Dict zurückgeben

        for req in raw_vacations:
            user_id_str = str(req.get('user_id'))
            if not user_id_str: continue
            try:
                start_date_obj = req['start_date']
                end_date_obj = req['end_date']
                if not isinstance(start_date_obj, date):
                    start_date_obj = datetime.strptime(str(start_date_obj), '%Y-%m-%d').date()
                if not isinstance(end_date_obj, date):
                    end_date_obj = datetime.strptime(str(end_date_obj), '%Y-%m-%d').date()

                status = req.get('status', 'Unbekannt')

                current_date = start_date_obj
                while current_date <= end_date_obj:
                    # Prüfe nur Daten im relevanten Monat (Performance)
                    if month_start <= current_date <= month_end:
                        processed[user_id_str][current_date] = status;
                    if current_date > month_end:
                        break  # OPTIMIERUNG: Brich ab, wenn das Ende des Monats überschritten ist
                    current_date += timedelta(days=1)
            except (ValueError, TypeError, KeyError) as e:
                print(f"[WARNUNG] Fehler beim Verarbeiten von Urlaub ID {req.get('id', 'N/A')}: {e}")

        return dict(processed)  # Konvertiere defaultdict zu dict

    def recalculate_daily_counts_for_day(self, date_obj, old_shift, new_shift):
        """
        Aktualisiert den 'daily_counts'-Cache im DataManager für einen
        bestimmten Tag nach einer Schichtänderung.
        (Verschoben von DataManager.recalculate_daily_counts_for_day)
        """

        # Invaliere den P5-Cache im DataManager
        cache_key = (date_obj.year, date_obj.month)
        if cache_key in self.dm.monthly_caches:
            print(f"[DM Cache] Entferne {cache_key} wegen Zählungs-Update aus P5-Cache (via Processor).")
            del self.dm.monthly_caches[cache_key]

        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[DataProcessor] Aktualisiere Zählung für {date_str}: '{old_shift}' -> '{new_shift}'")

        # Greife direkt auf den Cache im DM zu
        if date_str not in self.dm.daily_counts:
            self.dm.daily_counts[date_str] = {}

        counts_today = self.dm.daily_counts[date_str]

        def should_count_shift(shift_abbr):
            return shift_abbr and shift_abbr not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?']

        if should_count_shift(old_shift):
            counts_today[old_shift] = counts_today.get(old_shift, 1) - 1
            if counts_today[old_shift] <= 0:
                del counts_today[old_shift]

        if should_count_shift(new_shift):
            counts_today[new_shift] = counts_today.get(new_shift, 0) + 1

        if not counts_today and date_str in self.dm.daily_counts:
            del self.dm.daily_counts[date_str]

        print(f"[DataProcessor] Neue Zählung für {date_str}: {self.dm.daily_counts.get(date_str, {})}")