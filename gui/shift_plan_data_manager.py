from datetime import date, datetime, timedelta, time
import calendar
from collections import defaultdict
import traceback
import threading  # NEU: Importiert für asynchrones Cache-Löschen

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
        # --- KORREKTUR: Entferne super().__init__(app) (zur Vermeidung von TypeError) ---
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

        # --- KORREKTUR (Fix für Stunden-Bug) ---
        self.user_shift_totals = {}
        # --- ENDE KORREKTUR ---

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

    # --- NEUE HILFSFUNKTION FÜR RACE CONDITION FIX ---
    def _initialize_user_shift_totals(self, user_data_map):
        """
        Stellt sicher, dass self.user_shift_totals ALLE Benutzer-IDs enthält,
        initialisiert mit 0.0, um den Race Condition (Null-Bug) beim
        inkrementellen Live-Update zu verhindern.
        """
        # (Unverändert)
        all_relevant_user_ids = user_data_map.keys()

        if not isinstance(self.user_shift_totals, dict):
            self.user_shift_totals = {}

        for user_id in all_relevant_user_ids:
            user_id_str = str(user_id)
            if user_id_str not in self.user_shift_totals or 'hours_total' not in self.user_shift_totals[user_id_str]:
                self.user_shift_totals[user_id_str] = {
                    'hours_total': 0.0,
                    'shifts_total': 0
                }

        print(f"[DM Cache] Initialisiere/Verifiziere {len(all_relevant_user_ids)} Benutzer-Totals im Cache.")

    # --- ENDE NEUE HILFSFUNKTION ---

    def _clear_active_caches(self):
        """
        Setzt alle *aktiven* Caches zurück.
        """
        # (Unverändert)
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
        self.user_shift_totals = {}
        # self.user_data_map wird NICHT geleert

    def clear_all_monthly_caches(self):
        """
        Löscht den gesamten Multi-Monats-Cache (P5) UND
        setzt globale Helfer-Caches (wie Schichtzeiten) zurück.
        """
        # (Unverändert)
        print("[DM Cache] Lösche gesamten Monats-Cache (P5) und globale Helfer-Caches...")
        self.monthly_caches = {}
        self._clear_active_caches()

        if hasattr(self.vm, '_preprocessed_shift_times'):
            self.vm._preprocessed_shift_times.clear()
            self.vm._warned_missing_times.clear()

    def invalidate_month_cache(self, year, month):
        """
        Entfernt gezielt einen Monat aus dem P5-Cache (monthly_caches).
        """
        # (Unverändert)
        cache_key = (year, month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Invalidiere P5-Cache für Monat {year}-{month}.")
            del self.monthly_caches[cache_key]
        else:
            print(f"[DM Cache] P5-Cache für {year}-{month} war nicht vorhanden (muss nicht invalidiert werden).")

    def get_previous_month_shifts(self):
        # (Unverändert)
        return self._prev_month_shifts

    def get_next_month_shifts(self):
        # (Unverändert)
        return self.next_month_shifts

    # --- Delegierte Methoden (Regel 4) ---

    def get_generator_config(self):
        # (Unverändert)
        return self.helpers.get_generator_config()

    def save_generator_config(self, config_data):
        # (Unverändert)
        return self.helpers.save_generator_config(config_data)

    def get_min_staffing_for_date(self, current_date):
        # (Unverändert)
        return self.helpers.get_min_staffing_for_date(current_date)

    def calculate_total_hours_for_user(self, user_id_str, year, month):
        # (Unverändert)
        return self.helpers.calculate_total_hours_for_user(user_id_str, year, month)

    def _calculate_user_shift_totals(self, shift_data, user_data_map, shift_types_data):
        """
        Placeholder für die langsame Berechnung der Ist-Stunden-Totals.
        """
        # (Unverändert)
        print("[DM] Starte langsame Berechnung der user_shift_totals...")
        return self.helpers.calculate_user_shift_totals_from_db(shift_data, user_data_map, shift_types_data)

    def update_violation_set(self, year, month):
        # (Unverändert)
        self.vm.update_violation_set(year, month)

    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Delegiert an ViolationManager und invalidiert P5-Cache (JETZT ASYNCHRON)."""

        # P5-Cache invalidieren (jetzt asynchron, ausgelöst durch den Aufrufer)
        # (Die Logik wurde nach recalculate_daily_counts_for_day verschoben,
        #  da update_violations_incrementally bereits asynchron ist)

        # Aufruf an den Helfer
        return self.vm.update_violations_incrementally(user_id, date_obj, old_shift, new_shift)

    # --- Haupt-Ladefunktion (schlanker) ---

    def load_and_process_data(self, year, month, progress_callback=None, force_reload=False):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch ODER lädt aus dem P5-Cache.
        Nutzt Helfer für die Datenverarbeitung.
        """
        # (Funktion ist unverändert)
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

            if 'user_data_map' in cached_data:
                self.user_data_map = cached_data['user_data_map']
            if 'user_shift_totals' in cached_data:
                self.user_shift_totals = cached_data['user_shift_totals']

            if self.user_data_map:
                self._initialize_user_shift_totals(self.user_data_map)

            self.vm.preprocess_shift_times()
            update_progress(95, "Vorbereitung abgeschlossen.")
            return True  # Erfolg

        # 2. NICHT IM CACHE: Von DB laden
        print(f"[DM] Lade Monat {year}-{month} von DB (nicht im P5-Cache).")

        temp_data = {
            'shift_schedule_data': {}, 'processed_vacations': {}, 'wunschfrei_data': {},
            'daily_counts': {}, 'violation_cells': set(), 'locked_shifts_cache': {},
            '_prev_month_shifts': {}, 'previous_month_shifts': {},
            'processed_vacations_prev': {}, 'wunschfrei_data_prev': {},
            'next_month_shifts': {}, 'cached_users_for_month': [],
            'user_data_map': {},
            'user_shift_totals': {}
        }

        update_progress(10, "Lade alle Plandaten (Batch-Optimierung)...")
        first_day_current_month = date(year, month, 1)
        current_date_for_archive_check = datetime.combine(first_day_current_month, time(0, 0, 0))

        batch_data = get_all_data_for_plan_display(year, month, current_date_for_archive_check)
        if batch_data is None:
            print("[FEHLER] get_all_data_for_plan_display hat None zurückgegeben.")
            return False

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")

        temp_data['cached_users_for_month'] = batch_data.get('users', [])
        temp_data['user_data_map'] = {u['id']: u for u in temp_data['cached_users_for_month']}
        temp_data['locked_shifts_cache'] = batch_data.get('locks', {})
        temp_data['shift_schedule_data'] = batch_data.get('shifts', {})
        temp_data['wunschfrei_data'] = batch_data.get('wunschfrei_requests', {})
        raw_vacations = batch_data.get('vacation_requests', [])
        temp_data['processed_vacations'] = self.helpers.process_vacations(year, month, raw_vacations)
        temp_data['daily_counts'] = batch_data.get('daily_counts', {})
        temp_data['_prev_month_shifts'] = batch_data.get('prev_month_shifts', {})
        temp_data['previous_month_shifts'] = temp_data['_prev_month_shifts']
        temp_data['wunschfrei_data_prev'] = batch_data.get('prev_month_wunschfrei', {})
        raw_vacations_prev = batch_data.get('prev_month_vacations', [])
        prev_month_date = first_day_current_month - timedelta(days=1)
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
        self.vm.preprocess_shift_times()

        # 4. Atomares Update der aktiven Caches
        print(f"[DM] Atomares Update: Überschreibe aktive Caches mit Daten für {year}-{month}")
        self.year = year
        self.month = month
        self.user_data_map = temp_data['user_data_map']
        self._initialize_user_shift_totals(self.user_data_map)
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

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde)...")
        self.update_violation_set(year, month)

        update_progress(90, "Berechne Monats-Totals...")
        self.user_shift_totals = self._calculate_user_shift_totals(
            self.shift_schedule_data,
            self.user_data_map,
            self.app.shift_types_data
        )

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
            'user_data_map': self.user_data_map,
            'user_shift_totals': self.user_shift_totals
        }

        return True  # Erfolg

    # --- MODIFIZIERTE FUNKTION (Regel 2: Latenz-Fix) ---
    def recalculate_daily_counts_for_day(self, date_obj, old_shift, new_shift):
        """
        Aktualisiert self.daily_counts für einen bestimmten Tag nach Schichtänderung.
        Die langsame P5-Cache-Invalidierung wird in einen Hintergrund-Thread ausgelagert.
        """

        cache_key = (date_obj.year, date_obj.month)

        # --- INNOVATION (Regel 2): Latenz-Fix ---
        # Diese Operation (del) blockiert den Hauptthread und verzögert
        # das Anzeigen von 'T.' in der UI.
        if cache_key in self.monthly_caches:

            print(f"[DM Cache] Plane asynchrones Entfernen von {cache_key} aus P5-Cache...")

            def _invalidate_cache_async(key_to_delete):
                """Führt das Löschen im Hintergrund aus."""
                try:
                    # (Regel 1) Wir müssen sicherstellen, dass wir den 
                    # dict-Zugriff sperren, falls mehrere Threads gleichzeitig 
                    # darauf zugreifen.
                    # HINWEIS: Ein 'threading.Lock' wäre idealer,
                    # aber für diesen Zweck ist die Operation atomar genug,
                    # um ein 'KeyError' abzufangen, falls ein anderer Thread
                    # schneller war.
                    del self.monthly_caches[key_to_delete]
                    print(f"[DM Cache] Asynchrones Entfernen von {key_to_delete} erfolgreich.")
                except KeyError:
                    # Key wurde bereits von einem anderen Thread entfernt
                    print(f"[DM Cache] Asynchrones Entfernen: {key_to_delete} war bereits entfernt.")
                except Exception as e:
                    print(f"[FEHLER] Asynchrones Entfernen von {key_to_delete} fehlgeschlagen: {e}")

            # Starte das Löschen in einem separaten, nicht blockierenden Thread
            threading.Thread(target=_invalidate_cache_async, args=(cache_key,), daemon=True).start()

        # --- Alter (blockierender) Code ---
        # if cache_key in self.monthly_caches:
        #     print(f"[DM Cache] Entferne {cache_key} wegen Zählungs-Update aus P5-Cache.")
        #     del self.monthly_caches[cache_key]
        # --- ENDE ---

        # (Der Rest der Funktion ist schnell und bleibt synchron im Hauptthread)
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
                if old_shift in counts_today:
                    del counts_today[old_shift]

        if should_count_shift(new_shift):
            counts_today[new_shift] = counts_today.get(new_shift, 0) + 1

        if not counts_today and date_str in self.daily_counts:
            del self.daily_counts[date_str]

        print(f"[DM Counts] Neue Zählung für {date_str}: {self.daily_counts.get(date_str, {})}")

    # --- (Unverändert) ---
    def get_conflicts_for_shift(self, user_id, date_obj, target_shift_abbrev):
        """
        Delegiert die sofortige Konfliktprüfung an den PlanningAssistant.
        Nutzt nur Cache-Daten (Regel 2).
        """
        return self.planning_assistant.get_conflicts_for_shift(user_id, date_obj, target_shift_abbrev)