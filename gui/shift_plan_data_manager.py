# gui/shift_plan_data_manager.py
from datetime import date, datetime, timedelta, time
import calendar
from collections import defaultdict
import traceback

# DB Imports
from database.db_shifts import get_all_data_for_plan_display

from database.db_core import load_config_json, save_config_json
from gui.event_manager import EventManager
from gui.shift_lock_manager import ShiftLockManager

# Importiere ALLE ausgelagerten Manager-Klassen
from gui.shift_plan_conflict_manager import ShiftPlanConflictManager


class ShiftPlanDataManager:
    """
    Verantwortlich für das Laden, Vorverarbeiten und Berechnen aller Daten,
    die für die Anzeige des Dienstplans benötigt werden (Staffing, Stunden, Konflikte).

    Delegiert Konfliktprüfung an ShiftPlanConflictManager.
    Behält Berechnungen und Cache-Verarbeitung intern.
    """

    GENERATOR_CONFIG_KEY = "GENERATOR_SETTINGS_V1"

    def __init__(self, app):
        self.app = app

        # Multi-Monats-Cache
        self.monthly_caches = {}

        # Aktiver Monat
        self.year = 0
        self.month = 0

        # Caches für die *aktiven* Daten
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}

        # Caches für Vormonat
        self._prev_month_shifts = {}
        self.previous_month_shifts = {}
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}

        # Cache für Folgemonat
        self.next_month_shifts = {}

        # Cache für Benutzer
        self.cached_users_for_month = []

        # Manager-Instanzen
        self.shift_lock_manager = ShiftLockManager(app)
        self.conflict_manager = ShiftPlanConflictManager(app, self)

    def _clear_active_caches(self):
        """
        Setzt alle *aktiven* Caches zurück.
        """
        print("[DM] Aktive Caches werden zurückgesetzt...")
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}

        self.conflict_manager.clear_violations()

        self._prev_month_shifts = {}
        self.previous_month_shifts = {}
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}
        self.next_month_shifts = {}
        self.cached_users_for_month = []

        self.shift_lock_manager.locked_shifts = {}

    def clear_all_monthly_caches(self):
        """
        Löscht den gesamten Multi-Monats-Cache (P5).
        """
        print("[DM Cache] Lösche gesamten Monats-Cache (P5)...")
        self.monthly_caches = {}
        self._clear_active_caches()

    def get_previous_month_shifts(self):
        """Gibt die geladenen Schichtdaten des Vormonats für den Generator zurück."""
        return self._prev_month_shifts

    def get_next_month_shifts(self):
        """
        Gibt die Schichtdaten des Folgemonats aus dem Cache zurück.
        """
        return self.next_month_shifts

    @property
    def violation_cells(self):
        """Getter für die violation_cells aus dem ConflictManager."""
        return self.conflict_manager.get_violations()

    # --- Generator Config Methoden (unverändert) ---
    def get_generator_config(self):
        default = {
            'max_consecutive_same_shift': 4,
            'enable_24h_planning': False,
            'preferred_partners_prioritized': []
        }
        loaded = load_config_json(self.GENERATOR_CONFIG_KEY)
        if loaded and 'preferred_partners' in loaded and 'preferred_partners_prioritized' not in loaded:
            # ... (Migration logic)
            migrated_partners = []
            for pair in loaded.get('preferred_partners', []):
                if isinstance(pair, dict) and 'id_a' in pair and 'id_b' in pair:
                    try:
                        migrated_partners.append({
                            'id_a': int(pair['id_a']),
                            'id_b': int(pair['id_b']),
                            'priority': 1
                        })
                    except (ValueError, TypeError):
                        pass
            loaded['preferred_partners_prioritized'] = migrated_partners
        default.update({
            'mandatory_rest_days_after_max_shifts': 2,
            'avoid_understaffing_hard': True,
            'ensure_one_weekend_off': False,
            'wunschfrei_respect_level': 75,
            'fairness_threshold_hours': 10.0,
            'min_hours_fairness_threshold': 20.0,
            'min_hours_score_multiplier': 5.0,
            'fairness_score_multiplier': 1.0,
            'isolation_score_multiplier': 30.0
        })
        final_config = default.copy()
        if loaded:
            final_config.update(loaded)
        return final_config

    def save_generator_config(self, config_data):
        return save_config_json(self.GENERATOR_CONFIG_KEY, config_data)

    # --- ENDE Generator Config Methoden ---

    # --- ZURÜCKGEHOLT: _get_shift_helper ---
    def _get_shift_helper(self, user_id_str, date_obj, current_year, current_month):
        """
        Holt die *Arbeits*-Schicht für einen User an einem Datum, berücksichtigt Vormonat-Cache.
        (Wird von ConflictManager und intern benötigt)
        """
        date_str = date_obj.strftime('%Y-%m-%d')

        shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = self._prev_month_shifts.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = self.next_month_shifts.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = ""

        return shift if shift not in ["", "FREI", None, "U", "X", "EU", "WF", "U?"] else ""

    def load_and_process_data(self, year, month, progress_callback=None, force_reload=False):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch ODER lädt aus dem P5-Cache.
        """
        self.year = year
        self.month = month
        cache_key = (year, month)

        def update_progress(value, text):
            if progress_callback: progress_callback(value, text)

        # 1. PRÜFE GLOBALEN CACHE (P5)
        if cache_key in self.monthly_caches and not force_reload:
            print(f"[DM Cache] Lade Monat {year}-{month} aus dem P5-Cache.")
            update_progress(50, "Lade Daten aus Cache...")

            # Lade P5-Cache in aktive Caches
            cached_data = self.monthly_caches[cache_key]
            self.shift_schedule_data = cached_data['shift_schedule_data']
            self.processed_vacations = cached_data['processed_vacations']
            self.wunschfrei_data = cached_data['wunschfrei_data']
            self.daily_counts = cached_data['daily_counts']
            self.conflict_manager.violation_cells = cached_data['violation_cells']
            self._prev_month_shifts = cached_data['_prev_month_shifts']
            self.previous_month_shifts = cached_data['previous_month_shifts']
            self.processed_vacations_prev = cached_data['processed_vacations_prev']
            self.wunschfrei_data_prev = cached_data['wunschfrei_data_prev']
            self.next_month_shifts = cached_data['next_month_shifts']
            self.cached_users_for_month = cached_data['cached_users_for_month']
            self.shift_lock_manager.locked_shifts = cached_data['locked_shifts']

            update_progress(95, "Vorbereitung abgeschlossen.")
            return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

        # 2. NICHT IM CACHE: Von DB laden
        self._clear_active_caches()
        update_progress(10, "Lade alle Plandaten (Batch-Optimierung)...")

        first_day_current_month = date(year, month, 1)
        current_date_for_archive_check = datetime.combine(first_day_current_month, time(0, 0, 0))

        batch_data = get_all_data_for_plan_display(year, month, current_date_for_archive_check)

        if batch_data is None:
            print("[FEHLER] get_all_data_for_plan_display gab None zurück.")
            raise Exception("Fehler beim Abrufen der Batch-Daten aus der Datenbank.")

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")

        # 2b. Daten in Caches entpacken
        self.cached_users_for_month = batch_data.get('users', [])
        self.shift_lock_manager.locked_shifts = batch_data.get('locks', {})
        self.shift_schedule_data = batch_data.get('shifts', {})
        self.wunschfrei_data = batch_data.get('wunschfrei_requests', {})
        self.daily_counts = batch_data.get('daily_counts', {})
        self._prev_month_shifts = batch_data.get('prev_month_shifts', {})
        self.previous_month_shifts = self._prev_month_shifts
        self.wunschfrei_data_prev = batch_data.get('prev_month_wunschfrei', {})
        self.next_month_shifts = batch_data.get('next_month_shifts', {})

        # --- ZURÜCKGEHOLT: Verarbeitung intern ---
        raw_vacations = batch_data.get('vacation_requests', [])
        self.processed_vacations = self._process_vacations(year, month, raw_vacations)

        raw_vacations_prev = batch_data.get('prev_month_vacations', [])
        prev_month_date = first_day_current_month - timedelta(days=1)
        self.processed_vacations_prev = self._process_vacations(
            prev_month_date.year, prev_month_date.month, raw_vacations_prev
        )

        print(f"[DM Load] Batch-Entpacken abgeschlossen.")

        # 3. Restliche Verarbeitung (Events, Konflikte)
        try:
            if hasattr(self.app, 'app'):
                self.app.app.global_events_data = EventManager.get_events_for_year(year)
            else:
                self.app.global_events_data = EventManager.get_events_for_year(year)
        except Exception as e:
            print(f"[FEHLER] Fehler beim Laden der globalen Events aus DB: {e}")
            if hasattr(self.app, 'app'):
                self.app.app.global_events_data = {}
            else:
                self.app.global_events_data = {}

        print("[DM Load] Tageszählungen (daily_counts) direkt aus Batch übernommen.")

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde)...")
        # Delegiere *nur* die Konfliktprüfung
        self.conflict_manager.update_violation_set_full(year, month)
        update_progress(95, "Vorbereitung abgeschlossen.")

        # 4. Speichere im P5-Cache
        print(f"[DM Cache] Speichere Monat {year}-{month} im P5-Cache.")
        self.monthly_caches[cache_key] = {
            'shift_schedule_data': self.shift_schedule_data,
            'processed_vacations': self.processed_vacations,
            'wunschfrei_data': self.wunschfrei_data,
            'daily_counts': self.daily_counts,
            'violation_cells': self.conflict_manager.get_violations().copy(),
            '_prev_month_shifts': self._prev_month_shifts,
            'previous_month_shifts': self.previous_month_shifts,
            'processed_vacations_prev': self.processed_vacations_prev,
            'wunschfrei_data_prev': self.wunschfrei_data_prev,
            'next_month_shifts': self.next_month_shifts,
            'cached_users_for_month': self.cached_users_for_month,
            'locked_shifts': self.shift_lock_manager.locked_shifts,
        }

        return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

    # --- Delegierte Schnittstelle zur Konfliktprüfung ---
    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Delegiert die inkrementelle Konfliktprüfung an den ConflictManager."""
        cache_key = (date_obj.year, date_obj.month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Entferne {cache_key} wegen inkrementellem Update aus P5-Cache.")
            del self.monthly_caches[cache_key]

        return self.conflict_manager.update_violations_incrementally(user_id, date_obj, old_shift, new_shift)

    # --- ZURÜCKGEHOLT: recalculate_daily_counts_for_day ---
    def recalculate_daily_counts_for_day(self, date_obj, old_shift, new_shift):
        """Aktualisiert self.daily_counts für einen bestimmten Tag nach Schichtänderung."""

        cache_key = (date_obj.year, date_obj.month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Entferne {cache_key} wegen Zählungs-Update aus P5-Cache.")
            del self.monthly_caches[cache_key]

        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[DM Counts] Aktualisiere Zählung für {date_str}: '{old_shift}' -> '{new_shift}'")
        if date_str not in self.daily_counts:
            self.daily_counts[date_str] = {}

        counts_today = self.daily_counts[date_str]

        def should_count_shift(shift_abbr):
            return shift_abbr and shift_abbr not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?']

        if should_count_shift(old_shift):
            counts_today[old_shift] = counts_today.get(old_shift, 1) - 1
            if counts_today[old_shift] <= 0:
                del counts_today[old_shift]

        if should_count_shift(new_shift):
            counts_today[new_shift] = counts_today.get(new_shift, 0) + 1

        if not counts_today and date_str in self.daily_counts:
            del self.daily_counts[date_str]

        print(f"[DM Counts] Neue Zählung für {date_str}: {self.daily_counts.get(date_str, {})}")

    # --- ZURÜCKGEHOLT: _get_app_shift_types ---
    def _get_app_shift_types(self):
        """Hilfsfunktion, um shift_types_data sicher vom Bootloader (app.app) oder der App (app) zu holen."""
        if hasattr(self.app, 'shift_types_data'):
            return self.app.shift_types_data
        if hasattr(self.app, 'app') and hasattr(self.app.app, 'shift_types_data'):
            return self.app.app.shift_types_data
        print("[WARNUNG] shift_types_data weder in app noch in app.app gefunden.")
        return {}

    # --- ZURÜCKGEHOLT: _process_vacations ---
    def _process_vacations(self, year, month, raw_vacations):
        """ Verarbeitet Urlaubsanträge und erstellt eine Map für schnellen Zugriff. """
        processed = defaultdict(dict);

        try:
            month_start = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            month_end = date(year, month, last_day)
        except ValueError as e:
            print(f"[FEHLER] Ungültiges Datum in _process_vacations: Y={year} M={month}. Fehler: {e}")
            return {}

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
                    if month_start <= current_date <= month_end:
                        processed[user_id_str][current_date] = status;
                    if current_date > month_end:
                        break
                    current_date += timedelta(days=1)
            except (ValueError, TypeError, KeyError) as e:
                print(f"[WARNUNG] Fehler beim Verarbeiten von Urlaub ID {req.get('id', 'N/A')}: {e}")

        return dict(processed)

    # --- ZURÜCKGEHOLT: get_min_staffing_for_date ---
    def get_min_staffing_for_date(self, current_date):
        """ Ermittelt die Mindestbesetzungsregeln für ein spezifisches Datum. """
        rules_source = self.app
        if hasattr(self.app, 'app'):
            rules_source = self.app.app

        rules = getattr(rules_source, 'staffing_rules', {});
        min_staffing = {}
        min_staffing.update(rules.get('Daily', {}))
        weekday = current_date.weekday()
        if weekday >= 5:
            min_staffing.update(rules.get('Sa-So', {}))
        elif weekday == 4:
            min_staffing.update(rules.get('Fr', {}))
        else:
            min_staffing.update(rules.get('Mo-Do', {}))

        if hasattr(rules_source, 'is_holiday') and rules_source.is_holiday(current_date):
            min_staffing.update(rules.get('Holiday', {}))

        return {k: int(v) for k, v in min_staffing.items() if
                isinstance(v, (int, str)) and str(v).isdigit() and int(v) >= 0}

    # --- ZURÜCKGEHOLT & KORRIGIERT: calculate_total_hours_for_user ---
    def calculate_total_hours_for_user(self, user_id_str, year, month):
        """ Berechnet die geschätzten Gesamtstunden für einen Benutzer im Monat. """
        total_hours = 0.0;
        try:
            user_id_int = int(user_id_str)
        except ValueError:
            print(f"[WARNUNG] Ungültige user_id_str in calculate_total_hours: {user_id_str}");
            return 0.0

        days_in_month = calendar.monthrange(year, month)[1]
        shift_types_data = self._get_app_shift_types()

        # Überstunden vom Vormonat (N.)
        prev_month_last_day = date(year, month, 1) - timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_month_last_day, year, month)
        if prev_shift == 'N.':
            shift_info_n = shift_types_data.get('N.')
            hours_overlap = 6.0
            if shift_info_n and shift_info_n.get('end_time'):
                try:
                    end_time_n = datetime.strptime(shift_info_n['end_time'], '%H:%M').time();
                    hours_overlap = end_time_n.hour + end_time_n.minute / 60.0
                except ValueError:
                    pass
            total_hours += hours_overlap

        # Stunden des aktuellen Monats
        user_shifts_this_month = self.shift_schedule_data.get(user_id_str, {})
        # --- ZUGRIFF KORREKTUR: Defensiver Zugriff ---
        # Nutze .get(user_id_str, {}) um sicherzustellen, dass immer ein Dict zurückkommt
        user_vacations_this_month = self.processed_vacations.get(user_id_str, {})
        user_requests_this_month = self.wunschfrei_data.get(user_id_str, {})

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')

            shift = user_shifts_this_month.get(date_str, "");
            vacation_status = user_vacations_this_month.get(current_date)
            request_info = user_requests_this_month.get(date_str)

            # --- LOGIK FIX: WENN eine Schicht eingetragen ist, ist diese primär.
            #     Andernfalls greifen Urlaub/Wunschfrei. ---
            actual_shift_for_hours = shift

            if not shift:
                if vacation_status == 'Genehmigt':
                    actual_shift_for_hours = 'U'
                elif request_info and request_info[1] == 'WF' and request_info[0] in ["Genehmigt", "Akzeptiert"]:
                    actual_shift_for_hours = 'X'

            # --- ENDE LOGIK FIX ---

            if actual_shift_for_hours in shift_types_data:
                hours = float(shift_types_data[actual_shift_for_hours].get('hours', 0.0))

                if actual_shift_for_hours == 'N.' and day == days_in_month:
                    shift_info_n = shift_types_data.get('N.')
                    hours_to_deduct = 6.0
                    if shift_info_n and shift_info_n.get('end_time'):
                        try:
                            end_time_n = datetime.strptime(shift_info_n['end_time'], '%H:%M').time();
                            hours_to_deduct = end_time_n.hour + end_time_n.minute / 60.0
                        except ValueError:
                            pass
                    hours -= hours_to_deduct

                total_hours += hours

        return round(total_hours, 2)