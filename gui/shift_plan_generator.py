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

# --- ÄNDERUNG: save_shift_entry wird hier nicht mehr benötigt ---
# from database.db_shifts import save_shift_entry

# Imports für ausgelagerte Logik
from .generator.generator_helpers import GeneratorHelpers
from .generator.generator_scoring import GeneratorScoring
from .generator.generator_rounds import GeneratorRounds
# --- NEUER IMPORT für Batch-Speichern ---
from .generator.generator_persistence import save_generation_batch_to_db

# --- NEUE IMPORTS FÜR REFACTORING (Regel 4) ---
from .generator.generator_pre_planning import GeneratorPrePlanner
from .generator.generator_config import GeneratorConfig

# Konstanten (Basis-Konfiguration, die nicht aus der DB kommt)
MAX_MONTHLY_HOURS = 228.0
SOFT_MAX_CONSECUTIVE_SHIFTS = 6
HARD_MAX_CONSECUTIVE_SHIFTS = 8
# --- Parameter für Kritikalität ---
CRITICAL_LOOKAHEAD_DAYS = 14
CRITICAL_BUFFER = 1
# --- ENDE Parameter ---

# Standardwerte für Scores (Werden jetzt primär in GeneratorConfig verwaltet)
LOOKAHEAD_PENALTY_SCORE = 500


class ShiftPlanGenerator:
    """
    Kapselt die Logik zur automatischen Generierung des Schichtplans.
    Orchestriert die Helfer, Scoring- und Runden-Logik.
    Implementiert Pre-Planning mit dynamischer Kritikalitätsprüfung.
    """

    def __init__(self, app, data_manager, year, month, all_users, user_data_map,
                 vacation_requests, wunschfrei_requests, live_shifts_data,
                 locked_shifts_data,
                 holidays_in_month, progress_callback, completion_callback):

        # --- KERN-ATTRIBUTE ---
        self.app = app
        self.data_manager = data_manager
        self.year = year
        self.month = month
        self.all_users = all_users
        self.user_data_map = user_data_map
        self.vacation_requests = vacation_requests
        self.wunschfrei_requests = wunschfrei_requests
        self.initial_live_shifts_data = live_shifts_data
        self.locked_shifts_data = locked_shifts_data
        self.live_shifts_data = {}
        self.holidays_in_month = holidays_in_month
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

        # --- REFACTORING (Regel 4): Konfiguration auslagern ---
        # Die gesamte Konfigurationslogik ist jetzt in self.config
        self.config = GeneratorConfig(data_manager)

        # Direkten Zugriff auf häufig genutzte Konfigurationen herstellen
        self.user_preferences = self.config.user_preferences
        self.partner_priority_map = self.config.partner_priority_map
        self.avoid_priority_map = self.config.avoid_priority_map

        # Harte Strafen aus der Config holen
        self.AVOID_PARTNER_PENALTY_SCORE = self.config.AVOID_PARTNER_PENALTY_SCORE
        # --- ENDE REFACTORING ---

        # --- KORREKTUR (INNOVATION) ---
        # Der Generator soll nur 6, T. und N. aktiv planen.
        self.shifts_to_plan = ["6", "T.", "N."]
        # --- ENDE KORREKTUR ---

        self.shift_hours = {abbrev: float(data.get('hours', 0.0))
                            for abbrev, data in self.app.shift_types_data.items()}
        self.work_shifts = {s for s, data in self.app.shift_types_data.items() if
                            float(data.get('hours', 0.0)) > 0 and s not in ['U', 'EU']}
        self.work_shifts.update(['T.', 'N.', '6', '24'])
        self.free_shifts_indicators = {"", "FREI", "U", "X", "EU", "WF", "U?"}

        # NEU: Schichten, die der Generator niemals überschreiben oder planen darf, wenn sie vorhanden sind.
        # Enthält alle Freischichten, Urlaube und feste Blöcke (QA, S)
        self.fixed_shifts_indicators = {"U", "X", "EU", "WF", "U?", "QA", "S", "24"}

        # Konstanten als Attribute (für einfachen Zugriff durch Helfer)
        self.MAX_MONTHLY_HOURS = MAX_MONTHLY_HOURS
        self.SOFT_MAX_CONSECUTIVE_SHIFTS = SOFT_MAX_CONSECUTIVE_SHIFTS
        self.HARD_MAX_CONSECUTIVE_SHIFTS = HARD_MAX_CONSECUTIVE_SHIFTS
        self.CRITICAL_LOOKAHEAD_DAYS = CRITICAL_LOOKAHEAD_DAYS
        self.CRITICAL_BUFFER = CRITICAL_BUFFER
        self.LOOKAHEAD_PENALTY_SCORE = LOOKAHEAD_PENALTY_SCORE

        # --- REFACTORING (Regel 4): Konfigurierbare Einstellungen ---
        # Diese werden jetzt aus der self.config Instanz bezogen,
        # anstatt sie hier einzeln zu laden.
        self.max_consecutive_same_shift_limit = self.config.max_consecutive_same_shift_limit
        self.mandatory_rest_days = self.config.mandatory_rest_days
        self.avoid_understaffing_hard = self.config.avoid_understaffing_hard
        self.wunschfrei_respect_level = self.config.wunschfrei_respect_level
        self.generator_fill_rounds = self.config.generator_fill_rounds
        self.fairness_threshold_hours = self.config.fairness_threshold_hours
        self.min_hours_fairness_threshold = self.config.min_hours_fairness_threshold
        self.min_hours_score_multiplier = self.config.min_hours_score_multiplier
        self.fairness_score_multiplier = self.config.fairness_score_multiplier
        self.isolation_score_multiplier = self.config.isolation_score_multiplier
        # --- ENDE REFACTORING ---

        # Instanzen der ausgelagerten Logik
        self.helpers = GeneratorHelpers(self)
        self.scoring = GeneratorScoring(self)
        self.rounds = GeneratorRounds(self, self.helpers, self.scoring)

        # --- REFACTORING (Regel 4) ---
        # Pre-Planning Logik auslagern
        self.pre_planner = GeneratorPrePlanner(self, self.helpers)

        # Potenzielle kritische Schichten identifizieren (Vorfilterung)
        # Ruft jetzt die ausgelagerte Methode auf
        self.potential_critical_shifts = self.pre_planner.identify_potential_critical_shifts()
        # --- ENDE REFACTORING ---

        print(
            f"[Generator] Potenzielle kritische Schichten identifiziert (Lookahead={self.CRITICAL_LOOKAHEAD_DAYS}d, Puffer={self.CRITICAL_BUFFER}): {self.potential_critical_shifts if self.potential_critical_shifts else 'Keine'}")
        self.critical_shifts = set()

    def _update_progress(self, value, text):
        if self.progress_callback: self.progress_callback(value, text)

    def run_generation(self):
        self._generate()

    # --- REFACTORING (Regel 4) ---
    # Die Vorausplanungs-Methoden (_identify_potential_critical_shifts,
    # _get_actually_available_count, _pre_plan_critical_shift)
    # sind bereits in generator_pre_planning.py ausgelagert.
    # --- ENDE REFACTORING ---

    def _generate(self):
        """ Führt die eigentliche Generierungslogik aus. """
        try:
            self._update_progress(0, "Initialisiere Planung...")
            days_in_month = calendar.monthrange(self.year, self.month)[1]

            # --- Initialisierung der Live-Daten ---

            # --- NEU (Regel 1 & 4): Berücksichtige gesicherte Schichten ---
            self.live_shifts_data = defaultdict(dict)
            # 1. Lade die normalen Schichten
            for user_id_str, day_data in self.initial_live_shifts_data.items():
                self.live_shifts_data[user_id_str] = day_data.copy()

            # 2. Überschreibe (oder füge hinzu) die gesicherten Schichten
            # (Diese haben Vorrang)
            if self.locked_shifts_data:
                print("[Generator] Wende gesicherte Schichten (Locks) an...")
                for user_id_str, date_data in self.locked_shifts_data.items():
                    if user_id_str not in self.live_shifts_data:
                        self.live_shifts_data[user_id_str] = {}
                    for date_str, locked_shift in date_data.items():
                        # Prüfe, ob das Datum im aktuellen Monat liegt (wichtig!)
                        try:
                            lock_date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                            if lock_date_obj.year == self.year and lock_date_obj.month == self.month:
                                # Überschreibe nur, wenn die gesicherte Schicht
                                # nicht "leer" ist (obwohl das nie passieren sollte)
                                if locked_shift:
                                    self.live_shifts_data[user_id_str][date_str] = locked_shift
                        except ValueError:
                            continue  # Ungültiges Datum im Lock-Cache ignorieren
            # --- ENDE NEU ---

            self.live_user_hours = defaultdict(float)
            live_shift_counts = defaultdict(lambda: defaultdict(int))
            live_shift_counts_ratio = defaultdict(lambda: defaultdict(int))

            # WICHTIG: Diese Schleife muss *nach* dem Laden der Locks laufen
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

                    if shift in self.shifts_to_plan:
                        live_shift_counts[user_id_int][shift] += 1
            # --- Ende Initialisierung ---

            # HINWEIS: Die Logik zur dynamischen Prüfung (get_actually_available_count)
            # und zur Vorab-Zuweisung (pre_plan_critical_shift) war im
            # Originalcode vorhanden, wurde aber in _generate() nicht aktiv
            # aufgerufen. Sie ist nun korrekt im PrePlanner gekapselt,
            # falls sie zukünftig reaktiviert wird.

            self._update_progress(10, "Starte Hauptplanung...")

            total_steps = days_in_month * len(self.shifts_to_plan)
            current_step = 0

            # Hauptschleife: Tage
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')

                # --- KORREKTE MINDESTBESETZUNG LOGIK (SONDERTERMINE IGNORIEREN) ---
                try:
                    min_staffing_today = self.data_manager.get_min_staffing_for_date(current_date_obj)
                    is_event_day = False
                    if min_staffing_today:
                        if min_staffing_today.get('S', 0) > 0 or min_staffing_today.get('QA', 0) > 0:
                            is_event_day = True
                    if is_event_day:
                        base_staffing_rules = self.app.staffing_rules
                        is_holiday_today = current_date_obj in self.holidays_in_month
                        base_staffing_today = {}
                        if is_holiday_today and 'holiday_staffing' in base_staffing_rules:
                            base_staffing_today = base_staffing_rules['holiday_staffing'].copy()
                        else:
                            weekday_str = str(current_date_obj.weekday())
                            if weekday_str in base_staffing_rules.get('weekday_staffing', {}):
                                base_staffing_today = base_staffing_rules['weekday_staffing'][weekday_str].copy()
                        for shift in self.shifts_to_plan:
                            if shift in base_staffing_today:
                                min_staffing_today[shift] = base_staffing_today[shift]
                except Exception as staffing_err:
                    min_staffing_today = {};
                    print(f"[WARN] Staffing Error {date_str}: {staffing_err}")
                    traceback.print_exc()
                # --- ENDE MINDESTBESETZUNG LOGIK ---

                # Schleife: Schichten (self.shifts_to_plan ist jetzt ["6", "T.", "N."])
                for shift_abbrev in self.shifts_to_plan:
                    current_step += 1;
                    progress_perc = int(10 + (current_step / total_steps) * 85);
                    self._update_progress(progress_perc, f"Plane {shift_abbrev} für {date_str}...")

                    # --- NEUER VORDURCHLAUF (pro Schicht) ---
                    users_unavailable_today = set();
                    existing_dog_assignments = defaultdict(list);
                    assignments_today_by_shift = defaultdict(set)

                    for user_id_int, user_data in self.user_data_map.items():
                        user_id_str = str(user_id_int);
                        user_dog = user_data.get('diensthund');
                        is_unavailable, is_working = False, False

                        # --- KORREKTUR (PROBLEM 1: LOCKS): Explizite Prüfung auf Schichtsicherung ---
                        # Wir prüfen die Rohdaten der Locks, nicht die live_shifts_data
                        is_locked = self.locked_shifts_data.get(user_id_str, {}).get(date_str) is not None

                        if is_locked:
                            users_unavailable_today.add(user_id_str)

                            # Stelle sicher, dass die gesicherte Schicht in assignments_today landet
                            # (Wir müssen sie aus live_shifts_data holen, da sie dort beim Init geladen wurde)
                            locked_shift = self.live_shifts_data.get(user_id_str, {}).get(date_str)

                            if locked_shift:
                                assignments_today_by_shift[locked_shift].add(user_id_int)
                                if user_dog and user_dog != '---':
                                    existing_dog_assignments[user_dog].append(
                                        {'user_id': user_id_int, 'shift': locked_shift})

                            continue  # Gehe zum nächsten User, dieser ist gesperrt
                        # --- ENDE KORREKTUR (PROBLEM 1) ---

                        existing_shift = self.live_shifts_data.get(user_id_str, {}).get(date_str)

                        # Regel 1: Urlaub/WF (ganztägig)
                        if self.vacation_requests.get(user_id_str, {}).get(current_date_obj) in ['Approved',
                                                                                                 'Genehmigt']:
                            is_unavailable = True
                        elif date_str in self.wunschfrei_requests.get(user_id_str, {}):
                            wf_entry = self.wunschfrei_requests[user_id_str][date_str]
                            wf_status, wf_shift = None, None
                            if isinstance(wf_entry, tuple) and len(wf_entry) >= 1: wf_status = wf_entry[0]
                            if wf_status in ['Approved', 'Genehmigt', 'Akzeptiert']:
                                if not wf_entry[1]:
                                    is_unavailable = True  # Ganztägig
                                elif wf_entry[1] == shift_abbrev:
                                    is_unavailable = True  # Blockiert diese Schicht

                        # Regel 2: Bereits vorhandene Schichten (die NICHT gesichert sind)
                        if existing_shift:
                            is_working = True
                            assignments_today_by_shift[existing_shift].add(user_id_int)

                            # Blockiere, wenn fest (QA, S, U...)
                            if existing_shift in self.fixed_shifts_indicators:
                                is_unavailable = True

                            # Blockiere, wenn eine *andere* Schicht geplant wird
                            elif existing_shift != shift_abbrev:
                                is_unavailable = True

                        if is_unavailable:
                            users_unavailable_today.add(user_id_str)
                        elif is_working:
                            users_unavailable_today.add(user_id_str)

                        if is_working and user_dog and user_dog != '---':
                            existing_dog_assignments[user_dog].append({'user_id': user_id_int, 'shift': existing_shift})
                    # --- ENDE NEUER VORDURCHLAUF ---

                    # Logik für "6" Schicht
                    is_friday_6 = shift_abbrev == '6' and current_date_obj.weekday() == 4;
                    is_holiday_6 = shift_abbrev == '6' and current_date_obj in self.holidays_in_month
                    if shift_abbrev == '6' and not (is_friday_6 or is_holiday_6): continue

                    required_count = min_staffing_today.get(shift_abbrev, 0);
                    if required_count <= 0: continue

                    current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()));
                    needed_now = required_count - current_assigned_count
                    if needed_now <= 0: continue
                    print(
                        f"   -> Need {needed_now} for '{shift_abbrev}' @ {date_str} (Req:{required_count}, Has:{current_assigned_count})")

                    # --- KORREKTUR (Regel 1): `while`-Schleife (Fix 2) ---
                    while needed_now > 0:
                        assigned_this_loop = 0

                        # Runde 1 (Fair)
                        assigned_in_round_1 = self.rounds.run_fair_assignment_round(
                            shift_abbrev, current_date_obj,
                            users_unavailable_today,
                            existing_dog_assignments,
                            assignments_today_by_shift,
                            self.live_user_hours, live_shift_counts,
                            live_shift_counts_ratio,
                            1,  # HIER: Harte 1
                            days_in_month
                        )
                        assigned_this_loop += assigned_in_round_1

                        # Runden 2, 3, 4 (Fill)
                        if assigned_this_loop == 0 and self.generator_fill_rounds >= 1:
                            assigned_in_round_2 = self.rounds.run_fill_round(
                                shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                                assignments_today_by_shift, self.live_user_hours, live_shift_counts,
                                live_shift_counts_ratio,
                                1, round_num=2  # HIER: Harte 1
                            )
                            assigned_this_loop += assigned_in_round_2

                        if assigned_this_loop == 0 and self.generator_fill_rounds >= 2:
                            assigned_in_round_3 = self.rounds.run_fill_round(
                                shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                                assignments_today_by_shift, self.live_user_hours, live_shift_counts,
                                live_shift_counts_ratio,
                                1, round_num=3  # HIER: Harte 1
                            )
                            assigned_this_loop += assigned_in_round_3

                        if assigned_this_loop == 0 and self.generator_fill_rounds >= 3:
                            assigned_in_round_4 = self.rounds.run_fill_round(
                                shift_abbrev, current_date_obj, users_unavailable_today, existing_dog_assignments,
                                assignments_today_by_shift, self.live_user_hours, live_shift_counts,
                                live_shift_counts_ratio,
                                1, round_num=4  # HIER: Harte 1
                            )
                            assigned_this_loop += assigned_in_round_4

                        if assigned_this_loop == 0:
                            break

                        # --- KORREKTUR (Regel 1): State-Update (Fix 3 & 4) ---
                        # Aktualisiere die Vordurchlauf-Variablen für den
                        # nächsten Durchlauf der *while*-Schleife.

                        newly_assigned_id = None
                        current_assigned_ids_str = {str(uid) for uid in
                                                    assignments_today_by_shift.get(shift_abbrev, set())}

                        for user_id_str in current_assigned_ids_str:
                            if user_id_str not in users_unavailable_today:
                                newly_assigned_id = int(user_id_str)
                                break

                        if newly_assigned_id:
                            newly_assigned_id_str = str(newly_assigned_id)
                            users_unavailable_today.add(newly_assigned_id_str)

                            user_data = self.user_data_map.get(newly_assigned_id)
                            if user_data:
                                user_dog = user_data.get('diensthund')
                                if user_dog and user_dog != '---':
                                    existing_dog_assignments[user_dog].append(
                                        {'user_id': newly_assigned_id, 'shift': shift_abbrev}
                                    )
                        # --- ENDE State-Update ---

                        current_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()))
                        needed_now = required_count - current_assigned_count

                    # --- ENDE KORREKTUR (Regel 1) ---

                    final_assigned_count = len(assignments_today_by_shift.get(shift_abbrev, set()))
                    if final_assigned_count < required_count: print(
                        f"   -> [WARNUNG] Mindestbesetzung für '{shift_abbrev}' an {date_str} NICHT erreicht (Req: {required_count}, Assigned: {final_assigned_count}).")

            # --- NEU: Batch-Speichern am Ende aller Schleifen ---
            self._update_progress(95, "Speichere Plan in Datenbank...")

            success, saved_count_batch, error_msg_batch = save_generation_batch_to_db(
                self.live_shifts_data,
                self.year,
                self.month
            )

            if not success:
                print(f"KRITISCHER FEHLER: Das Speichern des Batch-Plans ist fehlgeschlagen: {error_msg_batch}")
                if self.completion_callback:
                    err_msg = f"Fehler beim Batch-Speichern:\n{error_msg_batch}"
                    self.app.after(100, lambda: self.completion_callback(False, 0, err_msg))
                return

                # --- ENDE NEU ---

            self._update_progress(100, "Generierung abgeschlossen.")
            final_hours_list = sorted(self.live_user_hours.items(), key=lambda item: item[1], reverse=True)
            print("Finale Stunden nach Generierung:", [(uid, f"{h:.1f}") for uid, h in final_hours_list])

            print("Finale Schichtzählungen (T./N./6):")
            for user_id_int in sorted(self.live_user_hours.keys()):
                counts = live_shift_counts[user_id_int];
                print(
                    f"  User {user_id_int}: T:{counts.get('T.', 0)}, N:{counts.get('N.', 0)}, 6:{counts.get('6', 0)}")

            if self.completion_callback:
                self.app.after(100, lambda sc=saved_count_batch: self.completion_callback(True, sc, None))

        except Exception as e:
            print(f"Fehler im Generierungs-Thread: {e}");
            traceback.print_exc()
            if self.completion_callback: error_msg = f"Ein Fehler ist aufgetreten:\n{e}"; self.app.after(100,
                                                                                                         lambda: self.completion_callback(
                                                                                                             False, 0,
                                                                                                             error_msg))