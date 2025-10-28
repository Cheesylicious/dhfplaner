# gui/shift_plan_generator.py
import calendar
import threading
from collections import defaultdict
from datetime import date, timedelta, datetime, time
import math
import traceback

# Annahme: DataManager ist importierbar oder über app erreichbar
try:
    from gui.shift_plan_data_manager import ShiftPlanDataManager
except ImportError:
    ShiftPlanDataManager = None  # Fallback

from database.db_shifts import save_shift_entry

# Imports für ausgelagerte Logik
from .generator.generator_helpers import GeneratorHelpers
from .generator.generator_scoring import GeneratorScoring
from .generator.generator_rounds import GeneratorRounds

# Konstanten
MAX_MONTHLY_HOURS = 228.0
SOFT_MAX_CONSECUTIVE_SHIFTS = 6
HARD_MAX_CONSECUTIVE_SHIFTS = 8
DEFAULT_MANDATORY_REST_DAYS = 2
DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT = 4
# --- Parameter für Kritikalität ---
CRITICAL_LOOKAHEAD_DAYS = 14
CRITICAL_BUFFER = 1  # Zurück auf 1 für die Vorfilterung
# --- ENDE Parameter ---


# Standardwerte für Scores
DEFAULT_FAIRNESS_THRESHOLD_HOURS = 10.0
DEFAULT_MIN_HOURS_FAIRNESS_THRESHOLD = 20.0
DEFAULT_MIN_HOURS_SCORE_MULT = 5.0
DEFAULT_FAIRNESS_SCORE_MULT = 1.0
DEFAULT_ISOLATION_SCORE_MULT = 30.0
DEFAULT_WUNSCHFREI_RESPECT = 75
DEFAULT_GENERATOR_FILL_ROUNDS = 3
LOOKAHEAD_PENALTY_SCORE = 500


class ShiftPlanGenerator:
    """
    Kapselt die Logik zur automatischen Generierung des Schichtplans.
    Orchestriert die Helfer, Scoring- und Runden-Logik.
    Implementiert Pre-Planning mit dynamischer Kritikalitätsprüfung.
    """

    def __init__(self, app, data_manager, year, month, all_users, user_data_map,
                 vacation_requests, wunschfrei_requests, live_shifts_data,
                 holidays_in_month, progress_callback, completion_callback):
        self.app = app
        self.data_manager = data_manager
        self.year = year
        self.month = month
        self.all_users = all_users
        self.user_data_map = user_data_map
        self.vacation_requests = vacation_requests
        self.wunschfrei_requests = wunschfrei_requests
        self.initial_live_shifts_data = live_shifts_data
        self.live_shifts_data = {}
        self.holidays_in_month = holidays_in_month
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

        self.shifts_to_plan = ["6", "T.", "N."]
        self.shift_hours = {abbrev: float(data.get('hours', 0.0))
                            for abbrev, data in self.app.shift_types_data.items()}
        self.work_shifts = {s for s, data in self.app.shift_types_data.items() if
                            float(data.get('hours', 0.0)) > 0 and s not in ['U', 'EU']}
        self.work_shifts.update(['T.', 'N.', '6', '24'])
        self.free_shifts_indicators = {"", "FREI", "U", "X", "EU", "WF", "U?"}

        # Konstanten als Attribute
        self.MAX_MONTHLY_HOURS = MAX_MONTHLY_HOURS
        self.SOFT_MAX_CONSECUTIVE_SHIFTS = SOFT_MAX_CONSECUTIVE_SHIFTS
        self.HARD_MAX_CONSECUTIVE_SHIFTS = HARD_MAX_CONSECUTIVE_SHIFTS
        self.CRITICAL_LOOKAHEAD_DAYS = CRITICAL_LOOKAHEAD_DAYS
        self.CRITICAL_BUFFER = CRITICAL_BUFFER
        self.LOOKAHEAD_PENALTY_SCORE = LOOKAHEAD_PENALTY_SCORE

        # Generator-Konfiguration laden
        self.generator_config = {}
        if self.data_manager and hasattr(self.data_manager, 'get_generator_config'):
            try:
                self.generator_config = self.data_manager.get_generator_config()
            except Exception as e:
                print(f"[FEHLER] Konnte Generator-Konfiguration nicht laden: {e}")

        # Konfigurierbare Einstellungen laden
        self.max_consecutive_same_shift_limit = self.generator_config.get('max_consecutive_same_shift',
                                                                          DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT)
        self.mandatory_rest_days = self.generator_config.get('mandatory_rest_days_after_max_shifts',
                                                             DEFAULT_MANDATORY_REST_DAYS)
        self.avoid_understaffing_hard = self.generator_config.get('avoid_understaffing_hard', True)
        self.wunschfrei_respect_level = self.generator_config.get('wunschfrei_respect_level',
                                                                  DEFAULT_WUNSCHFREI_RESPECT)
        self.generator_fill_rounds = self.generator_config.get('generator_fill_rounds', DEFAULT_GENERATOR_FILL_ROUNDS)
        self.fairness_threshold_hours = self.generator_config.get('fairness_threshold_hours',
                                                                  DEFAULT_FAIRNESS_THRESHOLD_HOURS)
        self.min_hours_fairness_threshold = self.generator_config.get('min_hours_fairness_threshold',
                                                                      DEFAULT_MIN_HOURS_FAIRNESS_THRESHOLD)
        self.min_hours_score_multiplier = self.generator_config.get('min_hours_score_multiplier',
                                                                    DEFAULT_MIN_HOURS_SCORE_MULT)
        self.fairness_score_multiplier = self.generator_config.get('fairness_score_multiplier',
                                                                   DEFAULT_FAIRNESS_SCORE_MULT)
        self.isolation_score_multiplier = self.generator_config.get('isolation_score_multiplier',
                                                                    DEFAULT_ISOLATION_SCORE_MULT)

        # User Preferences
        default_user_pref = {'min_monthly_hours': None, 'max_monthly_hours': None, 'shift_exclusions': [],
                             'ratio_preference_scale': 50, 'max_consecutive_same_shift_override': None}
        raw_user_preferences = self.generator_config.get('user_preferences', {})
        self.user_preferences = defaultdict(lambda: default_user_pref.copy())
        for user_id_str, prefs in raw_user_preferences.items():
            if 'ratio_preference_scale' not in prefs: prefs['ratio_preference_scale'] = 50
            self.user_preferences[user_id_str].update(prefs)

        # Partner
        self.prioritized_partners_list = self.generator_config.get('preferred_partners_prioritized', [])
        self.partner_priority_map = defaultdict(list)
        for entry in self.prioritized_partners_list:
            try:
                id_a, id_b, prio = int(entry['id_a']), int(entry['id_b']), int(entry['priority']);
                self.partner_priority_map[id_a].append((prio, id_b)); self.partner_priority_map[id_b].append(
                    (prio, id_a))
            except (ValueError, KeyError, TypeError):
                continue
        for user_id in self.partner_priority_map: self.partner_priority_map[user_id].sort(key=lambda x: x[0])

        # Instanzen der ausgelagerten Logik
        self.helpers = GeneratorHelpers(self)
        self.scoring = GeneratorScoring(self)
        self.rounds = GeneratorRounds(self, self.helpers, self.scoring)

        # Potenzielle kritische Schichten identifizieren (Vorfilterung)
        self.potential_critical_shifts = self._identify_potential_critical_shifts()
        print(
            f"[Generator] Potenzielle kritische Schichten identifiziert (Lookahead={self.CRITICAL_LOOKAHEAD_DAYS}d, Puffer={self.CRITICAL_BUFFER}): {self.potential_critical_shifts if self.potential_critical_shifts else 'Keine'}")
        self.critical_shifts = set()

    def _update_progress(self, value, text):
        if self.progress_callback: self.progress_callback(value, text)

    def run_generation(self):
        self._generate()

    def _identify_potential_critical_shifts(self):
        """ Identifiziert potenziell kritische Schichten basierend auf dem Puffer. """
        potential_critical = set()
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        start_day = max(1, days_in_month - self.CRITICAL_LOOKAHEAD_DAYS + 1)
        print(f"  [Krit-Check Vorfilter] Prüfe Tage {start_day} bis {days_in_month}...")
        for day in range(start_day, days_in_month + 1):
            current_date_obj = date(self.year, self.month, day)
            date_str = current_date_obj.strftime('%Y-%m-%d')
            try:
                min_staffing_today = self.data_manager.get_min_staffing_for_date(current_date_obj)
                if not min_staffing_today: continue
            except Exception as staffing_err:
                min_staffing_today = {};
                print(f"[WARN] Staffing Error bei Krit-Vorfilter {date_str}: {staffing_err}");
                continue
            initial_availability_per_shift = defaultdict(int)
            for user_dict in self.all_users:
                user_id_int = user_dict.get('id');
                if user_id_int is None: continue
                user_id_str = str(user_id_int);
                user_pref = self.user_preferences[user_id_str]
                is_unavailable_day = False
                if self.vacation_requests.get(user_id_str, {}).get(current_date_obj) in ['Approved', 'Genehmigt']:
                    is_unavailable_day = True
                elif not is_unavailable_day and date_str in self.wunschfrei_requests.get(user_id_str, {}):
                    wf_entry = self.wunschfrei_requests[user_id_str][date_str]  # Hole Eintrag
                    wf_status, wf_shift = None, None
                    if isinstance(wf_entry, tuple) and len(wf_entry) >= 2: wf_status, wf_shift = wf_entry[0], wf_entry[
                        1]  # Entpacke sicher
                    if wf_status in ['Approved', 'Genehmigt',
                                     'Akzeptiert'] and wf_shift == "": is_unavailable_day = True  # Nur ganztägig blockiert hier
                if is_unavailable_day: continue
                for shift_abbrev in self.shifts_to_plan:
                    wf_blocks_this_shift = False
                    if date_str in self.wunschfrei_requests.get(user_id_str, {}):
                        wf_entry = self.wunschfrei_requests[user_id_str][date_str]  # Hole Eintrag
                        wf_status, wf_shift = None, None
                        if isinstance(wf_entry, tuple) and len(wf_entry) >= 2: wf_status, wf_shift = wf_entry[0], \
                        wf_entry[1]  # Entpacke sicher
                        if wf_status in ['Approved', 'Genehmigt',
                                         'Akzeptiert'] and wf_shift == shift_abbrev: wf_blocks_this_shift = True  # Blockiert nur diese Schicht
                    is_excluded = shift_abbrev in user_pref.get('shift_exclusions', [])
                    if not wf_blocks_this_shift and not is_excluded:
                        initial_availability_per_shift[shift_abbrev] += 1
            for shift_abbrev in self.shifts_to_plan:
                required = min_staffing_today.get(shift_abbrev, 0)
                if required > 0:
                    available = initial_availability_per_shift[shift_abbrev]
                    if available <= required + self.CRITICAL_BUFFER:
                        potential_critical.add((current_date_obj, shift_abbrev))
                        print(
                            f"  [Krit-Check Vorfilter {date_str}-{shift_abbrev}] Potenziell Kritisch! Benötigt: {required}, Verfügbar: {available}, Puffer: {self.CRITICAL_BUFFER}")
        return potential_critical

    # --- _get_actually_available_count MIT DETAILLIERTEM LOGGING ---
    def _get_actually_available_count(self, target_date_obj, target_shift_abbrev):
        """ Zählt, wie viele Mitarbeiter *aktuell* die Ziels-Schicht machen könnten. """
        count = 0
        date_str = target_date_obj.strftime('%Y-%m-%d')
        print(f"    [DynCheck Detail {date_str}-{target_shift_abbrev}] Starte Zählung...")  # DEBUG START

        users_unavailable_on_target_day = set()
        occupied_dogs = defaultdict(list)
        unavailable_reasons = {}  # DEBUG: Speichert Gründe

        # Status Quo für den Zielt-Tag sammeln
        for uid_str, day_data in self.live_shifts_data.items():
            if date_str in day_data:
                shift = day_data[date_str]
                if shift and shift not in self.free_shifts_indicators:
                    users_unavailable_on_target_day.add(uid_str);
                    unavailable_reasons[uid_str] = f"Hat Schicht {shift}"  # DEBUG
                    uid_int = int(uid_str);
                    user_dog = self.user_data_map.get(uid_int, {}).get('diensthund');
                    if user_dog and user_dog != '---': occupied_dogs[user_dog].append(
                        {'user_id': uid_int, 'shift': shift})
            if self.vacation_requests.get(uid_str, {}).get(target_date_obj) in ['Approved', 'Genehmigt']:
                users_unavailable_on_target_day.add(uid_str);
                unavailable_reasons[uid_str] = "Urlaub"  # DEBUG
            elif date_str in self.wunschfrei_requests.get(uid_str, {}):
                wf_entry = self.wunschfrei_requests[uid_str][date_str]
                wf_status, wf_shift = None, None
                if isinstance(wf_entry, tuple) and len(wf_entry) >= 2: wf_status, wf_shift = wf_entry[0], wf_entry[1]
                if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert']:
                    if wf_shift == "":
                        users_unavailable_on_target_day.add(uid_str); unavailable_reasons[uid_str] = "WF(Tag)"  # DEBUG
                    elif wf_shift == target_shift_abbrev:
                        users_unavailable_on_target_day.add(uid_str); unavailable_reasons[
                            uid_str] = f"WF({target_shift_abbrev})"  # DEBUG

        # Jeden Mitarbeiter gegen harte Regeln prüfen
        for user_dict in self.all_users:
            user_id_int = user_dict.get('id');
            if user_id_int is None: continue
            user_id_str = str(user_id_int)

            if user_id_str in users_unavailable_on_target_day:
                print(
                    f"      - User {user_id_str}: Nicht verfügbar ({unavailable_reasons.get(user_id_str, 'Unbekannt')})")  # DEBUG
                continue

            user_pref = self.user_preferences[user_id_str];
            user_dog = user_dict.get('diensthund');
            current_hours = self.live_user_hours.get(user_id_int, 0.0);
            hours_for_this_shift = self.shift_hours.get(target_shift_abbrev, 0.0);
            max_hours_override = user_pref.get('max_monthly_hours');
            skip_reason = None;
            prev_date_obj = target_date_obj - timedelta(days=1);
            two_days_ago_obj = target_date_obj - timedelta(days=2);
            prev_shift = self.helpers.get_previous_shift(user_id_str, prev_date_obj);
            one_day_ago_raw_shift = self.helpers.get_previous_raw_shift(user_id_str, prev_date_obj);
            two_days_ago_shift = self.helpers.get_previous_shift(user_id_str, two_days_ago_obj)

            # Harte Regeln
            if user_dog and user_dog != '---' and user_dog in occupied_dogs and any(
                self.helpers.check_time_overlap_optimized(target_shift_abbrev, a['shift']) for a in
                occupied_dogs[user_dog]): skip_reason = "Dog"
            if not skip_reason and prev_shift == "N." and target_shift_abbrev in ["T.", "6"]: skip_reason = "N->T/6"
            if not skip_reason and target_shift_abbrev == "T." and one_day_ago_raw_shift in self.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T"
            if not skip_reason and target_shift_abbrev in user_pref.get('shift_exclusions',
                                                                        []): skip_reason = f"Excl({target_shift_abbrev})"
            consecutive_days = 0
            if not skip_reason: consecutive_days = self.helpers.count_consecutive_shifts(user_id_str, target_date_obj);
            if consecutive_days >= self.HARD_MAX_CONSECUTIVE_SHIFTS: skip_reason = f"MaxCons({consecutive_days})"
            if not skip_reason and self.mandatory_rest_days > 0 and consecutive_days == 0 and not self.helpers.check_mandatory_rest(
                user_id_str, target_date_obj): skip_reason = f"Rest({self.mandatory_rest_days}d)"
            max_hours_check = max_hours_override if max_hours_override is not None else self.MAX_MONTHLY_HOURS
            if not skip_reason and current_hours + hours_for_this_shift > max_hours_check: skip_reason = f"MaxHrs({current_hours:.1f}+{hours_for_this_shift:.1f}>{max_hours_check})"

            if not skip_reason:
                count += 1
                print(f"      + User {user_id_str}: Verfügbar (Stunden: {current_hours:.1f})")  # DEBUG
            else:
                print(
                    f"      - User {user_id_str}: Nicht verfügbar ({skip_reason}) (Stunden: {current_hours:.1f})")  # DEBUG

        print(f"    [DynCheck Detail {date_str}-{target_shift_abbrev}] Zählung Ende: {count}")  # DEBUG ENDE
        return count

    # _pre_plan_critical_shift Methode bleibt unverändert
    def _pre_plan_critical_shift(self, critical_date_obj, critical_shift_abbrev, needed_count,
                                 live_user_hours, live_shift_counts, live_shift_counts_ratio):
        """ Versucht, EINE kritische Schicht zu füllen (Hard Rules + niedrigste Stunden). """
        assigned_count = 0;
        search_attempts = 0;
        date_str = critical_date_obj.strftime('%Y-%m-%d')
        print(f"    [Pre-Plan] Fülle {critical_shift_abbrev} am {date_str} (benötigt: {needed_count})")
        users_unavailable_this_call = set();
        assignments_on_critical_date = defaultdict(set);
        dogs_assigned_on_critical_date = defaultdict(list)
        for uid_str, day_data in self.live_shifts_data.items():  # Status Quo für diesen Tag holen
            if date_str in day_data:
                shift = day_data[date_str]
                if shift and shift not in self.free_shifts_indicators: uid_int = int(uid_str);
                assignments_on_critical_date[shift].add(uid_int); users_unavailable_this_call.add(
                    uid_str); user_dog = self.user_data_map.get(uid_int, {}).get('diensthund');
                if user_dog and user_dog != '---': dogs_assigned_on_critical_date[user_dog].append(
                    {'user_id': uid_int, 'shift': shift})
            if self.vacation_requests.get(uid_str, {}).get(critical_date_obj) in ['Approved', 'Genehmigt']:
                users_unavailable_this_call.add(uid_str)
            elif date_str in self.wunschfrei_requests.get(uid_str, {}):
                wf_entry = self.wunschfrei_requests[uid_str][date_str]
                wf_status, wf_shift = None, None
                if isinstance(wf_entry, tuple) and len(wf_entry) >= 2: wf_status, wf_shift = wf_entry[0], wf_entry[1]
                if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert'] and (
                        wf_shift == "" or wf_shift == critical_shift_abbrev): users_unavailable_this_call.add(uid_str)

        while assigned_count < needed_count and search_attempts < len(
                self.all_users) + 1:  # Kandidaten suchen und zuweisen
            search_attempts += 1;
            possible_candidates = []
            for user_dict in self.all_users:  # Harte Regeln prüfen...
                user_id_int = user_dict.get('id');
                if user_id_int is None: continue
                user_id_str = str(user_id_int)
                if user_id_str in users_unavailable_this_call: continue
                user_pref = self.user_preferences[user_id_str];
                user_dog = user_dict.get('diensthund');
                current_hours = live_user_hours.get(user_id_int, 0.0);
                hours_for_this_shift = self.shift_hours.get(critical_shift_abbrev, 0.0);
                max_hours_override = user_pref.get('max_monthly_hours');
                skip_reason = None;
                prev_date_obj = critical_date_obj - timedelta(days=1);
                two_days_ago_obj = critical_date_obj - timedelta(days=2);
                prev_shift = self.helpers.get_previous_shift(user_id_str, prev_date_obj);
                one_day_ago_raw_shift = self.helpers.get_previous_raw_shift(user_id_str, prev_date_obj);
                two_days_ago_shift = self.helpers.get_previous_shift(user_id_str, two_days_ago_obj)
                if user_dog and user_dog != '---' and user_dog in dogs_assigned_on_critical_date and any(
                    self.helpers.check_time_overlap_optimized(critical_shift_abbrev, a['shift']) for a in
                    dogs_assigned_on_critical_date[user_dog]): skip_reason = "Dog"
                if not skip_reason and prev_shift == "N." and critical_shift_abbrev in ["T.",
                                                                                        "6"]: skip_reason = "N->T/6"
                if not skip_reason and critical_shift_abbrev == "T." and one_day_ago_raw_shift in self.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T"
                if not skip_reason and critical_shift_abbrev in user_pref.get('shift_exclusions',
                                                                              []): skip_reason = "Excl"
                consecutive_days = 0
                if not skip_reason: consecutive_days = self.helpers.count_consecutive_shifts(user_id_str,
                                                                                             critical_date_obj);
                if consecutive_days >= self.HARD_MAX_CONSECUTIVE_SHIFTS: skip_reason = "MaxCons"
                if not skip_reason and self.mandatory_rest_days > 0 and consecutive_days == 0 and not self.helpers.check_mandatory_rest(
                    user_id_str, critical_date_obj): skip_reason = "Rest"
                max_hours_check = max_hours_override if max_hours_override is not None else self.MAX_MONTHLY_HOURS
                if not skip_reason and current_hours + hours_for_this_shift > max_hours_check: skip_reason = "MaxHrs"
                if skip_reason: continue
                possible_candidates.append(
                    {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours})
            if not possible_candidates: print(
                f"      [Pre-Plan] Keine Kandidaten in Versuch {search_attempts} für {critical_shift_abbrev} am {date_str}."); break
            possible_candidates.sort(key=lambda x: x['hours']);
            chosen_user = possible_candidates[0]
            success, msg = save_shift_entry(chosen_user['id'], date_str, critical_shift_abbrev)  # Speichern
            if success:  # Live-Daten updaten
                assigned_count += 1;
                user_id_int = chosen_user['id'];
                user_id_str = chosen_user['id_str'];
                user_dog = chosen_user['dog']
                if user_id_str not in self.live_shifts_data: self.live_shifts_data[user_id_str] = {}
                self.live_shifts_data[user_id_str][date_str] = critical_shift_abbrev;
                users_unavailable_this_call.add(user_id_str);
                hours_added = self.shift_hours.get(critical_shift_abbrev, 0.0);
                live_user_hours[user_id_int] += hours_added;
                if critical_shift_abbrev in ['T.', '6']: live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1;
                if critical_shift_abbrev == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1;
                live_shift_counts[user_id_int][critical_shift_abbrev] += 1; print(
                    f"      [Pre-Plan] OK: User {user_id_int} -> {critical_shift_abbrev} @ {date_str}. (Hrs: {live_user_hours[user_id_int]:.1f})")
                if user_dog and user_dog != '---': dogs_assigned_on_critical_date[user_dog].append(
                    {'user_id': user_id_int, 'shift': critical_shift_abbrev})
            else:
                print(f"      [Pre-Plan] DB ERROR User {chosen_user['id']}: {msg}"); users_unavailable_this_call.add(
                    chosen_user['id_str'])
        return assigned_count

    # _generate Methode bleibt unverändert zum vorherigen Vorschlag
    def _generate(self):
        """ Führt die eigentliche Generierungslogik aus (jetzt OHNE Pre-Planning). """
        try:
            self._update_progress(0, "Initialisiere Planung...")
            days_in_month = calendar.monthrange(self.year, self.month)[1]

            # --- Initialisierung der Live-Daten ---
            self.live_shifts_data = defaultdict(dict)
            for user_id_str, day_data in self.initial_live_shifts_data.items():
                self.live_shifts_data[user_id_str] = day_data.copy()
            self.live_user_hours = defaultdict(float)
            live_shift_counts = defaultdict(lambda: defaultdict(int))
            live_shift_counts_ratio = defaultdict(lambda: defaultdict(int))
            for user_id_str, day_data in self.live_shifts_data.items():
                try:
                    user_id_int = int(user_id_str)
                except ValueError:
                    continue
                if user_id_int not in self.user_data_map: continue
                for date_str, shift in day_data.items():
                    try:
                        shift_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        continue
                    if shift_date_obj.year != self.year or shift_date_obj.month != self.month: continue
                    hours = self.shift_hours.get(shift, 0.0)
                    if hours > 0: self.live_user_hours[user_id_int] += hours
                    if shift in ['T.', '6']: live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1
                    if shift == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1
                    if shift in self.shifts_to_plan: live_shift_counts[user_id_int][shift] += 1
            # --- Ende Initialisierung ---

            save_count = 0
            # --- KEINE PRE-PLANNING PHASE MEHR ---
            self._update_progress(10, "Starte Hauptplanung...")  # Start bei 10%

            total_steps = days_in_month * len(self.shifts_to_plan)
            current_step = 0

            # Hauptschleife: Tage
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')
                users_unavailable_today = set();
                existing_dog_assignments = defaultdict(list);
                assignments_today_by_shift = defaultdict(set)
                # VORDURCHLAUF (unverändert)
                for user_id_int, user_data in self.user_data_map.items():
                    user_id_str = str(user_id_int);
                    user_dog = user_data.get('diensthund');
                    is_unavailable, is_working = False, False
                    if self.vacation_requests.get(user_id_str, {}).get(current_date_obj) in ['Approved', 'Genehmigt']:
                        is_unavailable = True
                    elif date_str in self.wunschfrei_requests.get(user_id_str, {}):
                        wf_entry = self.wunschfrei_requests[user_id_str][date_str]
                        wf_status, wf_shift = None, None
                        if isinstance(wf_entry, tuple) and len(wf_entry) >= 1: wf_status = wf_entry[0]
                        if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert']: is_unavailable = True
                    existing_shift = self.live_shifts_data.get(user_id_str, {}).get(date_str)
                    if existing_shift and existing_shift not in self.free_shifts_indicators: is_working = True;
                    assignments_today_by_shift[existing_shift].add(user_id_int)
                    if is_unavailable or is_working: users_unavailable_today.add(user_id_str)
                    if is_working and user_dog and user_dog != '---': existing_dog_assignments[user_dog].append(
                        {'user_id': user_id_int, 'shift': existing_shift})
                # Mindestbesetzung
                try:
                    min_staffing_today = self.data_manager.get_min_staffing_for_date(current_date_obj)
                except Exception as staffing_err:
                    min_staffing_today = {}; print(f"[WARN] Staffing Error {date_str}: {staffing_err}")
                # Schleife: Schichten
                for shift_abbrev in self.shifts_to_plan:
                    current_step += 1;
                    progress_perc = int(10 + (current_step / total_steps) * 90);
                    self._update_progress(progress_perc, f"Plane {shift_abbrev} für {date_str}...")  # Skala 10-100%
                    is_friday_6 = shift_abbrev == '6' and current_date_obj.weekday() == 4;
                    is_holiday_6 = shift_abbrev == '6' and current_date_obj in self.holidays_in_month
                    if shift_abbrev == '6' and not (is_friday_6 or is_holiday_6): continue
                    required_count = min_staffing_today.get(shift_abbrev, 0);
                    if required_count <= 0: continue
                    current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()));
                    needed_now = required_count - current_assigned_count
                    if needed_now <= 0: continue
                    print(
                        f"   -> Need {needed_now} for '{shift_abbrev}' @ {date_str} (Req:{required_count}, Has:{current_assigned_count})")  # "incl. Pre-Plan" entfernt
                    # Runde 1 (Aufruf ohne critical_shifts)
                    assigned_in_round_1 = self.rounds.run_fair_assignment_round(shift_abbrev, current_date_obj,
                                                                                users_unavailable_today,
                                                                                existing_dog_assignments,
                                                                                assignments_today_by_shift,
                                                                                self.live_user_hours, live_shift_counts,
                                                                                live_shift_counts_ratio, needed_now,
                                                                                days_in_month)  # critical_shifts entfernt
                    save_count += assigned_in_round_1
                    # Runden 2, 3, 4 (unverändert)
                    current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()));
                    needed_after_fair = required_count - current_assigned_count
                    if needed_after_fair > 0 and self.generator_fill_rounds >= 1: assigned_in_round_2 = self.rounds.run_fill_round(
                        shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                        assignments_today_by_shift, self.live_user_hours, live_shift_counts, live_shift_counts_ratio,
                        needed_after_fair,
                        round_num=2); save_count += assigned_in_round_2; current_assigned_count += assigned_in_round_2
                    needed_after_round_2 = required_count - current_assigned_count
                    if needed_after_round_2 > 0 and self.generator_fill_rounds >= 2: assigned_in_round_3 = self.rounds.run_fill_round(
                        shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                        assignments_today_by_shift, self.live_user_hours, live_shift_counts, live_shift_counts_ratio,
                        needed_after_round_2,
                        round_num=3); save_count += assigned_in_round_3; current_assigned_count += assigned_in_round_3
                    needed_after_round_3 = required_count - current_assigned_count
                    if needed_after_round_3 > 0 and self.generator_fill_rounds >= 3: assigned_in_round_4 = self.rounds.run_fill_round(
                        shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                        assignments_today_by_shift, self.live_user_hours, live_shift_counts, live_shift_counts_ratio,
                        needed_after_round_3,
                        round_num=4); save_count += assigned_in_round_4; current_assigned_count += assigned_in_round_4
                    # Endgültige Prüfung
                    final_assigned_count = current_assigned_count
                    if final_assigned_count < required_count: print(
                        f"   -> [WARNUNG] Mindestbesetzung für '{shift_abbrev}' an {date_str} NICHT erreicht (Req: {required_count}, Assigned: {final_assigned_count}).")
            # Abschluss
            self._update_progress(100, "Generierung abgeschlossen.")
            final_hours_list = sorted(self.live_user_hours.items(), key=lambda item: item[1], reverse=True)
            print("Finale Stunden nach Generierung:", [(uid, f"{h:.1f}") for uid, h in final_hours_list])
            print("Finale Schichtzählungen (T./N./6):")
            for user_id_int in sorted(self.live_user_hours.keys()): counts = live_shift_counts[user_id_int]; print(
                f"  User {user_id_int}: T:{counts.get('T.', 0)}, N:{counts.get('N.', 0)}, 6:{counts.get('6', 0)}")
            if self.completion_callback: self.app.after(100, lambda sc=save_count: self.completion_callback(True, sc,
                                                                                                            None))  # pre_planned_count entfernt

        except Exception as e:
            print(f"Fehler im Generierungs-Thread: {e}");
            traceback.print_exc()
            if self.completion_callback: error_msg = f"Ein Fehler ist aufgetreten:\n{e}"; self.app.after(100,
                                                                                                         lambda: self.completion_callback(
                                                                                                             False, 0,
                                                                                                             error_msg))