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

# Konstanten
MAX_MONTHLY_HOURS = 228.0  # Harte Obergrenze für Monatsstunden
MAX_CONSECUTIVE_SHIFTS = 6  # Harte Regel für max. Arbeitstage am Stück
DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT = 4  # Standard, wenn nicht in Config gesetzt (Weiche Regel)
FAIRNESS_THRESHOLD_HOURS = 10.0  # Schwellenwert für "deutliche" Stundenabweichung nach unten


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
        self.shifts_to_plan = ["6", "T.", "N."]  # Kann angepasst werden, falls Prioritäten sich ändern
        # Stunden pro Schichtkürzel
        self.shift_hours = {abbrev: float(data.get('hours', 0.0))
                            for abbrev, data in self.app.shift_types_data.items()}
        # Menge der Schichtkürzel, die als "Arbeitstage" zählen
        self.work_shifts = {s for s, data in self.app.shift_types_data.items() if
                            float(data.get('hours', 0.0)) > 0 and s not in ['U',
                                                                            'EU']}  # Urlaub etc. explizit ausschließen
        self.work_shifts.update(['T.', 'N.', '6', '24'])  # Wichtige Arbeitsschichten hinzufügen

        # Menge der Kürzel, die als "Frei" gelten (für N-F-T Regel und Isolations-Check)
        self.free_shifts_indicators = {"", "FREI", "U", "X", "EU", "WF", "U?"}

        # Generator-Konfiguration aus DataManager laden
        self.generator_config = {}
        if self.data_manager and hasattr(self.data_manager, 'get_generator_config'):
            try:
                self.generator_config = self.data_manager.get_generator_config()
                print("[Generator] Generator-Konfiguration geladen:", self.generator_config)
            except Exception as e:
                print(f"[FEHLER] Konnte Generator-Konfiguration nicht laden: {e}")

        # Einstellungen aus Config oder Standardwerte verwenden
        self.max_consecutive_same_shift_limit = self.generator_config.get('max_consecutive_same_shift',
                                                                          DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT)

        # Priorisierte Partner verarbeiten -> Map { user_id: [ (prio1, partner1), (prio2, partner2), ... ] }
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
                print(f"[WARNUNG] Ungültiger Eintrag in prioritized_partners ignoriert: {entry}")
        # Partnerlisten nach Priorität sortieren (wichtig für spätere Logik)
        for user_id in self.partner_priority_map:
            self.partner_priority_map[user_id].sort(key=lambda x: x[0])
        print(f"[Generator] Partner-Prioritäts-Map erstellt: {dict(self.partner_priority_map)}")

        # --- NEU: Cache für Folgemonatsdaten ---
        self._next_month_shifts = None  # Wird bei Bedarf gefüllt
        # --- ENDE NEU ---

    def _update_progress(self, value, text):
        """ Sendet Fortschritt an die GUI (über Callback). """
        if self.progress_callback: self.progress_callback(value, text)

    def run_generation(self):
        """ Startet den Generierungsprozess (wird im Thread aufgerufen). """
        # --- NEU: Folgemonatsdaten vorab laden (optional, könnte Performance verbessern) ---
        # self._load_next_month_data() # Aktivieren, wenn benötigt
        # --- ENDE NEU ---
        self._generate()

    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlappung zweier Schichten mithilfe des Caches im DataManager. """
        if shift1_abbrev in self.free_shifts_indicators or shift2_abbrev in self.free_shifts_indicators: return False  # Freie Schichten überlappen nie
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
        # Gibt leeren String zurück für Nicht-Arbeitstage oder wenn kein Eintrag
        return shift if shift not in [None, ""] and shift not in self.free_shifts_indicators else ""

    def _get_previous_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag vom Vortag (inkl. FREI, U, etc.). """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(check_date_str)
        first_day_current_month = date(self.year, self.month, 1)
        if shift is None and check_date_obj < first_day_current_month:
            prev_month_data = getattr(self.data_manager, '_prev_month_shifts', {})
            shift = prev_month_data.get(user_id_str, {}).get(check_date_str)
        return shift if shift is not None else ""  # Gibt Leerstring zurück, wenn kein Eintrag existiert

    # --- NEUE Hilfsfunktionen für nächste Tage ---
    def _load_next_month_data(self):
        """ Lädt die Schichtdaten des Folgemonats in einen Cache. """
        if self._next_month_shifts is None:  # Nur laden, wenn noch nicht geschehen
            next_month_year = self.year
            next_month_month = self.month + 1
            if next_month_month > 12:
                next_month_month = 1
                next_month_year += 1

            print(f"[Generator] Lade Daten für Folgemonat {next_month_year}-{next_month_month}...")
            # Annahme: DataManager hat eine Methode, um gezielt Monatsdaten zu holen
            # Diese muss evtl. im DataManager noch implementiert werden!
            if self.data_manager and hasattr(self.data_manager, 'get_raw_shifts_for_month'):
                try:
                    self._next_month_shifts = self.data_manager.get_raw_shifts_for_month(next_month_year,
                                                                                         next_month_month)
                    print("[Generator] Folgemonatsdaten geladen.")
                except Exception as e:
                    print(f"[FEHLER] Konnte Folgemonatsdaten nicht laden: {e}")
                    self._next_month_shifts = {}  # Leerer Cache bei Fehler
            else:
                print("[WARNUNG] Methode get_raw_shifts_for_month im DataManager nicht gefunden.")
                self._next_month_shifts = {}  # Leerer Cache

    def _get_next_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag vom Folgetag (inkl. FREI, U, etc.). """
        next_date_obj = check_date_obj + timedelta(days=1)
        next_date_str = next_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(next_date_str)

        # Prüfen, ob das Datum im Folgemonat liegt
        if shift is None and next_date_obj.month != self.month:
            self._load_next_month_data()  # Sicherstellen, dass Daten geladen sind
            if self._next_month_shifts:
                shift = self._next_month_shifts.get(user_id_str, {}).get(next_date_str)

        return shift if shift is not None else ""

    def _get_shift_after_next_raw_shift(self, user_id_str, check_date_obj):
        """ Holt den *exakten* Schichteintrag von Übermorgen (inkl. FREI, U, etc.). """
        after_next_date_obj = check_date_obj + timedelta(days=2)
        after_next_date_str = after_next_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(after_next_date_str)

        # Prüfen, ob das Datum im Folgemonat liegt
        if shift is None and after_next_date_obj.month != self.month:
            self._load_next_month_data()  # Sicherstellen, dass Daten geladen sind
            if self._next_month_shifts:
                shift = self._next_month_shifts.get(user_id_str, {}).get(after_next_date_str)

        return shift if shift is not None else ""

    # --- ENDE NEUE Hilfsfunktionen ---

    def _count_consecutive_shifts(self, user_id_str, check_date_obj):
        """ Zählt Arbeitstage am Stück rückwärts ab check_date_obj. """
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self._get_previous_shift(user_id_str, current_check)
            if shift and shift in self.work_shifts:  # Prüft, ob es ein definierter Arbeitstag ist
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
            if shift == target_shift_abbrev:  # Nur zählen, wenn exakt die gleiche Schicht
                count += 1;
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def _generate(self):
        """ Führt die eigentliche Generierungslogik aus. """
        try:
            self._update_progress(5, "Starte Generierungsprozess...")
            days_in_month = calendar.monthrange(self.year, self.month)[1]
            live_user_hours = defaultdict(float)
            live_shift_counts = defaultdict(lambda: defaultdict(int))

            # Initialisierung (Unverändert)
            for user_id_str, day_data in self.live_shifts_data.items():
                try:
                    user_id_int = int(user_id_str)
                except ValueError:
                    continue
                if user_id_int not in self.user_data_map: continue
                for date_str, shift in day_data.items():
                    try:
                        shift_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        if shift_date_obj.year != self.year or shift_date_obj.month != self.month: continue
                    except ValueError:
                        continue
                    hours = self.shift_hours.get(shift, 0.0)
                    if hours > 0: live_user_hours[user_id_int] += hours
                    if shift in self.shifts_to_plan: live_shift_counts[user_id_int][shift] += 1

            save_count = 0
            total_steps = days_in_month * len(self.shifts_to_plan)
            current_step = 0

            # Hauptschleife: Tage
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')
                prev_date_obj = current_date_obj - timedelta(days=1)
                two_days_ago_obj = current_date_obj - timedelta(days=2)
                # --- NEU: Datumsvariablen für Zukunft ---
                next_day_obj = current_date_obj + timedelta(days=1)
                day_after_next_obj = current_date_obj + timedelta(days=2)
                # --- ENDE NEU ---

                users_unavailable_today = set()
                existing_dog_assignments = defaultdict(list)
                assignments_today_by_shift = defaultdict(set)

                # VORDURCHLAUF (Unverändert)
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

                # Mindestbesetzung (Unverändert)
                try:
                    min_staffing_today = self.data_manager.get_min_staffing_for_date(current_date_obj)
                except Exception as staffing_err:
                    min_staffing_today = {}; print(f"[WARN] Staffing Error {date_str}: {staffing_err}")

                # Schleife: Schichten (6, T, N)
                for shift_abbrev in self.shifts_to_plan:
                    # ... (Fortschritt, Bedarfsermittlung etc. wie gehabt) ...
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
                    assigned_count_this_shift_loop = 0

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

                            # Schichten der Umwelttage holen
                            prev_shift = self._get_previous_shift(user_id_str, prev_date_obj);
                            one_day_ago_raw_shift = self._get_previous_raw_shift(user_id_str, prev_date_obj);
                            two_days_ago_shift = self._get_previous_shift(user_id_str, two_days_ago_obj)
                            # --- NEU: Zukünftige Schichten holen ---
                            next_raw_shift = self._get_next_raw_shift(user_id_str, current_date_obj)
                            after_next_raw_shift = self._get_shift_after_next_raw_shift(user_id_str, current_date_obj)
                            # --- ENDE NEU ---

                            # Regelprüfungen (Hard und Soft)
                            if user_dog and user_dog != '---' and user_dog in existing_dog_assignments and any(
                                self._check_time_overlap_optimized(shift_abbrev, a['shift']) for a in
                                existing_dog_assignments[user_dog]): skip_reason = "Dog Time Conflict"  # Hard
                            if not skip_reason and prev_shift == "N." and shift_abbrev in ["T.",
                                                                                           "6"]: skip_reason = f"N->{shift_abbrev} Conflict"  # Hard
                            if not skip_reason and shift_abbrev == "T." and one_day_ago_raw_shift in self.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T Conflict"  # Hard
                            if not skip_reason:
                                consecutive_days = self._count_consecutive_shifts(user_id_str, current_date_obj)
                                if consecutive_days >= MAX_CONSECUTIVE_SHIFTS: skip_reason = f"Max Consecutive ({consecutive_days})"  # Hard
                            if not skip_reason:
                                consecutive_same = self._count_consecutive_same_shifts(user_id_str, current_date_obj,
                                                                                       shift_abbrev)
                                if consecutive_same >= self.max_consecutive_same_shift_limit: skip_reason = f"Max Same '{shift_abbrev}' ({consecutive_same})"  # Soft
                            if not skip_reason and current_hours + hours_for_this_shift > MAX_MONTHLY_HOURS: skip_reason = f"Max Hours ({current_hours:.1f}+{hours_for_this_shift:.1f}>{MAX_MONTHLY_HOURS})"  # Hard

                            # --- NEU: Isolationsprüfung (als Weiche Regel/Penalty) ---
                            # Wird später im Score berücksichtigt, hier kein skip_reason
                            is_isolated = False
                            # Muster FREI - FREI - [DIENST] - FREI ?
                            if one_day_ago_raw_shift in self.free_shifts_indicators and \
                                    self._get_previous_raw_shift(user_id_str,
                                                                 two_days_ago_obj) in self.free_shifts_indicators and \
                                    next_raw_shift in self.free_shifts_indicators:
                                is_isolated = True
                            # Muster FREI - [DIENST] - FREI - FREI ?
                            elif one_day_ago_raw_shift in self.free_shifts_indicators and \
                                    next_raw_shift in self.free_shifts_indicators and \
                                    after_next_raw_shift in self.free_shifts_indicators:
                                is_isolated = True
                            # --- ENDE NEU ---

                            if skip_reason: skipped_reasons[skip_reason] += 1; continue

                            # Gültiger Kandidat
                            candidate_data = {
                                'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog,
                                'hours': current_hours, 'prev_shift': prev_shift,
                                'is_isolated': is_isolated  # Isolations-Flag hinzufügen
                            }
                            possible_candidates.append(candidate_data)
                            candidate_total_hours += current_hours;
                            num_available_candidates += 1

                        if not possible_candidates: print(
                            f"      -> No fair candidates found in search {search_attempts_fair}. Skipped: {dict(skipped_reasons)}"); break

                        # Schritt 1.2: Scores für Sortierung berechnen
                        average_hours = (
                                    candidate_total_hours / num_available_candidates) if num_available_candidates > 0 else 0.0
                        available_candidate_ids = {c['id'] for c in possible_candidates}

                        for candidate in possible_candidates:
                            candidate_id = candidate['id']
                            # Fairness Score
                            hours_diff = average_hours - candidate['hours']
                            candidate['fairness_score'] = 1 if hours_diff > FAIRNESS_THRESHOLD_HOURS else 0
                            # Partner Score
                            candidate['partner_score'] = 1000
                            if candidate_id in self.partner_priority_map:
                                for prio, partner_id in self.partner_priority_map[candidate_id]:
                                    if partner_id in available_candidate_ids:
                                        candidate['partner_score'] = prio; break
                                    elif partner_id in assignments_today_by_shift.get(shift_abbrev, set()):
                                        candidate['partner_score'] = 100 + prio; break
                            # Isolation Score (0=nicht isoliert, 1=isoliert) -> Höher ist schlechter
                            candidate['isolation_score'] = 1 if candidate.get('is_isolated', False) else 0

                        # Schritt 1.3: Kandidaten sortieren
                        # Priorität: Partner -> Fairness -> Isolation -> Blockbildung -> Stunden
                        possible_candidates.sort(
                            key=lambda x: (
                                x.get('partner_score', 1000),  # Prio 1: Partner (niedriger = besser)
                                -x.get('fairness_score', 0),  # Prio 2: Fairness (höher = besser, daher -)
                                x.get('isolation_score', 0),  # Prio 3: Isolation (niedriger = besser)
                                0 if x['prev_shift'] == shift_abbrev else 1,  # Prio 4: Block (0 = besser)
                                x['hours']  # Prio 5: Stunden (niedriger = besser)
                            )
                        )

                        # Schritt 1.4: Besten Kandidaten auswählen und zuweisen
                        chosen_user = possible_candidates[0]
                        print(
                            f"      -> Trying User {chosen_user['id']} (PartnerScore={chosen_user.get('partner_score', 1000)}, FairScore={chosen_user.get('fairness_score', 0)}, IsoScore={chosen_user.get('isolation_score', 0)}, Block={chosen_user['prev_shift'] == shift_abbrev}, Hrs={chosen_user['hours']:.1f})")

                        success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)

                        if success:
                            save_count += 1;
                            assigned_count_this_shift_loop += 1
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
                            live_shift_counts[user_id_int][shift_abbrev] += 1
                        else:  # Fehler beim Speichern
                            print(f"      -> Fair DB ERROR for User {chosen_user['id']}: {msg}")
                            users_unavailable_today.add(chosen_user['id_str'])

                    # ========================================================
                    # Runde 2: Auffüllen (Mindestbesetzung sicherstellen)
                    # ========================================================
                    current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()))
                    needed_after_fair = required_count - current_assigned_count
                    if needed_after_fair > 0:
                        print(
                            f"      -> Still need {needed_after_fair} for '{shift_abbrev}' @ {date_str}. Starting fill round (ignoring soft limits & preferences)...")
                        search_attempts_fill = 0
                        while current_assigned_count < required_count and search_attempts_fill < len(
                                self.all_users) + 1:
                            search_attempts_fill += 1
                            possible_fill_candidates = []
                            # Schritt 2.1: Gültige Kandidaten sammeln (nur Hard Rules)
                            for user_dict in self.all_users:
                                user_id_int = user_dict.get('id');
                                if user_id_int is None: continue
                                user_id_str = str(user_id_int)
                                if user_id_str in users_unavailable_today: continue
                                user_dog = user_dict.get('diensthund');
                                current_hours = live_user_hours.get(user_id_int, 0.0);
                                hours_for_this_shift = self.shift_hours.get(shift_abbrev, 0.0)
                                skip_reason = None
                                prev_shift = self._get_previous_shift(user_id_str, prev_date_obj);
                                one_day_ago_raw_shift = self._get_previous_raw_shift(user_id_str, prev_date_obj);
                                two_days_ago_shift = self._get_previous_shift(user_id_str, two_days_ago_obj)
                                # Nur Harte Regeln prüfen (Hund, N->T/6, N-F-T, Max Tage, Max Stunden)
                                if user_dog and user_dog != '---' and user_dog in existing_dog_assignments and any(
                                    self._check_time_overlap_optimized(shift_abbrev, a['shift']) for a in
                                    existing_dog_assignments[user_dog]): skip_reason = "Dog Time Conflict"
                                if not skip_reason and prev_shift == "N." and shift_abbrev in ["T.",
                                                                                               "6"]: skip_reason = f"N->{shift_abbrev} Conflict"
                                if not skip_reason and shift_abbrev == "T." and one_day_ago_raw_shift in self.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T Conflict"  # Harte Regel
                                if not skip_reason:
                                    consecutive_days = self._count_consecutive_shifts(user_id_str, current_date_obj)
                                    if consecutive_days >= MAX_CONSECUTIVE_SHIFTS: skip_reason = f"Max Consecutive ({consecutive_days})"  # Harte Regel
                                if not skip_reason and current_hours + hours_for_this_shift > MAX_MONTHLY_HOURS: skip_reason = f"Max Hours ({current_hours:.1f}+{hours_for_this_shift:.1f}>{MAX_MONTHLY_HOURS})"  # Harte Regel
                                # Max Same Shift & Partner & Isolation werden IGNORIERT
                                if skip_reason: continue
                                # Gültiger Kandidat für Fill-Runde
                                possible_fill_candidates.append(
                                    {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours})

                            if not possible_fill_candidates: print(
                                f"         -> No fill candidates found in search {search_attempts_fill}. (All blocked by hard rules!)"); break

                            # Schritt 2.2: Kandidaten sortieren (nur nach Stunden)
                            possible_fill_candidates.sort(key=lambda x: x['hours'])

                            # Schritt 2.3: Besten auswählen und zuweisen
                            chosen_user = possible_fill_candidates[0]
                            success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)
                            if success:
                                save_count += 1;
                                current_assigned_count += 1  # Gesamtzahl erhöhen
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
                                live_shift_counts[user_id_int][shift_abbrev] += 1
                                print(
                                    f"         -> Fill OK: User {chosen_user['id']} gets '{shift_abbrev}'. H:{live_user_hours[user_id_int]:.2f}")
                            else:  # Fehler beim Speichern
                                print(f"         -> Fill DB ERROR for User {chosen_user['id']}: {msg}")
                                users_unavailable_today.add(chosen_user['id_str'])  # User trotzdem blockieren

                    # Endgültige Prüfung nach beiden Runden
                    final_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()))
                    if final_assigned_count < required_count:
                        print(
                            f"   -> [WARNUNG] Mindestbesetzung für '{shift_abbrev}' an {date_str} nicht erreicht (Req: {required_count}, Assigned: {final_assigned_count}).")

            # Abschluss des Tages (keine spezifischen Aktionen hier)

            # Abschluss nach allen Tagen
            self._update_progress(100, "Generierung abgeschlossen.")
            # Finale Statistiken ausgeben
            final_hours_list = sorted(live_user_hours.items(), key=lambda item: item[1], reverse=True)
            print("Finale (geschätzte) Stunden nach Generierung:", [(uid, f"{h:.2f}") for uid, h in final_hours_list])
            print("Finale Schichtzählungen (T./N./6):")
            for user_id_int in sorted(live_user_hours.keys()):
                counts = live_shift_counts[user_id_int]
                print(f"  User {user_id_int}: T:{counts.get('T.', 0)}, N:{counts.get('N.', 0)}, 6:{counts.get('6', 0)}")

            # GUI über Abschluss informieren (im GUI-Thread)
            if self.completion_callback:
                self.app.after(100, lambda sc=save_count: self.completion_callback(True, sc, None))

        except Exception as e:  # Fehlerbehandlung für den gesamten Thread
            print(f"Fehler im Generierungs-Thread: {e}")
            traceback.print_exc()
            # GUI über Fehler informieren (im GUI-Thread)
            if self.completion_callback:
                error_msg = f"Ein Fehler ist aufgetreten:\n{e}"
                self.app.after(100, lambda: self.completion_callback(False, 0, error_msg))