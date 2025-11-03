# gui/generator/generator_rounds.py
from collections import defaultdict
from datetime import date, timedelta, datetime, time


# --- ENTFERNT ---
# from database.db_shifts import save_shift_entry  # Direkter DB-Import ENTFERNT


class GeneratorRounds:
    """
    Kapselt die Logik für die Ausführung der verschiedenen Zuweisungsrunden
    (Runde 1: Fair mit Future Conflict Score, Runde 2-4: Auffüllen).
    """

    def __init__(self, generator_instance, helpers_instance, scoring_instance):
        self.gen = generator_instance
        self.helpers = helpers_instance
        self.scoring = scoring_instance

    def run_fair_assignment_round(self, shift_abbrev, current_date_obj,
                                  users_unavailable_today, existing_dog_assignments, assignments_today_by_shift,
                                  live_user_hours, live_shift_counts, live_shift_counts_ratio,
                                  needed_now, days_in_month):  # critical_shifts entfernt
        """
        Führt die "Runde 1" (Faire Zuweisung mit Präferenzen und Future Conflict Score) aus.
        Gibt die Anzahl der erfolgreich zugewiesenen Schichten zurück.
        """

        assigned_count_this_round = 0
        search_attempts_fair = 0

        date_str = current_date_obj.strftime('%Y-%m-%d')
        prev_date_obj = current_date_obj - timedelta(days=1)
        two_days_ago_obj = current_date_obj - timedelta(days=2)

        while assigned_count_this_round < needed_now and search_attempts_fair < len(self.gen.all_users) + 1:
            search_attempts_fair += 1
            possible_candidates = []
            skipped_reasons = defaultdict(int)
            candidate_total_hours = 0.0
            num_available_candidates = 0

            # Schritt 1.1: Gültige Kandidaten sammeln
            for user_dict in self.gen.all_users:
                user_id_int = user_dict.get('id')
                if user_id_int is None: continue
                user_id_str = str(user_id_int)
                if user_id_str in users_unavailable_today: continue

                user_dog = user_dict.get('diensthund')
                current_hours = live_user_hours.get(user_id_int, 0.0)
                hours_for_this_shift = self.gen.shift_hours.get(shift_abbrev, 0.0)
                skip_reason = None
                user_pref = self.gen.user_preferences[user_id_str]
                max_hours_override = user_pref.get('max_monthly_hours')
                max_same_shift_override = user_pref.get('max_consecutive_same_shift_override')

                # Helfer-Methoden verwenden
                prev_shift = self.helpers.get_previous_shift(user_id_str, prev_date_obj)
                one_day_ago_raw_shift = self.helpers.get_previous_raw_shift(user_id_str, prev_date_obj)
                two_days_ago_shift = self.helpers.get_previous_shift(user_id_str, two_days_ago_obj)
                next_raw_shift = self.helpers.get_next_raw_shift(user_id_str, current_date_obj)
                after_next_raw_shift = self.helpers.get_shift_after_next_raw_shift(user_id_str, current_date_obj)

                # --- KORREKTUR (Regel 1): Diensthund-Logik ---
                if user_dog and user_dog != '---' and user_dog in existing_dog_assignments:
                    for assigned_dog_shift in existing_dog_assignments[user_dog]:
                        assigned_shift = assigned_dog_shift['shift']

                        # FIX: Explizite Prüfung auf identische Schicht,
                        # da check_time_overlap_optimized('T.', 'T.')
                        # fälschlicherweise False liefern könnte.
                        if shift_abbrev == assigned_shift:
                            skip_reason = "Dog (Same Shift)"
                            break

                            # Original-Prüfung auf Überlappung (z.B. T. vs 6)
                        if self.helpers.check_time_overlap_optimized(shift_abbrev, assigned_shift):
                            skip_reason = "Dog (Overlap)"
                            break

                    if skip_reason:
                        # Wenn ein Grund gefunden wurde, brich die äußere
                        # Schleife (über die Hunde) ab.
                        pass  # (Wird nach der IF-Box geprüft)
                # --- ENDE KORREKTUR ---

                # N->T/6 Block
                if not skip_reason and prev_shift == "N." and shift_abbrev in ["T.", "6"]: skip_reason = "N->T/6"

                # NEUE HARD RULE: N. -> QA/S Block (Behebt das aktuelle Problem)
                if not skip_reason and prev_shift == "N." and shift_abbrev in ["QA", "S"]: skip_reason = "N->QA/S"

                if not skip_reason and shift_abbrev == "T." and one_day_ago_raw_shift in self.gen.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T"
                if not skip_reason and shift_abbrev in user_pref.get('shift_exclusions',
                                                                     []): skip_reason = f"Excl({shift_abbrev})"
                consecutive_days = self.helpers.count_consecutive_shifts(user_id_str, current_date_obj)
                if not skip_reason and consecutive_days >= self.gen.SOFT_MAX_CONSECUTIVE_SHIFTS: skip_reason = f"MaxConsS({consecutive_days})"
                if not skip_reason and self.gen.mandatory_rest_days > 0 and consecutive_days == 0 and not self.helpers.check_mandatory_rest(
                        user_id_str, current_date_obj): skip_reason = f"Rest({self.gen.mandatory_rest_days}d)"
                if not skip_reason and date_str in self.gen.wunschfrei_requests.get(user_id_str, {}):
                    wf_entry = self.gen.wunschfrei_requests[user_id_str][date_str]
                    wf_status, wf_shift = None, None
                    if isinstance(wf_entry, tuple) and len(wf_entry) >= 2: wf_status, wf_shift = wf_entry[0], wf_entry[
                        1]
                    if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert'] and wf_shift in ["",
                                                                                             shift_abbrev] and self.gen.wunschfrei_respect_level >= 50: skip_reason = f"WF({self.gen.wunschfrei_respect_level})"
                limit = max_same_shift_override if max_same_shift_override is not None else self.gen.max_consecutive_same_shift_limit
                if not skip_reason:
                    consecutive_same = self.helpers.count_consecutive_same_shifts(user_id_str, current_date_obj,
                                                                                  shift_abbrev)
                    if consecutive_same >= limit: skip_reason = f"MaxSame({consecutive_same})"
                max_hours_check = max_hours_override if max_hours_override is not None else self.gen.MAX_MONTHLY_HOURS
                if not skip_reason and current_hours + hours_for_this_shift > max_hours_check: skip_reason = f"MaxHrs({current_hours:.1f}+{hours_for_this_shift:.1f}>{max_hours_check})"
                is_isolated = (
                                      one_day_ago_raw_shift in self.gen.free_shifts_indicators and self.helpers.get_previous_raw_shift(
                                  user_id_str,
                                  two_days_ago_obj) in self.gen.free_shifts_indicators and next_raw_shift in self.gen.free_shifts_indicators) or \
                              (
                                      one_day_ago_raw_shift in self.gen.free_shifts_indicators and next_raw_shift in self.gen.free_shifts_indicators and after_next_raw_shift in self.gen.free_shifts_indicators)

                if skip_reason: skipped_reasons[skip_reason] += 1; continue

                candidate_data = {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours,
                                  'prev_shift': prev_shift, 'is_isolated': is_isolated, 'user_pref': user_pref}
                possible_candidates.append(candidate_data);
                candidate_total_hours += current_hours;
                num_available_candidates += 1

            if not possible_candidates:
                print(
                    f"      -> No fair candidates found in search {search_attempts_fair}. Skipped: {dict(skipped_reasons)}")
                break

            # Schritt 1.2: Scores berechnen
            average_hours = (candidate_total_hours / num_available_candidates) if num_available_candidates > 0 else 0.0
            available_candidate_ids = {c['id'] for c in possible_candidates}
            for candidate in possible_candidates:
                scores = self.scoring.calculate_scores(
                    candidate, average_hours, available_candidate_ids,
                    shift_abbrev, live_shift_counts_ratio,
                    assignments_today_by_shift,
                    current_date_obj, days_in_month  # Ohne critical_shifts
                )
                candidate.update(scores)  # HIER WIRD 'avoid_score' hinzugefügt

            # Schritt 1.3: Kandidaten sortieren
            # NEU: 'avoid_score' zur Sortierung hinzugefügt (höchste Priorität, da Strafe)
            possible_candidates.sort(
                key=lambda x: (
                    x.get('avoid_score', 0),  # NEU: Strafe (niedriger=besser)
                    x.get('partner_score', 1000),  # Partner (niedriger=besser)
                    x.get('future_conflict_score', 0),  # Strafe (niedriger=besser)
                    -x.get('min_hours_score', 0),  # Bonus (höher=besser)
                    -x.get('fairness_score', 0),  # Bonus (höher=besser)
                    x.get('ratio_pref_score', 0),  # Strafe (näher an 0=besser)
                    x.get('isolation_score', 0),  # Strafe (niedriger=besser)
                    0 if x['prev_shift'] == shift_abbrev else 1,  # Bonus für gleiche Schicht
                    -x['hours']  # Mitarbeiter mit MEHR Stunden bevorzugen
                )
            )

            # Schritt 1.4: Besten Kandidaten auswählen und zuweisen
            chosen_user = possible_candidates[0]

            # NEU: 'Avoid' zum Log-Ausdruck hinzugefügt
            print(
                f"      -> Trying User {chosen_user['id']} "
                f"(Avoid={chosen_user.get('avoid_score', 0)}, "
                f"Partner={chosen_user.get('partner_score', 1000)}, "
                f"FutConf={chosen_user.get('future_conflict_score', 0)}, "
                f"MinHrs={chosen_user.get('min_hours_score', 0):.2f}, "
                f"Fair={chosen_user.get('fairness_score', 0):.2f}, "
                f"Ratio={chosen_user.get('ratio_pref_score', 0):.2f}, "
                f"Iso={chosen_user.get('isolation_score', 0)}, "
                f"Block={chosen_user['prev_shift'] == shift_abbrev}, "
                f"Hrs={chosen_user['hours']:.1f})"
            )

            # --- ÄNDERUNG: DB-Aufruf entfernt ---
            # success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)
            # if success:

            # Die Zuweisung im Arbeitsspeicher ist immer erfolgreich
            assigned_count_this_round += 1;
            user_id_int = chosen_user['id'];
            user_id_str = chosen_user['id_str'];
            user_dog = chosen_user['dog']
            if user_id_str not in self.gen.live_shifts_data: self.gen.live_shifts_data[user_id_str] = {}
            self.gen.live_shifts_data[user_id_str][date_str] = shift_abbrev;
            users_unavailable_today.add(user_id_str);
            assignments_today_by_shift[shift_abbrev].add(user_id_int)
            if user_dog and user_dog != '---': existing_dog_assignments[user_dog].append(
                {'user_id': user_id_int, 'shift': shift_abbrev})
            hours_added = self.gen.shift_hours.get(shift_abbrev, 0.0);
            live_user_hours[user_id_int] += hours_added
            if shift_abbrev in ['T.', '6']: live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1
            if shift_abbrev == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1
            # Korrektur: Inkrementiere live_shift_counts für alle Schichten
            live_shift_counts[user_id_int][shift_abbrev] += 1

            # --- ÄNDERUNG: Else-Block entfernt ---
            # else:
            #     print(f"      -> Fair DB ERROR for User {chosen_user['id']}: {msg}")
            #     users_unavailable_today.add(chosen_user['id_str'])
            # --- ENDE ÄNDERUNG ---

        return assigned_count_this_round

    def run_fill_round(self, shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                       assignments_today_by_shift, live_user_hours, live_shift_counts, live_shift_counts_ratio,
                       needed, round_num):
        """
        Führt eine Auffüllrunde (2, 3 oder 4) mit spezifischen Regel-Lockerungen durch.
        """
        assigned_count = 0;
        search_attempts = 0;
        date_str = current_date_obj.strftime('%Y-%m-%d');
        prev_date_obj = current_date_obj - timedelta(days=1);
        two_days_ago_obj = current_date_obj - timedelta(days=2)

        while assigned_count < needed and search_attempts < len(self.gen.all_users) + 1:
            search_attempts += 1;
            possible_fill_candidates = []

            for user_dict in self.gen.all_users:  # Harte Regeln prüfen (mit Lockerungen je Runde)
                user_id_int = user_dict.get('id');
                if user_id_int is None: continue
                user_id_str = str(user_id_int)
                if user_id_str in users_unavailable_today: continue

                user_dog = user_dict.get('diensthund');
                current_hours = live_user_hours.get(user_id_int, 0.0);
                hours_for_this_shift = self.gen.shift_hours.get(shift_abbrev, 0.0);
                skip_reason = None;
                user_pref = self.gen.user_preferences[user_id_str];
                max_hours_override = user_pref.get('max_monthly_hours');
                prev_shift = self.helpers.get_previous_shift(user_id_str, prev_date_obj);
                one_day_ago_raw_shift = self.helpers.get_previous_raw_shift(user_id_str, prev_date_obj);
                two_days_ago_shift = self.helpers.get_previous_shift(user_id_str, two_days_ago_obj)

                # --- KORREKTUR (Regel 1): Diensthund-Logik ---
                if user_dog and user_dog != '---' and user_dog in existing_dog_assignments:
                    for assigned_dog_shift in existing_dog_assignments[user_dog]:
                        assigned_shift = assigned_dog_shift['shift']

                        # FIX: Explizite Prüfung auf identische Schicht
                        if shift_abbrev == assigned_shift:
                            skip_reason = "Dog (Same Shift)"
                            break

                            # Original-Prüfung auf Überlappung
                        if self.helpers.check_time_overlap_optimized(shift_abbrev, assigned_shift):
                            skip_reason = "Dog (Overlap)"
                            break

                    if skip_reason:
                        pass
                # --- ENDE KORREKTUR ---

                # N->T/6 Block
                if not skip_reason and prev_shift == "N." and shift_abbrev in ["T.", "6"]: skip_reason = "N->T/6"

                # NEUE HARD RULE: N. -> QA/S Block
                if not skip_reason and prev_shift == "N." and shift_abbrev in ["QA", "S"]: skip_reason = "N->QA/S"

                if round_num <= 2 and not skip_reason and shift_abbrev == "T." and one_day_ago_raw_shift in self.gen.free_shifts_indicators and two_days_ago_shift == "N.": skip_reason = "N-F-T"
                if not skip_reason and shift_abbrev in user_pref.get('shift_exclusions', []): skip_reason = "Excl(Hard)"

                limit = self.gen.HARD_MAX_CONSECUTIVE_SHIFTS if self.gen.avoid_understaffing_hard else self.gen.SOFT_MAX_CONSECUTIVE_SHIFTS
                consecutive_days = 0
                if not skip_reason:
                    consecutive_days = self.helpers.count_consecutive_shifts(user_id_str, current_date_obj)
                    if consecutive_days >= limit:
                        skip_reason = f"MaxCons({consecutive_days}) Limit({limit})"

                if round_num <= 3 and not skip_reason and self.gen.mandatory_rest_days > 0 and consecutive_days == 0 and not self.helpers.check_mandatory_rest(
                        user_id_str, current_date_obj): skip_reason = "Rest(Hard)"
                max_hours_check = max_hours_override if max_hours_override is not None else self.gen.MAX_MONTHLY_HOURS
                if not skip_reason and current_hours + hours_for_this_shift > max_hours_check: skip_reason = f"MaxHrs({current_hours:.1f}+{hours_for_this_shift:.1f}>{max_hours_check})"

                if skip_reason: continue
                possible_fill_candidates.append(
                    {'id': user_id_int, 'id_str': user_id_str, 'dog': user_dog, 'hours': current_hours})

            if not possible_fill_candidates: print(
                f"         -> No fill candidates found in Runde {round_num}, search {search_attempts}."); break

            # HINWEIS: Runde 2-4 ignoriert absichtlich Partner/Avoid Scores.
            # Es geht nur darum, die Lücken mit den am wenigsten belasteten Leuten zu füllen.
            possible_fill_candidates.sort(key=lambda x: x['hours']);
            chosen_user = possible_fill_candidates[0]

            # --- ÄNDERUNG: DB-Aufruf entfernt ---
            # success, msg = save_shift_entry(chosen_user['id'], date_str, shift_abbrev)
            # if success:

            # Die Zuweisung im Arbeitsspeicher ist immer erfolgreich
            assigned_count += 1;
            user_id_int = chosen_user['id'];
            user_id_str = chosen_user['id_str'];
            user_dog = chosen_user['dog']
            if user_id_str not in self.gen.live_shifts_data: self.gen.live_shifts_data[user_id_str] = {}
            self.gen.live_shifts_data[user_id_str][date_str] = shift_abbrev;
            users_unavailable_today.add(user_id_str);
            assignments_today_by_shift[shift_abbrev].add(user_id_int)
            if user_dog and user_dog != '---': existing_dog_assignments[user_dog].append(
                {'user_id': user_id_int, 'shift': shift_abbrev})
            hours_added = self.gen.shift_hours.get(shift_abbrev, 0.0);
            live_user_hours[user_id_int] += hours_added
            if shift_abbrev in ['T.', '6']: live_shift_counts_ratio[user_id_int]['T_OR_6'] += 1
            if shift_abbrev == 'N.': live_shift_counts_ratio[user_id_int]['N_DOT'] += 1
            # Korrektur: Inkrementiere live_shift_counts für alle Schichten
            live_shift_counts[user_id_int][shift_abbrev] += 1
            print(
                f"         -> Fill OK (Runde {round_num}): User {chosen_user['id']} -> {shift_abbrev}. H:{live_user_hours[user_id_int]:.1f}")

            # --- ÄNDERUNG: Else-Block entfernt ---
            # else:
            #     print(
            #         f"         -> Fill DB ERROR (Runde {round_num}) User {chosen_user['id']}: {msg}");
            #     users_unavailable_today.add(
            #         chosen_user['id_str'])
            # --- ENDE ÄNDERUNG ---

        return assigned_count