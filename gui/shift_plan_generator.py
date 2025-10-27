# gui/shift_plan_generator.py
import calendar
import threading
from collections import defaultdict
from datetime import date, timedelta, datetime, time
import math

from database.db_shifts import save_shift_entry  # Datenbankzugriff für Speichern

# Konstanten
MAX_MONTHLY_HOURS = 228.0
MAX_CONSECUTIVE_SHIFTS = 6  # Harte Regel
MAX_CONSECUTIVE_SAME_SHIFT = 4  # Weiche Regel


class ShiftPlanGenerator:
    """
    Diese Klasse kapselt die Logik zur automatischen Generierung des Schichtplans.
    Sie wird in einem separaten Thread ausgeführt.
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
        self.live_shifts_data = live_shifts_data
        self.holidays_in_month = holidays_in_month
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

        self.shifts_to_plan = ["6", "T.", "N."]  # Priorität 6, T, N
        self.shift_hours = {abbrev: float(data.get('hours', 0.0))
                            for abbrev, data in self.app.shift_types_data.items()}
        self.work_shifts = {s for s, data in self.app.shift_types_data.items() if
                            float(data.get('hours', 0.0)) > 0 and s not in ['U', 'EU']}
        self.work_shifts.update(['T.', 'N.', '6', '24'])

    def _update_progress(self, value, text):
        if self.progress_callback: self.progress_callback(value, text)

    def run_generation(self):
        self._generate()

    # --- NEUE HILFSFUNKTION FÜR ZEIT-KONFLIKTPRÜFUNG ---
    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlappung anhand des vorverarbeiteten Caches im DataManager. """
        if shift1_abbrev in ['U', 'X', 'EU', 'WF', ''] or shift2_abbrev in ['U', 'X', 'EU', 'WF', '']: return False

        # Sicherer Zugriff auf den Cache des DataManagers (wird in load_and_process_data gefüllt)
        preprocessed_times = getattr(self.data_manager, '_preprocessed_shift_times', {})

        s1, e1 = preprocessed_times.get(shift1_abbrev, (None, None))
        s2, e2 = preprocessed_times.get(shift2_abbrev, (None, None))

        if s1 is None or s2 is None:
            # Kann keinen Konflikt feststellen, wenn die Zeitdaten fehlen.
            return False

        # Korrekte Überlappungsprüfung: Überlappung existiert, wenn s1 < e2 UND s2 < e1
        overlap = (s1 < e2) and (s2 < e1)
        return overlap

    # --- ENDE NEUE HILFSFUNKTION ---

    def _get_previous_shift(self, user_id_str, check_date_obj):
        check_date_str = check_date_obj.strftime('%Y-%m-%d')
        shift = self.live_shifts_data.get(user_id_str, {}).get(check_date_str)
        first_day_current_month = date(self.year, self.month, 1)
        if shift is None and check_date_obj < first_day_current_month:
            prev_month_data = getattr(self.data_manager, '_prev_month_shifts', {})
            shift = prev_month_data.get(user_id_str, {}).get(check_date_str)
        return shift if shift else ""

    def _count_consecutive_shifts(self, user_id_str, check_date_obj):
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self._get_previous_shift(user_id_str, current_check)
            if shift and shift in self.work_shifts:
                count += 1; current_check -= timedelta(days=1)
            else:
                break
        return count

    def _count_consecutive_same_shifts(self, user_id_str, check_date_obj, target_shift_abbrev):
        count = 0;
        current_check = check_date_obj - timedelta(days=1)
        while True:
            shift = self._get_previous_shift(user_id_str, current_check)
            if shift == target_shift_abbrev:
                count += 1; current_check -= timedelta(days=1)
            else:
                break
        return count

    def _generate(self):
        try:
            self._update_progress(5, "Starte Generierungsprozess...")
            days_in_month = calendar.monthrange(self.year, self.month)[1]
            live_daily_counts = defaultdict(lambda: defaultdict(int))
            live_user_hours = defaultdict(float)
            live_shift_counts = defaultdict(lambda: defaultdict(int))

            # Initialisierung
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
                    shift_info = self.app.shift_types_data.get(shift, {})
                    hours = self.shift_hours.get(shift, 0.0)
                    if hours > 0: live_user_hours[user_id_int] += hours
                    if shift in self.shifts_to_plan: live_shift_counts[user_id_int][shift] += 1
                    if shift and shift_info.get('check_for_understaffing', False): live_daily_counts[date_str][
                        shift] += 1

            save_count = 0;
            total_steps = days_in_month * len(self.shifts_to_plan);
            current_step = 0

            # Schleife durch Tage
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day);
                date_str = current_date_obj.strftime('%Y-%m-%d')
                prev_date_obj = current_date_obj - timedelta(days=1)
                users_unavailable_today = set()

                # --- KORREKTUR 1: Hunde-Belegungen sammeln (für Zeitprüfung) ---
                existing_dog_assignments = defaultdict(list)
                # --- ENDE KORREKTUR 1 ---

                # VORDURCHLAUF
                for user_id_int, user_data in self.user_data_map.items():
                    user_id_str = str(user_id_int);
                    user_dog = user_data.get('diensthund')
                    is_unavailable = False;
                    is_working = False
                    if self.vacation_requests.get(user_id_str, {}).get(current_date_obj) in ['Approved', 'Genehmigt']:
                        is_unavailable = True
                    elif not is_unavailable and date_str in self.wunschfrei_requests.get(user_id_str, {}):
                        wf_status = self.wunschfrei_requests[user_id_str][date_str][0]
                        if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert']: is_unavailable = True
                    existing_shift = self.live_shifts_data.get(user_id_str, {}).get(date_str)
                    if existing_shift and existing_shift not in ["", "FREI"]: is_working = True
                    if is_unavailable or is_working: users_unavailable_today.add(user_id_str)

                    # --- KORREKTUR 2: Hunde-Belegung speichern (nur wenn User arbeitet) ---
                    if is_working and user_dog:
                        existing_dog_assignments[user_dog].append({'user_id': user_id_int, 'shift': existing_shift})
                    # --- ENDE KORREKTUR 2 ---

                try:
                    min_staffing_today = self.data_manager.get_min_staffing_for_date(current_date_obj)
                except Exception as staffing_err:
                    min_staffing_today = {}; print(f"[WARN] Staffing Error {date_str}: {staffing_err}")

                # Schichten planen
                for shift_abbrev in self.shifts_to_plan:
                    current_step += 1;
                    progress_perc = int((current_step / total_steps) * 90) + 5
                    self._update_progress(progress_perc, f"Plane {shift_abbrev} für {date_str}...")
                    if shift_abbrev == "6" and (
                            current_date_obj.weekday() != 4 or current_date_obj in self.holidays_in_month): continue
                    required_count = min_staffing_today.get(shift_abbrev, 0)
                    if required_count <= 0: continue
                    needed_now = required_count - live_daily_counts[date_str][shift_abbrev]
                    if needed_now <= 0: continue
                    print(
                        f"   -> Need {needed_now} for '{shift_abbrev}' @ {date_str} (Req:{required_count}, Has:{live_daily_counts[date_str][shift_abbrev]})")

                    assigned_count_this_shift = 0
                    # Erste Runde: Fairness & Block-Förderung (Weiche Regeln aktiv)
                    search_attempts_fair = 0
                    while assigned_count_this_shift < needed_now and search_attempts_fair < len(self.all_users) + 1:
                        search_attempts_fair += 1
                        possible_candidates = []
                        skipped_reasons = defaultdict(int)
                        for user_dict in self.all_users:
                            user_id_int = user_dict['id'];
                            user_id_str = str(user_id_int);
                            user_dog = user_dict.get('diensthund')
                            current_hours = live_user_hours.get(user_id_int, 0.0);
                            hours_for_this_shift = self.shift_hours.get(shift_abbrev, 0.0)
                            skip_reason = None

                            # --- Konfliktprüfungen (Fair Round) ---
                            if user_id_str in users_unavailable_today:
                                skip_reason = "Unavailable/Working"
                            elif user_dog and user_dog in existing_dog_assignments:  # NEU: Hundezeitprüfung
                                is_dog_conflict = False
                                for assignment in existing_dog_assignments[user_dog]:
                                    if self._check_time_overlap_optimized(shift_abbrev, assignment['shift']):
                                        is_dog_conflict = True
                                        break
                                if is_dog_conflict: skip_reason = "Dog Time Conflict"
                            else:
                                prev_shift = self._get_previous_shift(user_id_str, prev_date_obj)
                                if prev_shift == "N." and shift_abbrev in ["T.", "6"]:
                                    skip_reason = f"N->{shift_abbrev} Conflict"
                                else:
                                    consecutive_days = self._count_consecutive_shifts(user_id_str, current_date_obj)
                                    if consecutive_days >= MAX_CONSECUTIVE_SHIFTS:
                                        skip_reason = f"Max Consecutive ({consecutive_days})"
                                    else:
                                        consecutive_same = self._count_consecutive_same_shifts(user_id_str,
                                                                                               current_date_obj,
                                                                                               shift_abbrev)
                                        if consecutive_same >= MAX_CONSECUTIVE_SAME_SHIFT:
                                            skip_reason = f"Max Same '{shift_abbrev}' ({consecutive_same})"  # WEICHE REGEL
                                        elif current_hours + hours_for_this_shift > MAX_MONTHLY_HOURS:
                                            skip_reason = f"Max Hours ({current_hours:.1f}+{hours_for_this_shift:.1f}>{MAX_MONTHLY_HOURS})"  # HARTE REGEL

                            if skip_reason: skipped_reasons[skip_reason] += 1; continue
                            # --- Ende Konfliktprüfungen ---

                            possible_candidates.append(
                                {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours,
                                 'shift_count': live_shift_counts[user_id_int][shift_abbrev], 'prev_shift': prev_shift})

                        if not possible_candidates: print(
                            f"      -> No fair candidates found in search {search_attempts_fair}. Skipped: {dict(skipped_reasons)}"); break

                        possible_candidates.sort(
                            key=lambda x: (0 if x['prev_shift'] == shift_abbrev else 1, x['shift_count'], x['hours']))
                        chosen_user = possible_candidates[0]
                        success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)

                        if success:
                            save_count += 1;
                            assigned_count_this_shift += 1
                            user_id_int = chosen_user['id'];
                            user_id_str = chosen_user['id_str'];
                            user_dog = chosen_user['dog']
                            if user_id_str not in self.live_shifts_data: self.live_shifts_data[user_id_str] = {}
                            self.live_shifts_data[user_id_str][date_str] = shift_abbrev
                            users_unavailable_today.add(user_id_str)
                            # --- KORREKTUR 3: Hunde-Belegung in Live-Liste updaten ---
                            if user_dog: existing_dog_assignments[user_dog].append(
                                {'user_id': user_id_int, 'shift': shift_abbrev})
                            # --- ENDE KORREKTUR 3 ---
                            shift_info = self.app.shift_types_data.get(shift_abbrev, {})
                            if shift_info.get('check_for_understaffing', False): live_daily_counts[date_str][
                                shift_abbrev] += 1
                            hours_added = self.shift_hours.get(shift_abbrev, 0.0)
                            live_user_hours[user_id_int] += hours_added
                            live_shift_counts[user_id_int][shift_abbrev] += 1
                        else:
                            print(f"      -> Fair DB ERROR for User {chosen_user['id']}: {msg}")
                            users_unavailable_today.add(chosen_user['id_str'])

                    # Zweite Runde: Unterbesetzung Auffüllen (Ignoriert Soft Limits)
                    needed_after_fair = required_count - live_daily_counts[date_str][shift_abbrev]
                    if needed_after_fair > 0:
                        print(
                            f"      -> Still need {needed_after_fair} for '{shift_abbrev}' @ {date_str}. Starting fill round (ignoring soft limits)...")
                        search_attempts_fill = 0
                        while assigned_count_this_shift < required_count and search_attempts_fill < len(
                                self.all_users) + 1:
                            search_attempts_fill += 1;
                            possible_fill_candidates = []
                            for user_dict in self.all_users:
                                user_id_int = user_dict['id'];
                                user_id_str = str(user_id_int);
                                user_dog = user_dict.get('diensthund')
                                current_hours = live_user_hours.get(user_id_int, 0.0);
                                hours_for_this_shift = self.shift_hours.get(shift_abbrev, 0.0)
                                skip_reason = None

                                # *** Harte Konfliktprüfungen (Fill Round) ***
                                if user_id_str in users_unavailable_today:
                                    skip_reason = "Unavailable/Working"
                                elif user_dog and user_dog in existing_dog_assignments:  # NEU: Hundezeitprüfung
                                    is_dog_conflict = False
                                    for assignment in existing_dog_assignments[user_dog]:
                                        if self._check_time_overlap_optimized(shift_abbrev, assignment['shift']):
                                            is_dog_conflict = True
                                            break
                                    if is_dog_conflict: skip_reason = "Dog Time Conflict"
                                else:
                                    prev_shift = self._get_previous_shift(user_id_str, prev_date_obj)
                                    if prev_shift == "N." and shift_abbrev in ["T.", "6"]:
                                        skip_reason = f"N->{shift_abbrev} Conflict"
                                    else:
                                        consecutive_days = self._count_consecutive_shifts(user_id_str, current_date_obj)
                                        if consecutive_days >= MAX_CONSECUTIVE_SHIFTS:
                                            skip_reason = f"Max Consecutive ({consecutive_days})"
                                        # MAX_CONSECUTIVE_SAME_SHIFT WIRD HIER NICHT GEPRÜFT!
                                        elif current_hours + hours_for_this_shift > MAX_MONTHLY_HOURS:
                                            skip_reason = f"Max Hours ({current_hours:.1f}+{hours_for_this_shift:.1f}>{MAX_MONTHLY_HOURS})"

                                if skip_reason: continue

                                possible_fill_candidates.append(
                                    {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours})

                            if not possible_fill_candidates: print(
                                f"         -> No fill candidates found in search {search_attempts_fill}. (All blocked by hard rules!)"); break

                            possible_fill_candidates.sort(key=lambda x: x['hours'])  # Priorisiere niedrigste Stunden
                            chosen_user = possible_fill_candidates[0]

                            # Zuweisung (Fill)
                            success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)
                            if success:
                                save_count += 1;
                                assigned_count_this_shift += 1
                                user_id_int = chosen_user['id'];
                                user_id_str = chosen_user['id_str'];
                                user_dog = chosen_user['dog']
                                if user_id_str not in self.live_shifts_data: self.live_shifts_data[user_id_str] = {}
                                self.live_shifts_data[user_id_str][date_str] = shift_abbrev
                                users_unavailable_today.add(user_id_str)
                                # --- KORREKTUR 4: Hunde-Belegung in Live-Liste updaten ---
                                if user_dog: existing_dog_assignments[user_dog].append(
                                    {'user_id': user_id_int, 'shift': shift_abbrev})
                                # --- ENDE KORREKTUR 4 ---
                                shift_info = self.app.shift_types_data.get(shift_abbrev, {})
                                if shift_info.get('check_for_understaffing', False): live_daily_counts[date_str][
                                    shift_abbrev] += 1
                                hours_added = self.shift_hours.get(shift_abbrev, 0.0)
                                live_user_hours[user_id_int] += hours_added
                                live_shift_counts[user_id_int][shift_abbrev] += 1
                                print(
                                    f"         -> Fill OK: User {chosen_user['id']} gets '{shift_abbrev}'. H:{live_user_hours[user_id_int]:.2f}")
                            else:
                                print(f"         -> Fill DB ERROR for User {chosen_user['id']}: {msg}")
                                users_unavailable_today.add(chosen_user['id_str'])

                    # Endgültige Prüfung
                    current_final_count = live_daily_counts[date_str][shift_abbrev]
                    if current_final_count < required_count: print(
                        f"   -> [WARNUNG] Mindestbesetzung für '{shift_abbrev}' an {date_str} nicht erreicht (Req: {required_count}, Assigned: {current_final_count}).")

            # Abschluss
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
            import traceback;
            traceback.print_exc()
            if self.completion_callback:
                error_msg = f"Ein Fehler ist aufgetreten:\n{e}"
                self.app.after(100, lambda: self.completion_callback(False, 0, error_msg))