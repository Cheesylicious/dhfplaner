# gui/shift_plan_data_manager.py
from datetime import date, datetime, timedelta, time
import calendar
from collections import defaultdict
import traceback  # Import für detailliertere Fehlermeldungen

# DB Imports
from database.db_shifts import get_all_data_for_plan_display
from database.db_core import load_config_json, save_config_json
from gui.event_manager import EventManager
from gui.shift_lock_manager import ShiftLockManager

# --- NEUE IMPORTE (Refactoring Regel 4) ---
# Importiere die Helfer aus dem neuen Unterordner
from .data_manager.dm_violation_manager import ViolationManager
from .data_manager.dm_helpers import DataManagerHelpers
# --- NEUER IMPORT (Regel 2 & 4): Latenz-Problem beheben ---
from gui.planning_assistant import PlanningAssistant


# --- ENDE NEUE IMPORTE ---


class ShiftPlanDataManager:
    """
    Verantwortlich für das Laden, Vorverarbeiten und Berechnen aller Daten,
    die für die Anzeige des Dienstplans benötigt werden (Staffing, Stunden, Konflikte).
    (Refactored, Regel 4: Logik an Helfer-Klassen delegiert)
    """

    # GENERATOR_CONFIG_KEY wird jetzt in DataManagerHelpers verwaltet

    def __init__(self, app):
        self.app = app

        # --- P5: Multi-Monats-Cache ---
        self.monthly_caches = {}

        # Aktiver Monat
        self.year = 0
        self.month = 0

        # Aktive Caches (Daten)
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}
        self.locked_shifts_cache = {}
        self.cached_users_for_month = []

        # --- NEU: user_data_map (wird für PlanningAssistant benötigt) ---
        # Stellt sicher, dass die User-Metadaten immer verfügbar sind
        self.user_data_map = {}
        # --- ENDE NEU ---

        # Aktive Caches (Konflikte)
        self.violation_cells = set()

        # Caches für Vormonat/Folgemonat
        self._prev_month_shifts = {}
        self.previous_month_shifts = {}
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}
        self.next_month_shifts = {}

        # --- NEU: Helfer-Klassen instanziieren ---
        # Wichtig: 'self' (die DataManager-Instanz) wird übergeben
        self.vm = ViolationManager(self)  # Violation Manager
        self.helpers = DataManagerHelpers(self)  # Helpers (Stunden, Config, etc.)

        # --- NEU (Regel 2 & 4): Latenz-Problem beheben ---
        # Initialisiert den Assistenten für sofortige UI-Validierung
        self.planning_assistant = PlanningAssistant(self)
        # --- ENDE NEU ---

        # ShiftLockManager (greift jetzt auf self.locked_shifts_cache zu)
        self.shift_lock_manager = ShiftLockManager(app, self)

    def _clear_active_caches(self):
        """
        Setzt alle *aktiven* Caches zurück.
        """
        print("[DM] Aktive Caches werden zurückgesetzt...")
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}
        self.violation_cells.clear()
        self.locked_shifts_cache = {}
        self._prev_month_shifts = {}
        self.previous_month_shifts = {}
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}
        self.next_month_shifts = {}
        self.cached_users_for_month = []

        # self.user_data_map wird NICHT geleert, da es App-global ist

        # Hinweis: Die Helfer-Caches (z.B. in vm._preprocessed_shift_times)
        # werden *nicht* geleert, da sie global gültig sind (z.B. Schichtzeiten).
        # Wenn Schichtzeiten sich ändern, muss vm.preprocess_shift_times()
        # manuell neu getriggert werden (z.B. durch clear_all_monthly_caches).

    def clear_all_monthly_caches(self):
        """
        Löscht den gesamten Multi-Monats-Cache (P5) UND
        setzt globale Helfer-Caches (wie Schichtzeiten) zurück.
        """
        print("[DM Cache] Lösche gesamten Monats-Cache (P5) und globale Helfer-Caches...")
        self.monthly_caches = {}
        self._clear_active_caches()

        # Setzt auch die Caches in den Helfern zurück
        if hasattr(self.vm, '_preprocessed_shift_times'):
            self.vm._preprocessed_shift_times.clear()
            self.vm._warned_missing_times.clear()

    def invalidate_month_cache(self, year, month):
        """
        Entfernt gezielt einen Monat aus dem P5-Cache (monthly_caches).
        """
        cache_key = (year, month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Invalidiere P5-Cache für Monat {year}-{month}.")
            del self.monthly_caches[cache_key]
        else:
            print(f"[DM Cache] P5-Cache für {year}-{month} war nicht vorhanden (muss nicht invalidiert werden).")

    def get_previous_month_shifts(self):
        return self._prev_month_shifts

    def get_next_month_shifts(self):
        return self.next_month_shifts

    # --- Delegierte Methoden (Regel 4) ---

    def get_generator_config(self):
        """Delegiert an DataManagerHelpers"""
        return self.helpers.get_generator_config()

    def save_generator_config(self, config_data):
        """Delegiert an DataManagerHelpers"""
        return self.helpers.save_generator_config(config_data)

    def get_min_staffing_for_date(self, current_date):
        """Delegiert an DataManagerHelpers"""
        return self.helpers.get_min_staffing_for_date(current_date)

    def calculate_total_hours_for_user(self, user_id_str, year, month):
        """Delegiert an DataManagerHelpers"""
        return self.helpers.calculate_total_hours_for_user(user_id_str, year, month)

    def update_violation_set(self, year, month):
        """Delegiert an ViolationManager"""
        self.vm.update_violation_set(year, month)

    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Delegiert an ViolationManager und invalidiert P5-Cache."""
        # P5-Cache invalidieren (muss hier im DM passieren)
        cache_key = (date_obj.year, date_obj.month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Entferne {cache_key} wegen inkrementellem Update aus P5-Cache.")
            del self.monthly_caches[cache_key]

        # Aufruf an den Helfer
        return self.vm.update_violations_incrementally(user_id, date_obj, old_shift, new_shift)

    # --- Haupt-Ladefunktion (schlanker) ---

    def load_and_process_data(self, year, month, progress_callback=None, force_reload=False):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch ODER lädt aus dem P5-Cache.
        Nutzt Helfer für die Datenverarbeitung.
        """
        cache_key = (year, month)

        def update_progress(value, text):
            if progress_callback: progress_callback(value, text)

        # 1. PRÜFE GLOBALEN CACHE (P5)
        if cache_key in self.monthly_caches and not force_reload:
            print(f"[DM Cache] Lade Monat {year}-{month} aus dem P5-Cache.")
            update_progress(50, "Lade Daten aus Cache...")

            cached_data = self.monthly_caches[cache_key]

            # Atomares Überschreiben der aktiven Caches
            self.year = year
            self.month = month
            self.shift_schedule_data = cached_data['shift_schedule_data']
            self.processed_vacations = cached_data['processed_vacations']
            self.wunschfrei_data = cached_data['wunschfrei_data']
            self.daily_counts = cached_data['daily_counts']
            self.violation_cells = cached_data['violation_cells']
            self._prev_month_shifts = cached_data['_prev_month_shifts']
            self.previous_month_shifts = cached_data['previous_month_shifts']
            self.processed_vacations_prev = cached_data['processed_vacations_prev']
            self.wunschfrei_data_prev = cached_data['wunschfrei_data_prev']
            self.next_month_shifts = cached_data['next_month_shifts']
            self.cached_users_for_month = cached_data['cached_users_for_month']
            self.locked_shifts_cache = cached_data.get('locked_shifts', {})

            # --- NEU: user_data_map aus Cache laden ---
            # (Wichtig für PlanningAssistant, falls App neu gestartet wurde)
            if 'user_data_map' in cached_data:
                self.user_data_map = cached_data['user_data_map']
            # --- ENDE NEU ---

            # Schichtzeiten-Cache (global) sicherstellen (delegiert)
            self.vm.preprocess_shift_times()

            update_progress(95, "Vorbereitung abgeschlossen.")
            # --- KORREKTUR: Rückgabewert an ShiftPlanTab angepasst ---
            return True  # Erfolg
            # --- ENDE KORREKTUR ---

        # 2. NICHT IM CACHE: Von DB laden
        print(f"[DM] Lade Monat {year}-{month} von DB (nicht im P5-Cache).")

        temp_data = {
            'shift_schedule_data': {}, 'processed_vacations': {}, 'wunschfrei_data': {},
            'daily_counts': {}, 'violation_cells': set(), 'locked_shifts_cache': {},
            '_prev_month_shifts': {}, 'previous_month_shifts': {},
            'processed_vacations_prev': {}, 'wunschfrei_data_prev': {},
            'next_month_shifts': {}, 'cached_users_for_month': [],
            'user_data_map': {}  # NEU
        }

        update_progress(10, "Lade alle Plandaten (Batch-Optimierung)...")
        first_day_current_month = date(year, month, 1)
        current_date_for_archive_check = datetime.combine(first_day_current_month, time(0, 0, 0))

        batch_data = get_all_data_for_plan_display(year, month, current_date_for_archive_check)
        if batch_data is None:
            # --- KORREKTUR: Rückgabewert an ShiftPlanTab angepasst ---
            print("[FEHLER] get_all_data_for_plan_display hat None zurückgegeben.")
            return False  # Misserfolg
            # --- ENDE KORREKTUR ---

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")

        # 2b. Daten in temporäre Caches entpacken (delegiert)
        temp_data['cached_users_for_month'] = batch_data.get('users', [])

        # --- NEU: user_data_map füllen (wichtig für PlanningAssistant)
        temp_data['user_data_map'] = {u['id']: u for u in temp_data['cached_users_for_month']}
        # --- ENDE NEU ---

        temp_data['locked_shifts_cache'] = batch_data.get('locks', {})
        temp_data['shift_schedule_data'] = batch_data.get('shifts', {})
        temp_data['wunschfrei_data'] = batch_data.get('wunschfrei_requests', {})
        raw_vacations = batch_data.get('vacation_requests', [])

        # --- Aufruf an Helfer ---
        temp_data['processed_vacations'] = self.helpers.process_vacations(year, month, raw_vacations)

        temp_data['daily_counts'] = batch_data.get('daily_counts', {})
        temp_data['_prev_month_shifts'] = batch_data.get('prev_month_shifts', {})
        temp_data['previous_month_shifts'] = temp_data['_prev_month_shifts']
        temp_data['wunschfrei_data_prev'] = batch_data.get('prev_month_wunschfrei', {})
        raw_vacations_prev = batch_data.get('prev_month_vacations', [])
        prev_month_date = first_day_current_month - timedelta(days=1)

        # --- Aufruf an Helfer ---
        temp_data['processed_vacations_prev'] = self.helpers.process_vacations(prev_month_date.year,
                                                                               prev_month_date.month,
                                                                               raw_vacations_prev)
        temp_data['next_month_shifts'] = batch_data.get('next_month_shifts', {})

        print(f"[DM Load] Batch-Entpacken (temporär) abgeschlossen.")

        # 3. Restliche Verarbeitung
        try:
            if hasattr(self.app, 'app'):
                self.app.app.global_events_data = EventManager.get_events_for_year(year)
            else:
                self.app.global_events_data = EventManager.get_events_for_year(year)
            print(f"[DM Load] Globale Events für {year} aus Datenbank geladen.")
        except Exception as e:
            print(f"[FEHLER] Fehler beim Laden der globalen Events aus DB: {e}")
            if hasattr(self.app, 'app'):
                self.app.app.global_events_data = {}
            else:
                self.app.global_events_data = {}

        print("[DM Load] Tageszählungen (daily_counts) direkt aus Batch übernommen.")

        # Schichtzeiten vorverarbeiten (delegiert)
        self.vm.preprocess_shift_times()

        # 4. Atomares Update der aktiven Caches
        print(f"[DM] Atomares Update: Überschreibe aktive Caches mit Daten für {year}-{month}")
        self.year = year
        self.month = month
        self.shift_schedule_data = temp_data['shift_schedule_data']
        self.processed_vacations = temp_data['processed_vacations']
        self.wunschfrei_data = temp_data['wunschfrei_data']
        self.daily_counts = temp_data['daily_counts']
        self.locked_shifts_cache = temp_data['locked_shifts_cache']
        self._prev_month_shifts = temp_data['_prev_month_shifts']
        self.previous_month_shifts = temp_data['previous_month_shifts']
        self.processed_vacations_prev = temp_data['processed_vacations_prev']
        self.wunschfrei_data_prev = temp_data['wunschfrei_data_prev']
        self.next_month_shifts = temp_data['next_month_shifts']
        self.cached_users_for_month = temp_data['cached_users_for_month']
        self.user_data_map = temp_data['user_data_map']  # NEU

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde)...")
        # Volle Konfliktprüfung (delegiert)
        self.update_violation_set(year, month)  # Füllt self.violation_cells

        update_progress(95, "Vorbereitung abgeschlossen.")

        # 5. Im P5-Cache speichern
        print(f"[DM Cache] Speichere Monat {year}-{month} im P5-Cache.")
        self.monthly_caches[cache_key] = {
            'shift_schedule_data': self.shift_schedule_data,
            'processed_vacations': self.processed_vacations,
            'wunschfrei_data': self.wunschfrei_data,
            'daily_counts': self.daily_counts,
            'violation_cells': self.violation_cells.copy(),
            '_prev_month_shifts': self._prev_month_shifts,
            'previous_month_shifts': self.previous_month_shifts,
            'processed_vacations_prev': self.processed_vacations_prev,
            'wunschfrei_data_prev': self.wunschfrei_data_prev,
            'next_month_shifts': self.next_month_shifts,
            'cached_users_for_month': self.cached_users_for_month,
            'locked_shifts': self.locked_shifts_cache,
            'user_data_map': self.user_data_map  # NEU
        }

        # --- KORREKTUR: Rückgabewert an ShiftPlanTab angepasst ---
        return True  # Erfolg
        # --- ENDE KORREKTUR ---

    def recalculate_daily_counts_for_day(self, date_obj, old_shift, new_shift):
        """Aktualisiert self.daily_counts für einen bestimmten Tag nach Schichtänderung."""

        # P5-Cache invalidieren
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
                # Sicherstellen, dass der Schlüssel existiert, bevor del aufgerufen wird
                if old_shift in counts_today:
                    del counts_today[old_shift]

        if should_count_shift(new_shift):
            counts_today[new_shift] = counts_today.get(new_shift, 0) + 1

        if not counts_today and date_str in self.daily_counts:
            del self.daily_counts[date_str]

        print(f"[DM Counts] Neue Zählung für {date_str}: {self.daily_counts.get(date_str, {})}")

    # --- NEU: Delegierung an PlanningAssistant (behebt den AttributeError) ---
    def get_conflicts_for_shift(self, user_id, date_obj, target_shift_abbrev):
        """
        Delegiert die sofortige Konfliktprüfung an den PlanningAssistant.
        Nutzt nur Cache-Daten (Regel 2).
        """
        return self.planning_assistant.get_conflicts_for_shift(user_id, date_obj, target_shift_abbrev)
    # --- ENDE NEU ---