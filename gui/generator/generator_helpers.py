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
        # NEU: Schichten, die als fortlaufende Arbeitstage gezählt werden müssen (inkl. QA/S)
        self.hard_work_indicators = {'T.', 'N.', '6', '24', 'QA', 'S'}

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
        """
        Holt die *Arbeits*-Schicht vom Vortag (ignoriert U, X, WF etc.).
        Gibt die Schichtabkürzung zurück, oder "" falls kein Dienst.

        KORREKTUR (N->T Problem): Priorisiert die Vormonatsdatenbank,
        wenn das Datum im Vormonat liegt.
        """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')

        # --- KORREKTUR (N->T Problem) ---
        # 1. Prüfe, ob das Datum im Vormonat liegt
        if check_date_obj.month != self.gen.month:
            # Hier greifen wir auf die Methode zu, die in ShiftPlanDataManager bereitgestellt wird
            prev_month_data = self.gen.data_manager.get_previous_month_shifts().get(user_id_str, {})
            shift = prev_month_data.get(check_date_str)
            if shift and shift not in self.gen.free_shifts_indicators:
                return shift
            # Explizit "" zurückgeben, wenn im Vormonat nichts gefunden wurde
            return ""

            # 2. Wenn nicht im Vormonat, prüfe live_shifts_data (aktueller Monat)
        shifts_data = self.gen.live_shifts_data.get(user_id_str, {})
        shift = shifts_data.get(check_date_str)
        if shift and shift not in self.gen.free_shifts_indicators:
            return shift
        # --- ENDE KORREKTUR ---

        return ""  # Kein Dienst gefunden

    def get_previous_raw_shift(self, user_id_str, check_date_obj):
        """
        Holt die Schicht vom Vortag, *inklusive* Freischichten.
        Gibt die Schichtabkürzung (oder None) zurück.

        KORREKTUR (N->T Problem): Priorisiert die Vormonatsdatenbank,
        wenn das Datum im Vormonat liegt.
        """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')

        # --- KORREKTUR (N->T Problem) ---
        # 1. Prüfe, ob das Datum im Vormonat liegt
        if check_date_obj.month != self.gen.month:
            # Hier greifen wir auf die Methode zu, die in ShiftPlanDataManager bereitgestellt wird
            prev_month_data = self.gen.data_manager.get_previous_month_shifts().get(user_id_str, {})
            shift = prev_month_data.get(check_date_str)
            if shift is not None:
                return shift
            return None  # Explizit None zurückgeben

        # 2. Wenn nicht im Vormonat, prüfe live_shifts_data (aktueller Monat)
        shifts_data = self.gen.live_shifts_data.get(user_id_str, {})
        shift = shifts_data.get(check_date_str)
        if shift is not None:
            return shift
        # --- ENDE KORREKTUR ---

        return None  # Kein Eintrag gefunden

    def get_next_raw_shift(self, user_id_str, current_date_obj):
        """ Holt die Schicht des nächsten Tages. (Für Isolationsprüfung) """
        next_date_obj = current_date_obj + timedelta(days=1)
        next_date_str = next_date_obj.strftime('%Y-%m-%d')

        # Prüfe aktuellen Monatsplan
        shift = self.gen.live_shifts_data.get(user_id_str, {}).get(next_date_str)
        if shift is not None: return shift

        # Prüfe Cache für Folgemonatsdaten (nur für den ersten Tag des nächsten Monats relevant)
        if next_date_obj.month != current_date_obj.month and next_date_obj.day == 1:
            if self._next_month_shifts is None:
                # Hier greifen wir auf die Methode zu, die in ShiftPlanDataManager bereitgestellt wird (siehe Korrektur oben)
                self._next_month_shifts = self.gen.data_manager.get_next_month_shifts()
            shift = self._next_month_shifts.get(user_id_str, {}).get(next_date_str)
            if shift is not None: return shift

        return None

    def get_shift_after_next_raw_shift(self, user_id_str, current_date_obj):
        """ Holt die Schicht des übernächsten Tages. (Für Isolationsprüfung) """
        after_next_date_obj = current_date_obj + timedelta(days=2)
        after_next_date_str = after_next_date_obj.strftime('%Y-%m-%d')

        # Prüfe aktuellen Monatsplan
        shift = self.gen.live_shifts_data.get(user_id_str, {}).get(after_next_date_str)
        if shift is not None: return shift

        # Prüfe Cache für Folgemonatsdaten (relevant für Tag 1 & 2 des Folgemonats)
        if after_next_date_obj.month != current_date_obj.month and after_next_date_obj.day in [1, 2]:
            if self._next_month_shifts is None:
                # Hier greifen wir auf die Methode zu, die in ShiftPlanDataManager bereitgestellt wird (siehe Korrektur oben)
                self._next_month_shifts = self.gen.data_manager.get_next_month_shifts()
            shift = self._next_month_shifts.get(user_id_str, {}).get(after_next_date_str)
            if shift is not None: return shift

        return None

    def count_consecutive_shifts(self, user_id_str, current_date_obj):
        """ Zählt die fortlaufenden Arbeitstage bis zum aktuellen Tag. """
        count = 0
        current_check = current_date_obj - timedelta(days=1)

        while True:
            # get_previous_raw_shift liefert die Schicht oder None
            shift = self.get_previous_raw_shift(user_id_str, current_check)

            # Prüft, ob die Schicht eine ARBEITSschicht ist (inkl. QA/S)
            if shift and shift in self.hard_work_indicators:
                count += 1
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def count_consecutive_same_shifts(self, user_id_str, current_date_obj, target_shift_abbrev):
        """ Zählt die fortlaufenden identischen Arbeitstage. """
        count = 0
        current_check = current_date_obj - timedelta(days=1)

        while True:
            shift = self.get_previous_shift(user_id_str,
                                            current_check)  # Nutzt get_previous_shift (ignoriert Freischichten)

            if shift == target_shift_abbrev:
                count += 1
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
            # get_previous_raw_shift liefert die Schicht oder None
            shift = self.get_previous_raw_shift(user_id_str, check_date)

            # Prüft, ob die Schicht eine FREI-Schicht ist
            if shift in self.gen.free_shifts_indicators:
                free_days_count += 1
                check_date -= timedelta(days=1)

                # Abbruch bei übermäßig vielen Freitagen
                if free_days_count > self.gen.HARD_MAX_CONSECUTIVE_SHIFTS + self.gen.mandatory_rest_days:
                    return True
            else:
                break

        last_work_day_obj = check_date  # Der letzte Arbeitstag war check_date

        # Wenn free_days_count 0 ist, gab es keine Pause -> keine Prüfung nötig
        if free_days_count == 0:
            return True

        # Zählt die Arbeitstage vor der Pause (inkl. last_work_day_obj)
        work_day_count = self.count_consecutive_shifts(user_id_str, last_work_day_obj + timedelta(days=1))

        # Wenn der Block vor der Pause >= HARD_MAX war, muss die Pause ausreichend sein
        if work_day_count >= self.gen.HARD_MAX_CONSECUTIVE_SHIFTS:
            return free_days_count >= self.gen.mandatory_rest_days

        return True  # Block war zu kurz, keine obligatorische Ruhezeit nötig

