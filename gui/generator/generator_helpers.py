# gui/generator/generator_helpers.py
from datetime import date, timedelta, datetime, time

class GeneratorHelpers:
    """
    Kapselt alle Low-Level-Datenabrufe und Regelprüfungen für den Generator.
    Greift auf den Zustand der Haupt-Generator-Instanz zu.
    """

    def __init__(self, generator_instance):
        self.gen = generator_instance
        self._next_month_shifts = None  # Cache für Folgemonatsdaten

    def check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlappung zweier Schichten mithilfe des Caches im DataManager. """
        if shift1_abbrev in self.gen.free_shifts_indicators or shift2_abbrev in self.gen.free_shifts_indicators: return False
        preprocessed_times = getattr(self.gen.data_manager, '_preprocessed_shift_times', {})
        s1, e1 = preprocessed_times.get(shift1_abbrev, (None, None))
        s2, e2 = preprocessed_times.get(shift2_abbrev, (None, None))
        if s1 is None or s2 is None: return False
        overlap = (s1 < e2) and (s2 < e1)
        return overlap

    def get_previous_shift(self, user_id_str, check_date_obj):
        """ Holt die *Arbeits*-Schicht vom Vortag (ignoriert FREI etc.). """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')
        shift = self.gen.live_shifts_data.get(user_id_str, {}).get(check_date_str)
        first_day_current_month = date(self.gen.year, self.gen.month, 1)
        if shift is None and check_date_obj < first_day_current_month:
            prev_month_data = getattr(self.gen.data_manager, '_prev_month_shifts', {})
            shift = prev_month_data.get(user_id_str, {}).get(check_date_str)
        return shift if shift not in [None, ""] and shift not in self.gen.free_shifts_indicators else ""

    def get_previous_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag vom Vortag (inkl. FREI, U, etc.). """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')
        shift = self.gen.live_shifts_data.get(user_id_str, {}).get(check_date_str)
        first_day_current_month = date(self.gen.year, self.gen.month, 1)
        if shift is None and check_date_obj < first_day_current_month:
            prev_month_data = getattr(self.gen.data_manager, '_prev_month_shifts', {})
            shift = prev_month_data.get(user_id_str, {}).get(check_date_str)
        return shift if shift is not None else ""

    def _load_next_month_data(self):
        """ Lädt die Schichtdaten des Folgemonats in einen Cache (intern in dieser Klasse). """
        if self._next_month_shifts is None:
            next_month_year = self.gen.year
            next_month_month = self.gen.month + 1
            if next_month_month > 12:
                next_month_month = 1
                next_month_year += 1

            if self.gen.data_manager and hasattr(self.gen.data_manager, 'get_raw_shifts_for_month'):
                try:
                    self._next_month_shifts = self.gen.data_manager.get_raw_shifts_for_month(next_month_year,
                                                                                             next_month_month)
                except Exception as e:
                    print(f"[FEHLER] Konnte Folgemonatsdaten nicht laden: {e}")
                    self._next_month_shifts = {}
            else:
                self._next_month_shifts = {}

    def get_next_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag vom Folgetag (inkl. FREI, U, etc.). """
        next_date_obj = check_date_obj + timedelta(days=1)
        next_date_str = next_date_obj.strftime('%Y-%m-%d')
        shift = self.gen.live_shifts_data.get(user_id_str, {}).get(next_date_str)

        if shift is None and next_date_obj.month != self.gen.month:
            self._load_next_month_data()
            if self._next_month_shifts:
                shift = self._next_month_shifts.get(user_id_str, {}).get(next_date_str)

        return shift if shift is not None else ""

    def get_shift_after_next_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag von Übermorgen (inkl. FREI, U, etc.). """
        after_next_date_obj = check_date_obj + timedelta(days=2)
        after_next_date_str = after_next_date_obj.strftime('%Y-%m-%d')
        shift = self.gen.live_shifts_data.get(user_id_str, {}).get(after_next_date_str)

        if shift is None and after_next_date_obj.month != self.gen.month:
            self._load_next_month_data()
            if self._next_month_shifts:
                shift = self._next_month_shifts.get(user_id_str, {}).get(after_next_date_str)

        return shift if shift is not None else ""

    def count_consecutive_shifts(self, user_id_str, check_date_obj):
        """ Zählt Arbeitstage am Stück rückwärts ab check_date_obj. """
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self.get_previous_shift(user_id_str, current_check) # Nutzt lokale Helfer-Methode
            if shift and shift in self.gen.work_shifts:
                count += 1;
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def count_consecutive_same_shifts(self, user_id_str, check_date_obj, target_shift_abbrev):
        """ Zählt gleiche Arbeitsschichten am Stück rückwärts ab check_date_obj. """
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self.get_previous_shift(user_id_str, current_check) # Nutzt lokale Helfer-Methode
            if shift == target_shift_abbrev:
                count += 1;
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def check_mandatory_rest(self, user_id_str, current_date_obj):
        """
        Prüft, ob der Benutzer die obligatorische Ruhezeit nach einem maximalen Block
        von Arbeitstagen (HARD_MAX_CONSECUTIVE_SHIFTS) eingehalten hat.
        """
        if self.gen.mandatory_rest_days <= 0:
            return True

        day_before = current_date_obj - timedelta(days=1)
        free_days_count = 0
        check_date = day_before

        while True:
            shift = self.get_previous_raw_shift(user_id_str, check_date) # Nutzt lokale Helfer-Methode

            if shift in self.gen.free_shifts_indicators:
                free_days_count += 1
                check_date -= timedelta(days=1)

                if free_days_count > self.gen.HARD_MAX_CONSECUTIVE_SHIFTS + self.gen.mandatory_rest_days:
                    return True
            else:
                break

        last_work_day_obj = check_date

        if free_days_count == 0:
            return True

        work_day_count = self.count_consecutive_shifts(user_id_str, last_work_day_obj + timedelta(days=1)) # Nutzt lokale Helfer-Methode

        if work_day_count >= self.gen.HARD_MAX_CONSECUTIVE_SHIFTS:
            if free_days_count < self.gen.mandatory_rest_days:
                return False

        return True