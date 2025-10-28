# gui/shift_plan_generator.py
import calendar
import threading
from collections import defaultdict
from datetime import date, timedelta, datetime, time
import math
import traceback  # Für detailliertere Fehlermeldungen bei Bedarf

# Annahme: DataManager ist importierbar oder über app erreichbar
try:
    from gui.shift_plan_data_manager import ShiftPlanDataManager
except ImportError:
    ShiftPlanDataManager = None  # Fallback

from database.db_shifts import save_shift_entry

# Konstanten (jetzt eher als DEFAULTS, da konfigurierbar)
MAX_MONTHLY_HOURS = 228.0  # Harte Obergrenze für Monatsstunden (Nicht konfigurierbar)
SOFT_MAX_CONSECUTIVE_SHIFTS = 6  # Standard-Obergrenze (Präferenz-Limit für Runde 1)
HARD_MAX_CONSECUTIVE_SHIFTS = 8  # Absolute Obergrenze (Hard-Limit für Runde 2/Ruhezeit-Check)
DEFAULT_MANDATORY_REST_DAYS = 2  # Standard für Mindestruhezeit nach Max-Schichten
DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT = 4  # Standard, wenn nicht in Config gesetzt (Weiche Regel)

# Standardwerte für Scores (werden im Generator mit Konfigurationswerten überschrieben)
DEFAULT_FAIRNESS_THRESHOLD_HOURS = 10.0
DEFAULT_MIN_HOURS_FAIRNESS_THRESHOLD = 20.0
DEFAULT_MIN_HOURS_SCORE_MULT = 5.0
DEFAULT_FAIRNESS_SCORE_MULT = 1.0
DEFAULT_ISOLATION_SCORE_MULT = 30.0 # Standardwert aus GeneratorSettingsWindow
DEFAULT_WUNSCHFREI_RESPECT = 75


class ShiftPlanGenerator:
    """
    Kapselt die Logik zur automatischen Generierung des Schichtplans.
    Berücksichtigt Regeln, Präferenzen (Partner, Block), Stundenfairness und Mindestbesetzung.
    """

    def __init__(self, app, data_manager, year, month, all_users, user_data_map,
                 vacation_requests, wunschfrei_requests, live_shifts_data,
                 holidays_in_month, progress_callback, completion_callback):
        self.app = app
        self.data_manager = data_manager
        self.year = year
        self.month = month
        self.all_users = all_users  # Liste von User-Dicts
        self.user_data_map = user_data_map  # Dict {user_id: user_dict}
        self.vacation_requests = vacation_requests  # {user_id_str: {date_obj: status}}
        self.wunschfrei_requests = wunschfrei_requests  # {user_id_str: {date_str: (status, shift_abbr)}}
        self.live_shifts_data = live_shifts_data  # {user_id_str: {date_str: shift_abbr}} - Wird während Generierung aktualisiert!
        self.holidays_in_month = holidays_in_month  # Set von date_obj
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

        # Reihenfolge, in der Schichten geplant werden
        self.shifts_to_plan = ["6", "T.", "N."]
        # Stunden pro Schichtkürzel
        self.shift_hours = {abbrev: float(data.get('hours', 0.0))
                            for abbrev, data in self.app.shift_types_data.items()}
        # Menge der Schichtkürzel, die als "Arbeitstage" zählen
        self.work_shifts = {s for s, data in self.app.shift_types_data.items() if
                            float(data.get('hours', 0.0)) > 0 and s not in ['U', 'EU']}
        self.work_shifts.update(['T.', 'N.', '6', '24'])

        # Menge der Kürzel, die als "Frei" gelten
        self.free_shifts_indicators = {"", "FREI", "U", "X", "EU", "WF", "U?"}

        # Generator-Konfiguration laden
        self.generator_config = {}
        if self.data_manager and hasattr(self.data_manager, 'get_generator_config'):
            try:
                # Nutzt die Methode aus dem DataManager, die Defaults integriert
                self.generator_config = self.data_manager.get_generator_config()
                print("[Generator] Generator-Konfiguration geladen:", self.generator_config) # Debugging hinzugefügt
            except Exception as e:
                print(f"[FEHLER] Konnte Generator-Konfiguration nicht laden: {e}")

        # --- Konfigurierbare Einstellungen laden ---
        self.max_consecutive_same_shift_limit = self.generator_config.get('max_consecutive_same_shift',
                                                                          DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT)
        # Korrektur: mandatory_rest_days kommt aus der Config
        self.mandatory_rest_days = self.generator_config.get('mandatory_rest_days_after_max_shifts',
                                                             DEFAULT_MANDATORY_REST_DAYS)
        self.avoid_understaffing_hard = self.generator_config.get('avoid_understaffing_hard', True)
        self.wunschfrei_respect_level = self.generator_config.get('wunschfrei_respect_level',
                                                                  DEFAULT_WUNSCHFREI_RESPECT)

        # Score Schwellenwerte
        self.fairness_threshold_hours = self.generator_config.get('fairness_threshold_hours',
                                                                  DEFAULT_FAIRNESS_THRESHOLD_HOURS)
        self.min_hours_fairness_threshold = self.generator_config.get('min_hours_fairness_threshold',
                                                                      DEFAULT_MIN_HOURS_FAIRNESS_THRESHOLD)

        # Score Multiplikatoren
        self.min_hours_score_multiplier = self.generator_config.get('min_hours_score_multiplier',
                                                                    DEFAULT_MIN_HOURS_SCORE_MULT)
        self.fairness_score_multiplier = self.generator_config.get('fairness_score_multiplier',
                                                                   DEFAULT_FAIRNESS_SCORE_MULT)
        self.isolation_score_multiplier = self.generator_config.get('isolation_score_multiplier',
                                                                     DEFAULT_ISOLATION_SCORE_MULT)

        # Benutzer-spezifische Präferenzen laden
        default_user_pref = {
            'min_monthly_hours': None,
            'max_monthly_hours': None,
            'shift_exclusions': [],
            'ratio_preference_scale': 50,
            'max_consecutive_same_shift_override': None
        }
        raw_user_preferences = self.generator_config.get('user_preferences', {})
        self.user_preferences = defaultdict(lambda: default_user_pref.copy())
        for user_id_str, prefs in raw_user_preferences.items():
            if 'ratio_preference_scale' not in prefs:
                prefs['ratio_preference_scale'] = 50
            self.user_preferences[user_id_str].update(prefs)

        # Partner-Prioritäten verarbeiten
        self.prioritized_partners_list = self.generator_config.get('preferred_partners_prioritized', [])
        self.partner_priority_map = defaultdict(list)
        for entry in self.prioritized_partners_list:
            try:
                id_a = int(entry['id_a'])
                id_b = int(entry['id_b'])
                prio = int(entry['priority'])
                self.partner_priority_map[id_a].append((prio, id_b))
                self.partner_priority_map[id_b].append((prio, id_a))
            except (ValueError, KeyError, TypeError):
                continue
        for user_id in self.partner_priority_map:
            self.partner_priority_map[user_id].sort(key=lambda x: x[0])

        # Cache für Folgemonatsdaten
        self._next_month_shifts = None

    def _update_progress(self, value, text):
        """ Sendet Fortschritt an die GUI (über Callback). """
        if self.progress_callback: self.progress_callback(value, text)

    def run_generation(self):
        """ Startet den Generierungsprozess (wird im Thread aufgerufen). """
        self._generate()

    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlappung zweier Schichten mithilfe des Caches im DataManager. """
        if shift1_abbrev in self.free_shifts_indicators or shift2_abbrev in self.free_shifts_indicators: return False
        preprocessed_times = getattr(self.data_manager, '_preprocessed_shift_times', {})
        s1, e1 = preprocessed_times.get(shift1_abbrev, (None, None))
        s2, e2 = preprocessed_times.get(shift2_abbrev, (None, None))
        if s1 is None or s2 is None: return False
        overlap = (s1 < e2) and (s2 < e1)
        return overlap

    def _get_previous_shift(self, user_id_str, check_date_obj):
        """ Holt die *Arbeits*-Schicht vom Vortag (ignoriert FREI etc.). """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(check_date_str)
        first_day_current_month = date(self.year, self.month, 1)
        if shift is None and check_date_obj < first_day_current_month:
            prev_month_data = getattr(self.data_manager, '_prev_month_shifts', {})
            shift = prev_month_data.get(user_id_str, {}).get(check_date_str)
        return shift if shift not in [None, ""] and shift not in self.free_shifts_indicators else ""

    def _get_previous_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag vom Vortag (inkl. FREI, U, etc.). """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(check_date_str)
        first_day_current_month = date(self.year, self.month, 1)
        if shift is None and check_date_obj < first_day_current_month:
            prev_month_data = getattr(self.data_manager, '_prev_month_shifts', {})
            shift = prev_month_data.get(user_id_str, {}).get(check_date_str)
        return shift if shift is not None else ""

    def _load_next_month_data(self):
        """ Lädt die Schichtdaten des Folgemonats in einen Cache. """
        if self._next_month_shifts is None:
            next_month_year = self.year
            next_month_month = self.month + 1
            if next_month_month > 12:
                next_month_month = 1
                next_month_year += 1

            if self.data_manager and hasattr(self.data_manager, 'get_raw_shifts_for_month'):
                try:
                    self._next_month_shifts = self.data_manager.get_raw_shifts_for_month(next_month_year,
                                                                                         next_month_month)
                except Exception as e:
                    print(f"[FEHLER] Konnte Folgemonatsdaten nicht laden: {e}")
                    self._next_month_shifts = {}
            else:
                self._next_month_shifts = {}

    def _get_next_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag vom Folgetag (inkl. FREI, U, etc.). """
        next_date_obj = check_date_obj + timedelta(days=1)
        next_date_str = next_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(next_date_str)

        if shift is None and next_date_obj.month != self.month:
            self._load_next_month_data()
            if self._next_month_shifts:
                shift = self._next_month_shifts.get(user_id_str, {}).get(next_date_str)

        return shift if shift is not None else ""

    def _get_shift_after_next_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag von Übermorgen (inkl. FREI, U, etc.). """
        after_next_date_obj = check_date_obj + timedelta(days=2)
        after_next_date_str = after_next_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(after_next_date_str)

        if shift is None and after_next_date_obj.month != self.month:
            self._load_next_month_data()
            if self._next_month_shifts:
                shift = self._next_month_shifts.get(user_id_str, {}).get(after_next_date_str)

        return shift if shift is not None else ""

    def _count_consecutive_shifts(self, user_id_str, check_date_obj):
        """ Zählt Arbeitstage am Stück rückwärts ab check_date_obj. """
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self._get_previous_shift(user_id_str, current_check)
            if shift and shift in self.work_shifts:
                count += 1;
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def _count_consecutive_same_shifts(self, user_id_str, check_date_obj, target_shift_abbrev):
        """ Zählt gleiche Arbeitsschichten am Stück rückwärts ab check_date_obj. """
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self._get_previous_shift(user_id_str, current_check)
            if shift == target_shift_abbrev:
                count += 1;
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def _check_mandatory_rest(self, user_id_str, current_date_obj):
        """
        Prüft, ob der Benutzer die obligatorische Ruhezeit nach einem maximalen Block
        von Arbeitstagen (HARD_MAX_CONSECUTIVE_SHIFTS) eingehalten hat.
        """
        if self.mandatory_rest_days <= 0:
            return True

        day_before = current_date_obj - timedelta(days=1)
        free_days_count = 0
        check_date = day_before

        while True:
            shift = self._get_previous_raw_shift(user_id_str, check_date)

            if shift in self.free_shifts_indicators:
                free_days_count += 1
                check_date -= timedelta(days=1)

                if free_days_count > HARD_MAX_CONSECUTIVE_SHIFTS + self.mandatory_rest_days:
                    return True
            else:
                break

        last_work_day_obj = check_date

        if free_days_count == 0:
            return True

        work_day_count = self._count_consecutive_shifts(user_id_str, last_work_day_obj + timedelta(days=1))

        if work_day_count >= HARD_MAX_CONSECUTIVE_SHIFTS:
            if free_days_count < self.mandatory_rest_days:
                return False

        return True

    def _generate(self):
        """ Führt die eigentliche Generierungslogik aus. """
        try:
            self._update_progress(5, "Starte Generierungsprozess...")
            days_in_month = calendar.monthrange(self.year, self.month)[1]
            # NEU: Zusätzlich für T/N-Ratio-Scoring benötigte Zähler
            live_user_hours = defaultdict(float)
            live_shift_counts = defaultdict(lambda: defaultdict(int))
            live_shift_counts_ratio = defaultdict(lambda: defaultdict(int))  # Für T/N Ratio

            # Initialisierung
            for user_id_str, day_data in self.live_shifts_data.items():
                try:
                    user_id_int = int(user_id_str)
                except ValueError: continue
                if user_id_int not in self.user_data_map: continue
                for date_str, shift in day_data.items():
                    try:
                        shift_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        if shift_date_obj.year != self.year or shift_date_obj.month != self.month: continue
                    except ValueError: continue
                    hours = self.shift_hours.get(shift, 0.0)
                    if hours > 0: live_user_hours[user_id_int] += hours

                    if shift == 'T.' or shift == '6': live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1
                    if shift == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1
                    if shift in self.shifts_to_plan: live_shift_counts[user_id_int][shift] += 1  # Normale Zählung

            save_count = 0
            total_steps = days_in_month * len(self.shifts_to_plan)
            current_step = 0

            # Hauptschleife: Tage
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')
                prev_date_obj = current_date_obj - timedelta(days=1)
                two_days_ago_obj = current_date_obj - timedelta(days=2)
                next_day_obj = current_date_obj + timedelta(days=1)
                day_after_next_obj = current_date_obj + timedelta(days=2)

                users_unavailable_today = set()
                existing_dog_assignments = defaultdict(list)
                assignments_today_by_shift = defaultdict(set)

                # VORDURCHLAUF
                for user_id_int, user_data in self.user_data_map.items():
                    user_id_str = str(user_id_int);
                    user_dog = user_data.get('diensthund')
                    is_unavailable, is_working = False, False
                    if self.vacation_requests.get(user_id_str, {}).get(current_date_obj) in ['Approved', 'Genehmigt']:
                        is_unavailable = True
                    elif not is_unavailable and date_str in self.wunschfrei_requests.get(user_id_str, {}):
                        wf_status, wf_shift = self.wunschfrei_requests[user_id_str][date_str]
                        if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert']: is_unavailable = True
                    existing_shift = self.live_shifts_data.get(user_id_str, {}).get(date_str)
                    if existing_shift and existing_shift not in ["", "FREI"]:
                        is_working = True;
                        assignments_today_by_shift[existing_shift].add(user_id_int)
                    if is_unavailable or is_working: users_unavailable_today.add(user_id_str)
                    if is_working and user_dog and user_dog != '---': existing_dog_assignments[user_dog].append(
                        {'user_id': user_id_int, 'shift': existing_shift})

                # Mindestbesetzung
                try:
                    min_staffing_today = self.data_manager.get_min_staffing_for_date(current_date_obj)
                except Exception as staffing_err:
                    min_staffing_today = {};
                    print(f"[WARN] Staffing Error {date_str}: {staffing_err}")

                # Schleife: Schichten (6, T, N)
                for shift_abbrev in self.shifts_to_plan:
                    current_step += 1;
                    progress_perc = int((current_step / total_steps) * 90) + 5
                    self._update_progress(progress_perc, f"Plane {shift_abbrev} für {date_str}...")
                    if shift_abbrev == "6" and (
                            current_date_obj.weekday() != 4 and current_date_obj not in self.holidays_in_month): continue
                    required_count = min_staffing_today.get(shift_abbrev, 0)
                    if required_count <= 0: continue
                    current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()))
                    needed_now = required_count - current_assigned_count
                    if needed_now <= 0: continue
                    print(
                        f"   -> Need {needed_now} for '{shift_abbrev}' @ {date_str} (Req:{required_count}, Has:{current_assigned_count})")
                    assigned_count_this_shift_loop = 0 # Zähler für die Zuweisungen *innerhalb* dieser Schicht-Iteration

                    # ===============================================
                    # Runde 1: Faire Zuweisung mit Präferenzen
                    # ===============================================
                    search_attempts_fair = 0
                    while assigned_count_this_shift_loop < needed_now and search_attempts_fair < len(
                            self.all_users) + 1:
                        search_attempts_fair += 1
                        possible_candidates = []
                        skipped_reasons = defaultdict(int)
                        candidate_total_hours = 0.0;
                        num_available_candidates = 0

                        # Schritt 1.1: Gültige Kandidaten sammeln
                        for user_dict in self.all_users:
                            user_id_int = user_dict.get('id');
                            if user_id_int is None: continue
                            user_id_str = str(user_id_int)
                            if user_id_str in users_unavailable_today: continue

                            user_dog = user_dict.get('diensthund');
                            current_hours = live_user_hours.get(user_id_int, 0.0);
                            hours_for_this_shift = self.shift_hours.get(shift_abbrev, 0.0)
                            skip_reason = None

                            user_pref = self.user_preferences[user_id_str]
                            min_hours_pref = user_pref.get('min_monthly_hours')
                            max_hours_override = user_pref.get('max_monthly_hours')
                            max_same_shift_override = user_pref.get('max_consecutive_same_shift_override')

                            prev_shift = self._get_previous_shift(user_id_str, prev_date_obj);
                            one_day_ago_raw_shift = self._get_previous_raw_shift(user_id_str, prev_date_obj);
                            two_days_ago_shift = self._get_previous_shift(user_id_str, two_days_ago_obj)
                            next_raw_shift = self._get_next_raw_shift(user_id_str, current_date_obj)
                            after_next_raw_shift = self._get_shift_after_next_raw_shift(user_id_str, current_date_obj)

                            # Regelprüfungen (Hard und Soft)
                            if user_dog and user_dog != '---' and user_dog in existing_dog_assignments and any(
                                    self._check_time_overlap_optimized(shift_abbrev, a['shift']) for a in
                                    existing_dog_assignments[user_dog]): skip_reason = "Dog Time Conflict"
                            if not skip_reason and prev_shift == "N." and shift_abbrev in ["T.",
                                                                                           "6"]: skip_reason = f"N->{shift_abbrev} Conflict"
                            if not skip_reason and shift_abbrev == "T." and one_day_ago_raw_shift in self.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T Conflict"

                            if not skip_reason and shift_abbrev in user_pref.get('shift_exclusions', []):
                                skip_reason = f"User Excludes '{shift_abbrev}'"

                            consecutive_days = self._count_consecutive_shifts(user_id_str, current_date_obj) # Wird mehrfach gebraucht
                            if not skip_reason and consecutive_days >= SOFT_MAX_CONSECUTIVE_SHIFTS:
                                skip_reason = f"Max Consecutive (Soft Limit: {consecutive_days})"

                            if not skip_reason and self.mandatory_rest_days > 0 and consecutive_days == 0:
                                if not self._check_mandatory_rest(user_id_str, current_date_obj):
                                    skip_reason = f"Mandatory Rest Violated ({self.mandatory_rest_days} days needed)"

                            if not skip_reason and date_str in self.wunschfrei_requests.get(user_id_str, {}):
                                wf_status, wf_shift = self.wunschfrei_requests[user_id_str][date_str]
                                if wf_shift in ["", shift_abbrev] and self.wunschfrei_respect_level >= 50: # Check Respekt-Level
                                    skip_reason = f"Wunschfrei (Respect Level {self.wunschfrei_respect_level})"

                            limit = max_same_shift_override if max_same_shift_override is not None else self.max_consecutive_same_shift_limit
                            if not skip_reason:
                                consecutive_same = self._count_consecutive_same_shifts(user_id_str, current_date_obj,
                                                                                       shift_abbrev)
                                if consecutive_same >= limit: skip_reason = f"Max Same '{shift_abbrev}' ({consecutive_same})"

                            max_hours_check = max_hours_override if max_hours_override is not None else MAX_MONTHLY_HOURS
                            if not skip_reason and current_hours + hours_for_this_shift > max_hours_check:
                                skip_reason = f"User Max Hours ({current_hours:.1f}+{hours_for_this_shift:.1f}>{max_hours_check})"

                            is_isolated = False
                            if one_day_ago_raw_shift in self.free_shifts_indicators and \
                                    self._get_previous_raw_shift(user_id_str, two_days_ago_obj) in self.free_shifts_indicators and \
                                    next_raw_shift in self.free_shifts_indicators:
                                is_isolated = True
                            elif one_day_ago_raw_shift in self.free_shifts_indicators and \
                                    next_raw_shift in self.free_shifts_indicators and \
                                    after_next_raw_shift in self.free_shifts_indicators:
                                is_isolated = True

                            if skip_reason: skipped_reasons[skip_reason] += 1; continue

                            candidate_data = {
                                'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog,
                                'hours': current_hours, 'prev_shift': prev_shift,
                                'is_isolated': is_isolated, 'user_pref': user_pref
                            }
                            possible_candidates.append(candidate_data)
                            candidate_total_hours += current_hours;
                            num_available_candidates += 1

                        if not possible_candidates: print(
                            f"      -> No fair candidates found in search {search_attempts_fair}. Skipped: {dict(skipped_reasons)}"); break

                        # Schritt 1.2: Scores berechnen (mit Multiplikatoren)
                        average_hours = (candidate_total_hours / num_available_candidates) if num_available_candidates > 0 else 0.0
                        available_candidate_ids = {c['id'] for c in possible_candidates}

                        for candidate in possible_candidates:
                            candidate_id = candidate['id']

                            min_hours_pref = candidate['user_pref'].get('min_monthly_hours')
                            candidate['min_hours_score'] = 0
                            if min_hours_pref is not None:
                                hours_to_min = min_hours_pref - candidate['hours']
                                if hours_to_min > self.min_hours_fairness_threshold:
                                    # KORRIGIERT: Anwendung des MinHrsScore Multiplikators
                                    candidate['min_hours_score'] = self.min_hours_score_multiplier
                                elif hours_to_min > 0: candidate['min_hours_score'] = 1

                            hours_diff = average_hours - candidate['hours']
                            candidate['fairness_score'] = 0
                            if hours_diff > self.fairness_threshold_hours:
                                # KORRIGIERT: Anwendung des FairnessScore Multiplikators
                                candidate['fairness_score'] = self.fairness_score_multiplier

                            candidate['partner_score'] = 1000
                            if candidate_id in self.partner_priority_map:
                                for prio, partner_id in self.partner_priority_map[candidate_id]:
                                    if partner_id in available_candidate_ids:
                                        candidate['partner_score'] = prio; break
                                    elif partner_id in assignments_today_by_shift.get(shift_abbrev, set()):
                                        candidate['partner_score'] = 100 + prio; break

                            # KORRIGIERT: Anwendung des IsolationScore Multiplikators
                            candidate['isolation_score'] = candidate.get('is_isolated', False) * self.isolation_score_multiplier

                            candidate['ratio_pref_score'] = 0
                            scale_pref = candidate['user_pref'].get('ratio_preference_scale', 50)
                            if scale_pref != 50:
                                t_or_6_count = live_shift_counts_ratio[candidate_id].get('T_OR_6', 0)
                                n_dot_count = live_shift_counts_ratio[candidate_id].get('N_DOT', 0)
                                total_tn = t_or_6_count + n_dot_count
                                current_ratio_t = 0.5 if total_tn == 0 else t_or_6_count / total_tn
                                target_ratio_t = scale_pref / 100.0
                                ratio_deviation = current_ratio_t - target_ratio_t
                                is_day_shift = shift_abbrev in ['T.', '6']; is_night_shift = shift_abbrev == 'N.'
                                if is_day_shift:
                                    if target_ratio_t > 0.5 and ratio_deviation < 0: candidate['ratio_pref_score'] = -1 * abs(ratio_deviation) * 2
                                    elif target_ratio_t < 0.5 and ratio_deviation > 0: candidate['ratio_pref_score'] = abs(ratio_deviation) * 2
                                elif is_night_shift:
                                    if target_ratio_t < 0.5 and ratio_deviation > 0: candidate['ratio_pref_score'] = -1 * abs(ratio_deviation) * 2
                                    elif target_ratio_t > 0.5 and ratio_deviation < 0: candidate['ratio_pref_score'] = abs(ratio_deviation) * 2

                        # Schritt 1.3: Kandidaten sortieren
                        possible_candidates.sort(
                            key=lambda x: (
                                x.get('partner_score', 1000),
                                -x.get('min_hours_score', 0),
                                -x.get('fairness_score', 0),
                                x.get('ratio_pref_score', 0),
                                x.get('isolation_score', 0),
                                0 if x['prev_shift'] == shift_abbrev else 1,
                                x['hours']
                            )
                        )

                        # Schritt 1.4: Besten Kandidaten auswählen und zuweisen
                        chosen_user = possible_candidates[0]
                        print(
                            f"      -> Trying User {chosen_user['id']} (PartnerScore={chosen_user.get('partner_score', 1000)}, MinHrsScore={chosen_user.get('min_hours_score', 0)}, FairScore={chosen_user.get('fairness_score', 0)}, RatioScore={chosen_user.get('ratio_pref_score', 0):.2f}, IsoScore={chosen_user.get('isolation_score', 0)}, Block={chosen_user['prev_shift'] == shift_abbrev}, Hrs={chosen_user['hours']:.1f})")

                        success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)

                        if success:
                            save_count += 1;
                            assigned_count_this_shift_loop += 1
                            user_id_int = chosen_user['id'];
                            user_id_str = chosen_user['id_str'];
                            user_dog = chosen_user['dog']
                            if user_id_str not in self.live_shifts_data: self.live_shifts_data[user_id_str] = {}
                            self.live_shifts_data[user_id_str][date_str] = shift_abbrev
                            users_unavailable_today.add(user_id_str);
                            assignments_today_by_shift[shift_abbrev].add(user_id_int)
                            if user_dog and user_dog != '---': existing_dog_assignments[user_dog].append({'user_id': user_id_int, 'shift': shift_abbrev})
                            hours_added = self.shift_hours.get(shift_abbrev, 0.0);
                            live_user_hours[user_id_int] += hours_added
                            if shift_abbrev == 'T.' or shift_abbrev == '6': live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1
                            if shift_abbrev == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1
                            live_shift_counts[user_id_int][shift_abbrev] += 1
                        else:
                            print(f"      -> Fair DB ERROR for User {chosen_user['id']}: {msg}")
                            users_unavailable_today.add(chosen_user['id_str'])

                    # --- Runden 2, 3 und 4 ---
                    current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()))
                    needed_after_fair = required_count - current_assigned_count

                    # Runde 2: Auffüllen (Standard Hard Rules)
                    if needed_after_fair > 0:
                        print(f"      -> Still need {needed_after_fair} (Runde 2: Standard Fill)...")
                        assigned_in_round_2 = self._run_fill_round(shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments, assignments_today_by_shift, live_user_hours, live_shift_counts, live_shift_counts_ratio, needed_after_fair, round_num=2)
                        assigned_count_this_shift_loop += assigned_in_round_2
                        save_count += assigned_in_round_2
                        current_assigned_count += assigned_in_round_2 # Aktualisiere Gesamtzahl

                    # Runde 3: Auffüllen (N-F-T gelockert)
                    needed_after_round_2 = required_count - current_assigned_count
                    if needed_after_round_2 > 0:
                        print(f"      -> Still need {needed_after_round_2} (Runde 3: Relax N-F-T)...")
                        assigned_in_round_3 = self._run_fill_round(shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments, assignments_today_by_shift, live_user_hours, live_shift_counts, live_shift_counts_ratio, needed_after_round_2, round_num=3)
                        assigned_count_this_shift_loop += assigned_in_round_3
                        save_count += assigned_in_round_3
                        current_assigned_count += assigned_in_round_3 # Aktualisiere Gesamtzahl

                    # Runde 4: Auffüllen (Mandatory Rest gelockert)
                    needed_after_round_3 = required_count - current_assigned_count
                    if needed_after_round_3 > 0:
                        print(f"      -> Still need {needed_after_round_3} (Runde 4: Relax Mandatory Rest)...")
                        assigned_in_round_4 = self._run_fill_round(shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments, assignments_today_by_shift, live_user_hours, live_shift_counts, live_shift_counts_ratio, needed_after_round_3, round_num=4)
                        assigned_count_this_shift_loop += assigned_in_round_4
                        save_count += assigned_in_round_4
                        current_assigned_count += assigned_in_round_4 # Aktualisiere Gesamtzahl

                    # Endgültige Prüfung nach allen Runden
                    final_assigned_count = current_assigned_count
                    if final_assigned_count < required_count:
                        print(f"   -> [WARNUNG] Mindestbesetzung für '{shift_abbrev}' an {date_str} NICHT erreicht (Req: {required_count}, Assigned: {final_assigned_count}).")

            # Abschluss nach allen Tagen
            self._update_progress(100, "Generierung abgeschlossen.")
            final_hours_list = sorted(live_user_hours.items(), key=lambda item: item[1], reverse=True)
            print("Finale (geschätzte) Stunden nach Generierung:", [(uid, f"{h:.2f}") for uid, h in final_hours_list])
            print("Finale Schichtzählungen (T./N./6):")
            for user_id_int in sorted(live_user_hours.keys()):
                counts = live_shift_counts[user_id_int]
                print(f"  User {user_id_int}: T:{counts.get('T.', 0)}, N:{counts.get('N.', 0)}, 6:{counts.get('6', 0)}")

            if self.completion_callback:
                self.app.after(100, lambda sc=save_count: self.completion_callback(True, sc, None))

        except Exception as e:
            print(f"Fehler im Generierungs-Thread: {e}")
            traceback.print_exc()
            if self.completion_callback:
                error_msg = f"Ein Fehler ist aufgetreten:\n{e}"
                self.app.after(100, lambda: self.completion_callback(False, 0, error_msg))


    def _run_fill_round(self, shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                        assignments_today_by_shift, live_user_hours, live_shift_counts, live_shift_counts_ratio,
                        needed, round_num):
        """ Führt eine Auffüllrunde mit spezifischen Regel-Lockerungen durch. """

        assigned_count = 0
        search_attempts = 0
        date_str = current_date_obj.strftime('%Y-%m-%d')
        prev_date_obj = current_date_obj - timedelta(days=1)
        two_days_ago_obj = current_date_obj - timedelta(days=2)

        # Schleife, bis Bedarf gedeckt ist oder keine Kandidaten mehr da sind
        while assigned_count < needed and search_attempts < len(self.all_users) + 1:
            search_attempts += 1
            possible_fill_candidates = []

            # Kandidaten sammeln (nur Hard Rules prüfen, mit Lockerungen je Runde)
            for user_dict in self.all_users:
                user_id_int = user_dict.get('id');
                if user_id_int is None: continue
                user_id_str = str(user_id_int)
                if user_id_str in users_unavailable_today: continue

                user_dog = user_dict.get('diensthund');
                current_hours = live_user_hours.get(user_id_int, 0.0);
                hours_for_this_shift = self.shift_hours.get(shift_abbrev, 0.0)
                skip_reason = None

                user_pref = self.user_preferences[user_id_str]
                max_hours_override = user_pref.get('max_monthly_hours')

                prev_shift = self._get_previous_shift(user_id_str, prev_date_obj);
                one_day_ago_raw_shift = self._get_previous_raw_shift(user_id_str, prev_date_obj);
                two_days_ago_shift = self._get_previous_shift(user_id_str, two_days_ago_obj)

                # --- Hard Rules Prüfung (mit Lockerungen je Runde) ---

                # Hundekonflikt (Immer Hard Rule)
                if user_dog and user_dog != '---' and user_dog in existing_dog_assignments and any(
                        self._check_time_overlap_optimized(shift_abbrev, a['shift']) for a in
                        existing_dog_assignments[user_dog]):
                    skip_reason = "Dog Time Conflict"

                # N -> T/6 Konflikt (Immer Hard Rule)
                if not skip_reason and prev_shift == "N." and shift_abbrev in ["T.", "6"]:
                    skip_reason = f"N->{shift_abbrev} Conflict"

                # N-F-T Konflikt (Wird in Runde 3+ gelockert)
                if round_num <= 2:  # Nur in Runde 2 prüfen
                    if not skip_reason and shift_abbrev == "T." and one_day_ago_raw_shift in self.free_shifts_indicators and two_days_ago_shift == "N.":
                        skip_reason = "N-F-T Conflict"

                # Schicht-Ausschluss (Immer Hard Rule)
                if not skip_reason and shift_abbrev in user_pref.get('shift_exclusions', []):
                    skip_reason = f"User Excludes '{shift_abbrev}' (Hard)"

                # Max Consecutive Shifts (HARD LIMIT, evtl. gelockert durch avoid_understaffing_hard)
                if not skip_reason:
                    consecutive_days = self._count_consecutive_shifts(user_id_str, current_date_obj)
                    limit = HARD_MAX_CONSECUTIVE_SHIFTS if self.avoid_understaffing_hard else SOFT_MAX_CONSECUTIVE_SHIFTS
                    if consecutive_days >= limit:
                        skip_reason = f"Max Consecutive ({consecutive_days}) - Hard Stop (Limit: {limit})"

                # Mandatory Rest Check (Wird in Runde 4+ gelockert)
                if round_num <= 3:  # Nur in Runde 2 und 3 prüfen
                    if not skip_reason and self.mandatory_rest_days > 0 and consecutive_days == 0:  # Prüfe nur wenn Kette nicht verlängert wird
                        if not self._check_mandatory_rest(user_id_str, current_date_obj):
                            skip_reason = f"Mandatory Rest Violated ({self.mandatory_rest_days} days needed) (Hard)"

                # Max Stunden (Immer Hard Rule)
                max_hours_check = max_hours_override if max_hours_override is not None else MAX_MONTHLY_HOURS
                if not skip_reason and current_hours + hours_for_this_shift > max_hours_check:
                    skip_reason = f"User Max Hours ({current_hours:.1f}+{hours_for_this_shift:.1f}>{max_hours_check}) (Hard)"

                if skip_reason: continue
                # Gültiger Kandidat für diese Fill-Runde
                possible_fill_candidates.append(
                    {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours})

            if not possible_fill_candidates:
                print(f"         -> No fill candidates found in Runde {round_num}, search {search_attempts}.");
                break  # Keine Kandidaten mehr für diese Runde

            # Kandidaten sortieren (nur nach Stunden)
            possible_fill_candidates.sort(key=lambda x: x['hours'])

            # Besten auswählen und zuweisen
            chosen_user = possible_fill_candidates[0]
            success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)
            if success:
                assigned_count += 1
                user_id_int = chosen_user['id'];
                user_id_str = chosen_user['id_str'];
                user_dog = chosen_user['dog']
                # Live-Daten aktualisieren
                if user_id_str not in self.live_shifts_data: self.live_shifts_data[user_id_str] = {}
                self.live_shifts_data[user_id_str][date_str] = shift_abbrev
                users_unavailable_today.add(user_id_str);
                assignments_today_by_shift[shift_abbrev].add(user_id_int)
                if user_dog and user_dog != '---': existing_dog_assignments[user_dog].append(
                    {'user_id': user_id_int, 'shift': shift_abbrev})
                hours_added = self.shift_hours.get(shift_abbrev, 0.0);
                live_user_hours[user_id_int] += hours_added
                if shift_abbrev == 'T.' or shift_abbrev == '6': live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1
                if shift_abbrev == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1
                live_shift_counts[user_id_int][shift_abbrev] += 1
                print(
                    f"         -> Fill OK (Runde {round_num}): User {chosen_user['id']} gets '{shift_abbrev}'. H:{live_user_hours[user_id_int]:.2f}")
            else:
                print(f"         -> Fill DB ERROR (Runde {round_num}) for User {chosen_user['id']}: {msg}")
                users_unavailable_today.add(chosen_user['id_str'])  # User trotzdem blockieren

        return assigned_count  # Gibt die Anzahl der in dieser Runde zugewiesenen Schichten zurück