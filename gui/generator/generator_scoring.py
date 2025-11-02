# gui/generator/generator_scoring.py
from datetime import timedelta


class GeneratorScoring:
    """
    Kapselt die Scoring-Logik für die "Runde 1" (Faire Zuweisung) des Generators,
    jetzt mit integriertem Lookahead-Scoring zur Bewertung zukünftiger Konflikte.
    """
    # Wie viele Tage vorausschauen für die Konfliktzählung?
    CONFLICT_LOOKAHEAD_DAYS = 7

    def __init__(self, generator_instance):
        self.gen = generator_instance

    def _check_rule_violation_at_date(self, candidate_id_str, check_date, check_shift):
        """
        Prüft, ob der Mitarbeiter an 'check_date' die Schicht 'check_shift'
        machen könnte, basierend auf dem *aktuellen* Planungsstand in live_shifts_data
        und den harten Regeln. Gibt True zurück, wenn eine Regel verletzt wird.
        (Diese Funktion ist ähnlich zu Teilen von _get_actually_available_count)
        """
        date_str = check_date.strftime('%Y-%m-%d')

        # --- Allgemeine Verfügbarkeit prüfen (Urlaub, WF, bestehende Schicht) ---
        # WICHTIG: Prüfe nur, ob der Tag generell blockiert ist. Die spezifische Schicht
        # wird später durch Regeln geprüft.
        if self.gen.vacation_requests.get(candidate_id_str, {}).get(check_date) in ['Approved',
                                                                                    'Genehmigt']: return True  # Urlaub
        if date_str in self.gen.wunschfrei_requests.get(candidate_id_str, {}):
            wf_entry = self.gen.wunschfrei_requests[candidate_id_str][date_str]
            wf_status, wf_shift = None, None
            if isinstance(wf_entry, tuple) and len(wf_entry) >= 2: wf_status, wf_shift = wf_entry[0], wf_entry[1]
            if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert']:
                if wf_shift == "" or wf_shift == check_shift: return True  # WF(Tag) oder WF(Schicht)
        existing_shift = self.gen.live_shifts_data.get(candidate_id_str, {}).get(date_str)
        if existing_shift and existing_shift not in self.gen.free_shifts_indicators: return True  # Hat schon Schicht

        # --- Harte Regeln prüfen ---
        user_pref = self.gen.user_preferences[candidate_id_str]
        user_dog = self.gen.user_data_map.get(int(candidate_id_str), {}).get('diensthund')
        current_hours = self.gen.live_user_hours.get(int(candidate_id_str), 0.0)
        hours_for_this_shift = self.gen.shift_hours.get(check_shift, 0.0)
        max_hours_override = user_pref.get('max_monthly_hours')

        prev_date_obj = check_date - timedelta(days=1)
        two_days_ago_obj = check_date - timedelta(days=2)

        # Helferfunktionen verwenden
        prev_shift = self.gen.helpers.get_previous_shift(candidate_id_str, prev_date_obj)
        one_day_ago_raw_shift = self.gen.helpers.get_previous_raw_shift(candidate_id_str, prev_date_obj)
        two_days_ago_shift = self.gen.helpers.get_previous_shift(candidate_id_str, two_days_ago_obj)

        # N -> T/6
        if prev_shift == "N." and check_shift in ["T.", "6"]: return True

        # NEUE HARD RULE: N. -> QA/S Block
        if prev_shift == "N." and check_shift in ["QA", "S"]: return True

        # N-F-T
        if check_shift == "T." and one_day_ago_raw_shift in self.gen.free_shifts_indicators and two_days_ago_shift == "N.": return True
        # Schicht-Ausschluss
        if check_shift in user_pref.get('shift_exclusions', []): return True
        # Max Consecutive (HARD LIMIT)
        consecutive_days = self.gen.helpers.count_consecutive_shifts(candidate_id_str, check_date)
        if consecutive_days >= self.gen.HARD_MAX_CONSECUTIVE_SHIFTS: return True
        # Mandatory Rest
        if self.gen.mandatory_rest_days > 0 and consecutive_days == 0 and not self.gen.helpers.check_mandatory_rest(
                candidate_id_str, check_date): return True
        # Max Stunden
        max_hours_check = max_hours_override if max_hours_override is not None else self.gen.MAX_MONTHLY_HOURS
        if current_hours + hours_for_this_shift > max_hours_check: return True

        return False  # Keine Regelverletzung gefunden

    # NEUE Funktion zur Konfliktzählung
    def _calculate_future_conflicts(self, candidate_id_str, current_date, assigned_shift_today):
        """
        Simuliert die Zuweisung von 'assigned_shift_today' am 'current_date' und zählt,
        wie viele Schichten der Mitarbeiter in den nächsten CONFLICT_LOOKAHEAD_DAYS
        aufgrund *neu entstehender* Regelverletzungen (N->T, N-F-T, MaxConsec, MandRest, N->QA/S)
        nicht mehr machen könnte.
        """
        conflict_count = 0

        # Temporäre Simulation der heutigen Zuweisung im live_shifts_data
        original_shift = self.gen.live_shifts_data.get(candidate_id_str, {}).get(current_date.strftime('%Y-%m-%d'))
        if candidate_id_str not in self.gen.live_shifts_data: self.gen.live_shifts_data[
            candidate_id_str] = {}  # Sicherstellen
        self.gen.live_shifts_data[candidate_id_str][current_date.strftime('%Y-%m-%d')] = assigned_shift_today

        # Iteriere durch die nächsten X Tage
        for i in range(1, self.CONFLICT_LOOKAHEAD_DAYS + 1):
            future_date = current_date + timedelta(days=i)
            # Prüfe nur Tage im aktuellen Monat (optional, könnte man erweitern)
            if future_date.month != current_date.month: break

            # Iteriere durch mögliche Schichten an diesem zukünftigen Tag
            for future_shift in self.gen.shifts_to_plan:

                # Prüfe harte Regeln mit dem *simulierten* heutigen Eintrag
                if self._check_rule_violation_at_date(candidate_id_str, future_date, future_shift):
                    # Jetzt prüfen wir, ob die Regelverletzung *durch* die heutige Schicht verursacht wurde.

                    # N->T/6 Konflikt durch heutige Zuweisung?
                    if i == 1 and assigned_shift_today == "N." and future_shift in ["T.", "6"]:
                        conflict_count += 1
                        continue  # Nächste Schicht prüfen

                    # NEUER KONFLIKT: N. -> QA/S durch heutige Zuweisung?
                    if i == 1 and assigned_shift_today == "N." and future_shift in ["QA", "S"]:
                        conflict_count += 1
                        continue

                    # N-F-T Konflikt durch heutige Zuweisung?
                    if i == 2 and assigned_shift_today == "N." and future_shift == "T.":
                        intermediate_shift_simulated = self.gen.helpers.get_previous_raw_shift(candidate_id_str,
                                                                                               future_date)  # Holt Schicht von Tag i=1
                        if intermediate_shift_simulated is None or intermediate_shift_simulated in self.gen.free_shifts_indicators:
                            conflict_count += 1
                            continue

                    # Max Consecutive / Mandatory Rest Konflikt durch heutige Zuweisung?
                    consecutive_days_at_future = self.gen.helpers.count_consecutive_shifts(candidate_id_str,
                                                                                           future_date)
                    if consecutive_days_at_future >= self.gen.HARD_MAX_CONSECUTIVE_SHIFTS:
                        # War die Kette *vor* heute schon zu lang?
                        consecutive_days_before_today = self.gen.helpers.count_consecutive_shifts(candidate_id_str,
                                                                                                  current_date)
                        if consecutive_days_before_today < self.gen.HARD_MAX_CONSECUTIVE_SHIFTS:
                            # Ja, die heutige Schicht hat die Kette über das Limit gebracht
                            conflict_count += 1
                            continue

                    is_resting_violated = (self.gen.mandatory_rest_days > 0 and
                                           consecutive_days_at_future == 0 and not
                                           self.gen.helpers.check_mandatory_rest(candidate_id_str, future_date))
                    if is_resting_violated:
                        # War die Ruhezeit *vor* heute schon verletzt oder erst durch die heutige Schicht?
                        consecutive_days_incl_today = self.gen.helpers.count_consecutive_shifts(candidate_id_str,
                                                                                                current_date + timedelta(
                                                                                                    days=1))
                        if consecutive_days_incl_today >= self.gen.HARD_MAX_CONSECUTIVE_SHIFTS:
                            days_since_today = (future_date - current_date).days
                            if days_since_today <= self.gen.mandatory_rest_days:
                                # Die heutige Schicht hat die Ruhezeitverletzung verursacht
                                conflict_count += 1
                                continue

        # WICHTIG: Simulation zurücksetzen!
        if original_shift is None:
            # Wenn vorher kein Eintrag da war, lösche den simulierten
            if current_date.strftime('%Y-%m-%d') in self.gen.live_shifts_data.get(candidate_id_str, {}):
                del self.gen.live_shifts_data[candidate_id_str][current_date.strftime('%Y-%m-%d')]
        else:
            # Setze auf den ursprünglichen Wert zurück
            self.gen.live_shifts_data[candidate_id_str][current_date.strftime('%Y-%m-%d')] = original_shift

        return conflict_count

    def calculate_scores(self, candidate, average_hours, available_candidate_ids,
                         shift_abbrev, live_shift_counts_ratio,
                         assignments_today_by_shift,
                         current_date_obj, days_in_month):  # critical_shifts entfernt
        """
        Berechnet alle Scores für einen einzelnen Kandidaten in Runde 1.
        """
        candidate_id = candidate['id']
        candidate_id_str = candidate['id_str']
        scores = {
            'min_hours_score': 0,
            'fairness_score': 0,
            'partner_score': 1000,
            'avoid_score': 0, # NEU: Score für zu vermeidende Partner
            'isolation_score': 0,
            'ratio_pref_score': 0,
            'future_conflict_score': 0  # NEUER Score
        }

        day_factor = max(0.01, (current_date_obj.day / days_in_month))

        # 1. Min Hours Score
        min_hours_pref = candidate['user_pref'].get('min_monthly_hours')
        if min_hours_pref is not None:
            hours_to_min = min_hours_pref - candidate['hours']
            if hours_to_min > self.gen.min_hours_fairness_threshold:
                scores['min_hours_score'] = self.gen.min_hours_score_multiplier * day_factor
            elif hours_to_min > 0:
                scores['min_hours_score'] = 1 * day_factor

        # 2. Fairness Score
        hours_diff = average_hours - candidate['hours']
        if hours_diff > self.gen.fairness_threshold_hours: scores[
            'fairness_score'] = self.gen.fairness_score_multiplier * day_factor

        # 3. Partner Score
        if candidate_id in self.gen.partner_priority_map:
            for prio, partner_id in self.gen.partner_priority_map[candidate_id]:
                if partner_id in available_candidate_ids:
                    scores['partner_score'] = prio;
                    break
                elif partner_id in assignments_today_by_shift.get(shift_abbrev, set()):
                    scores['partner_score'] = 100 + prio;
                    break

        # 4. NEU: Avoid Score (Konflikt-Partner)
        if candidate_id in self.gen.avoid_priority_map:
            # Hole das Set der bereits für diese Schicht eingeteilten Mitarbeiter
            assigned_to_this_shift = assignments_today_by_shift.get(shift_abbrev, set())
            if assigned_to_this_shift: # Nur prüfen, wenn schon jemand da ist
                for prio, avoid_id in self.gen.avoid_priority_map[candidate_id]:
                    if avoid_id in assigned_to_this_shift:
                        # Konflikt gefunden! Strafe basierend auf Priorität.
                        # Prio 1 = höchste Strafe.
                        # Wir verwenden eine hohe Basisstrafe, die durch die Prio moduliert wird.
                        # (Niedrigere Prio-Zahl = Schlimmerer Konflikt)
                        scores['avoid_score'] = self.gen.AVOID_PARTNER_PENALTY_SCORE / max(1, prio)
                        break # Ein Konflikt reicht

        # 5. Isolation Score
        scores['isolation_score'] = candidate.get('is_isolated', False) * self.gen.isolation_score_multiplier

        # 6. Ratio Preference Score (T/N)
        scale_pref = candidate['user_pref'].get('ratio_preference_scale', 50)
        if scale_pref != 50:
            t_or_6_count = live_shift_counts_ratio[candidate_id].get('T_OR_6', 0);
            n_dot_count = live_shift_counts_ratio[candidate_id].get('N_DOT', 0)
            total_tn = t_or_6_count + n_dot_count;
            current_ratio_t = 0.5 if total_tn == 0 else t_or_6_count / total_tn
            target_ratio_t = scale_pref / 100.0;
            ratio_deviation = current_ratio_t - target_ratio_t
            is_day_shift = shift_abbrev in ['T.', '6'];
            is_night_shift = shift_abbrev == 'N.'
            if is_day_shift:
                if target_ratio_t > 0.5 and ratio_deviation < 0:
                    scores['ratio_pref_score'] = (-1 * abs(ratio_deviation) * 2) * day_factor
                elif target_ratio_t < 0.5 and ratio_deviation > 0:
                    scores['ratio_pref_score'] = (abs(ratio_deviation) * 2) * day_factor
            elif is_night_shift:
                if target_ratio_t < 0.5 and ratio_deviation > 0:
                    scores['ratio_pref_score'] = (-1 * abs(ratio_deviation) * 2) * day_factor
                elif target_ratio_t > 0.5 and ratio_deviation < 0:
                    scores['ratio_pref_score'] = (abs(ratio_deviation) * 2) * day_factor

        # 7. NEU: Future Conflict Score
        # Nur berechnen, wenn nicht am Monatsende (da Lookahead sonst sinnlos)
        if (days_in_month - current_date_obj.day) >= 1:
            # KORREKTUR: Übergibt shift_abbrev als assigned_shift_today
            scores['future_conflict_score'] = self._calculate_future_conflicts(
                candidate_id_str, current_date_obj, shift_abbrev
            )
            scores['future_conflict_score'] *= 10

        return scores