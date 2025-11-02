# gui/shift_plan_data_manager.py
from datetime import date, datetime, timedelta, time  # Importiere 'time'
import calendar
from collections import defaultdict
import traceback  # Import für detailliertere Fehlermeldungen

# DB Imports
# --- INNOVATION: Nur noch 1 DB-Funktion für das Laden benötigt (BLEIBT ERHALTEN) ---
from database.db_shifts import get_all_data_for_plan_display
# --- ANPASSUNG: Veraltete Importe entfernt ---
# (Wie in Ihrer Originaldatei)

from database.db_core import load_config_json, save_config_json
from gui.event_manager import EventManager
from gui.shift_lock_manager import ShiftLockManager


class ShiftPlanDataManager:
    """
    Verantwortlich für das Laden, Vorverarbeiten und Berechnen aller Daten,
    die für die Anzeige des Dienstplans benötigt werden (Staffing, Stunden, Konflikte).
    NUTZT INNOVATIVE BATCH-ABFRAGEN (Regel 2) UND MEHRSTUFIGES CACHING (P5).
    """

    GENERATOR_CONFIG_KEY = "GENERATOR_SETTINGS_V1"

    def __init__(self, app):
        self.app = app

        # --- NEU (Für P5: Multi-Monats-Cache) ---
        # Dieser Cache speichert die kompletten Daten-Snapshots für bereits geladene Monate.
        # Schlüssel: (year, month), Wert: dict mit allen relevanten Daten
        self.monthly_caches = {}
        # --- ENDE NEU ---

        # Speichert, welcher Monat aktuell *aktiv* ist (angezeigt wird)
        self.year = 0
        self.month = 0

        # Caches für die *aktiven* Daten (des Monats self.year/self.month)
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}
        self.violation_cells = set()

        # Cache für Vormonats-Shifts
        self._prev_month_shifts = {}
        self.previous_month_shifts = {}  # Veraltet, wird aber von get_previous_month_shifts genutzt

        # Caches für Vormonats-Anträge
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}

        # Cache für Folgemonats-Shifts
        self.next_month_shifts = {}

        # Cache für vorverarbeitete Schichtzeiten
        self._preprocessed_shift_times = {}

        # Cache für Benutzer
        self.cached_users_for_month = []

        # Set zur Nachverfolgung von Warnungen
        self._warned_missing_times = set()

        # ShiftLockManager Instanz
        self.shift_lock_manager = ShiftLockManager(app)

    # --- NEU: Umbenannt von _clear_caches (Regel 4) ---
    def _clear_active_caches(self):
        """
        Setzt alle *aktiven* Caches zurück. Notwendig beim Laden eines neuen Monats,
        der noch nicht im globalen Cache (self.monthly_caches) ist.
        """
        print("[DM] Aktive Caches werden zurückgesetzt...")
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}
        self.violation_cells.clear()
        self._prev_month_shifts = {}
        self.previous_month_shifts = {}
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}
        self.next_month_shifts = {}
        self.cached_users_for_month = []
        self._warned_missing_times.clear()  # Warnungen auch zurücksetzen

        # WICHTIG: Setzt die Locks im Manager zurück (basierend auf Ihrer Logik)
        self.shift_lock_manager.locked_shifts = {}

    # --- NEU: Globale Cache-Löschfunktion (P5) ---
    def clear_all_monthly_caches(self):
        """
        Löscht den gesamten Multi-Monats-Cache (P5).
        Nötig z.B. bei globalen Änderungen (User-Update, Schichtart-Update).
        """
        print("[DM Cache] Lösche gesamten Monats-Cache (P5)...")
        self.monthly_caches = {}
        self._clear_active_caches()

    # --- ENDE NEU ---

    def get_previous_month_shifts(self):
        """Gibt die geladenen Schichtdaten des Vormonats für den Generator zurück."""
        return self._prev_month_shifts

    def get_next_month_shifts(self):
        """
        Gibt die Schichtdaten des Folgemonats aus dem Cache zurück.
        """
        return self.next_month_shifts

    # --- Generator Config Methoden (unverändert) ---
    def get_generator_config(self):
        default = {
            'max_consecutive_same_shift': 4,
            'enable_24h_planning': False,
            'preferred_partners_prioritized': []
        }
        loaded = load_config_json(self.GENERATOR_CONFIG_KEY)
        if loaded and 'preferred_partners' in loaded and 'preferred_partners_prioritized' not in loaded:
            print("[WARNUNG] Alte Partnerstruktur gefunden, migriere zu priorisierter Struktur mit Prio 1...")
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

    def _get_shift_helper(self, user_id_str, date_obj, current_year, current_month):
        """ Holt die *Arbeits*-Schicht für einen User an einem Datum, berücksichtigt Vormonat-Cache. """
        # HINWEIS: Greift weiterhin auf die *aktiven* Caches zu (self.shift_schedule_data etc.)
        # Diese werden durch load_and_process_data korrekt gesetzt.
        date_str = date_obj.strftime('%Y-%m-%d')

        shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = self._prev_month_shifts.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = self.next_month_shifts.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = ""

        return shift if shift not in ["", "FREI", None, "U", "X", "EU", "WF", "U?"] else ""

    # --- INNOVATION: load_and_process_data nutzt jetzt die NEUE BATCH-FUNKTION UND CACHING (P5) ---
    def load_and_process_data(self, year, month, progress_callback=None, force_reload=False):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch ODER lädt aus dem P5-Cache.
        Ruft danach die volle Konfliktprüfung auf.

        Args:
            year (int): Jahr
            month (int): Monat
            progress_callback (function, optional): Callback für Fortschrittsanzeige.
            force_reload (bool, optional): Erzwingt das Neuladen von der DB, ignoriert den Cache.
        """

        # --- NEU (P5) ---
        # Setzt den Status, welcher Monat geladen wird/ist
        self.year = year
        self.month = month

        cache_key = (year, month)

        def update_progress(value, text):
            if progress_callback: progress_callback(value, text)

        # 1. PRÜFE GLOBALEN CACHE (P5)
        if cache_key in self.monthly_caches and not force_reload:
            print(f"[DM Cache] Lade Monat {year}-{month} aus dem P5-Cache.")
            update_progress(50, "Lade Daten aus Cache...")

            # Daten aus Cache in aktive Variablen kopieren
            cached_data = self.monthly_caches[cache_key]
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
            self.shift_lock_manager.locked_shifts = cached_data['locked_shifts']

            # Wichtig: Schichtzeiten (sollten global sein, aber zur Sicherheit)
            # (Dieser Aufruf ist schnell, da er nur den globalen app-State prüft)
            self._preprocess_shift_times()

            update_progress(95, "Vorbereitung abgeschlossen.")

            return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

        # 2. NICHT IM CACHE (ODER force_reload=True): Von DB laden

        # Caches leeren, um Daten vom Vormonat (falls vorhanden) zu entfernen
        # Nutzt die umbenannte Funktion (Regel 1)
        self._clear_active_caches()
        # --- ENDE NEU ---

        update_progress(10, "Lade alle Plandaten (Batch-Optimierung)...")

        first_day_current_month = date(year, month, 1)
        current_date_for_archive_check = datetime.combine(first_day_current_month, time(0, 0, 0))

        # 2a. EIN EINZIGER DB-AUFRUF (Ihre innovative Funktion)
        batch_data = get_all_data_for_plan_display(year, month, current_date_for_archive_check)

        if batch_data is None:
            print("[FEHLER] get_all_data_for_plan_display gab None zurück.")
            # Caches bleiben leer (wurden durch _clear_active_caches() geleert)
            raise Exception("Fehler beim Abrufen der Batch-Daten aus der Datenbank.")

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")

        # 2b. Daten in die *aktiven* Caches des DataManagers entpacken

        # Benutzer
        self.cached_users_for_month = batch_data.get('users', [])
        print(f"[DM Load] {len(self.cached_users_for_month)} Benutzer aus Batch geladen.")

        # Schichtsicherungen (Locks)
        self.shift_lock_manager.locked_shifts = batch_data.get('locks', {})
        print(f"[DM Load] {len(self.shift_lock_manager.locked_shifts)} Schichtsicherungen aus Batch geladen.")

        # Hauptmonat
        self.shift_schedule_data = batch_data.get('shifts', {})
        self.wunschfrei_data = batch_data.get('wunschfrei_requests', {})
        raw_vacations = batch_data.get('vacation_requests', [])
        self.processed_vacations = self._process_vacations(year, month, raw_vacations)
        self.daily_counts = batch_data.get('daily_counts', {})  # Zählungen kommen jetzt direkt

        # Vormonat
        self._prev_month_shifts = batch_data.get('prev_month_shifts', {})
        self.previous_month_shifts = self._prev_month_shifts  # (für Abwärtskompatibilität)
        self.wunschfrei_data_prev = batch_data.get('prev_month_wunschfrei', {})
        raw_vacations_prev = batch_data.get('prev_month_vacations', [])
        prev_month_date = first_day_current_month - timedelta(days=1)
        self.processed_vacations_prev = self._process_vacations(prev_month_date.year, prev_month_date.month,
                                                                raw_vacations_prev)

        # Folgemonat
        self.next_month_shifts = batch_data.get('next_month_shifts', {})

        print(f"[DM Load] Batch-Entpacken abgeschlossen.")
        # --- ENDE INNOVATION ---

        # 3. Restliche Verarbeitung (bleibt gleich)

        # Lade globale Events
        try:
            # Stellt sicher, dass self.app (MainAdmin/UserWindow) 'app' (Bootloader) hat
            if hasattr(self.app, 'app'):
                self.app.app.global_events_data = EventManager.get_events_for_year(year)
            else:
                # Fallback, falls 'app' der Bootloader selbst ist (während Pre-Loading)
                self.app.global_events_data = EventManager.get_events_for_year(year)
            print(f"[DM Load] Globale Events für {year} aus Datenbank geladen.")
        except Exception as e:
            print(f"[FEHLER] Fehler beim Laden der globalen Events aus DB: {e}")
            if hasattr(self.app, 'app'):
                self.app.app.global_events_data = {}
            else:
                self.app.global_events_data = {}

        # Tageszählungen (müssen nicht mehr berechnet werden, kommen aus DB)
        print("[DM Load] Tageszählungen (daily_counts) direkt aus Batch übernommen.")

        # Schichtzeiten vorverarbeiten
        self._preprocess_shift_times()

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde)...")
        # Volle Konfliktprüfung
        self.update_violation_set(year, month)

        update_progress(95, "Vorbereitung abgeschlossen.")

        # --- NEU (P5): Speichere die geladenen Daten im globalen Cache ---
        print(f"[DM Cache] Speichere Monat {year}-{month} im P5-Cache.")
        self.monthly_caches[cache_key] = {
            'shift_schedule_data': self.shift_schedule_data,
            'processed_vacations': self.processed_vacations,
            'wunschfrei_data': self.wunschfrei_data,
            'daily_counts': self.daily_counts,
            'violation_cells': self.violation_cells.copy(),  # Wichtig: Set kopieren
            '_prev_month_shifts': self._prev_month_shifts,
            'previous_month_shifts': self.previous_month_shifts,
            'processed_vacations_prev': self.processed_vacations_prev,
            'wunschfrei_data_prev': self.wunschfrei_data_prev,
            'next_month_shifts': self.next_month_shifts,
            'cached_users_for_month': self.cached_users_for_month,
            'locked_shifts': self.shift_lock_manager.locked_shifts,
        }
        # --- ENDE NEU ---

        return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

    # --- ENDE METHODE ---

    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Aktualisiert das violation_cells Set gezielt nach einer Schichtänderung und gibt betroffene Zellen zurück."""

        # --- NEU (P5): Inkrementelle Updates müssen den P5-Cache invalidieren ---
        cache_key = (date_obj.year, date_obj.month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Entferne {cache_key} wegen inkrementellem Update aus P5-Cache.")
            del self.monthly_caches[cache_key]
        # --- ENDE NEU ---

        print(f"[DM-Incr] Update für User {user_id} am {date_obj}: '{old_shift}' -> '{new_shift}'")
        affected_cells = set()
        day = date_obj.day;
        year = date_obj.year;
        month = date_obj.month
        user_id_str = str(user_id)

        # Hilfsfunktionen zum Hinzufügen/Entfernen von Violations
        def add_violation(uid, d):
            cell = (uid, d)
            if cell not in self.violation_cells:
                print(f"    -> ADD V: U{uid}, D{d}")
                self.violation_cells.add(cell)
                affected_cells.add(cell)

        def remove_violation(uid, d):
            cell = (uid, d)
            if cell in self.violation_cells:
                print(f"    -> REMOVE V: U{uid}, D{d}")
                self.violation_cells.discard(cell)
                affected_cells.add(cell)

        # 1. Ruhezeitkonflikte (N -> T/6) prüfen und aktualisieren
        print("  Prüfe Ruhezeit...")
        prev_day_obj = date_obj - timedelta(days=1);
        next_day_obj = date_obj + timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_day_obj, year, month)

        next_shift = self._get_shift_helper(user_id_str, next_day_obj, year, month)

        is_next_shift_work = bool(next_shift)
        is_old_shift_conflict = old_shift not in ["", "N.", "U", "X", "EU", "WF", "U?"]
        is_new_shift_conflict = new_shift not in ["", "N.", "U", "X", "EU", "WF", "U?"]

        # a) Alte Konflikte entfernen
        if old_shift == 'N.':
            remove_violation(user_id, day)
            if next_day_obj.month == month and next_day_obj.year == year: remove_violation(user_id, day + 1)
        if prev_shift == 'N.' and is_old_shift_conflict:
            if prev_day_obj.month == month and prev_day_obj.year == year: remove_violation(user_id, day - 1)
            remove_violation(user_id, day)

        # b) Neue Konflikte hinzufügen
        if new_shift == 'N.' and is_next_shift_work:
            add_violation(user_id, day)
            if next_day_obj.month == month and next_day_obj.year == year: add_violation(user_id, day + 1)
        if prev_shift == 'N.' and is_new_shift_conflict:
            if prev_day_obj.month == month and prev_day_obj.year == year: add_violation(user_id, day - 1)
            add_violation(user_id, day)

        # 2. Hundekonflikte prüfen und aktualisieren
        print("  Prüfe Hundekonflikt...")
        user_data = next((u for u in self.cached_users_for_month if u.get('id') == user_id), None)
        dog = user_data.get('diensthund') if user_data and user_data.get('diensthund') != '---' else None
        old_dog = user_data.get('diensthund') if user_data else None
        if old_dog == '---': old_dog = None

        involved_dogs = set()
        if dog: involved_dogs.add(dog)
        if old_dog and old_dog != dog: involved_dogs.add(old_dog)
        if old_shift and not new_shift and old_dog: involved_dogs.add(old_dog)
        if not involved_dogs and old_shift:
            for other_user in self.cached_users_for_month:
                other_dog = other_user.get('diensthund')
                if other_dog and other_dog != '---':
                    other_id = other_user.get('id')
                    if other_id is None: continue
                    other_shift_exists = self._get_shift_helper(str(other_id), date_obj, year, month)
                    if other_shift_exists or (other_id == user_id and dog == other_dog):
                        involved_dogs.add(other_dog)

        print(f"    -> Hunde zu prüfen für Tag {day}: {involved_dogs}")

        for current_dog in involved_dogs:
            assignments_today = []
            for other_user in self.cached_users_for_month:
                if other_user.get('diensthund') == current_dog:
                    other_user_id = other_user.get('id')
                    if other_user_id is None: continue
                    current_shift_for_other = new_shift if other_user_id == user_id else self._get_shift_helper(
                        str(other_user_id), date_obj, year, month)
                    if current_shift_for_other:
                        assignments_today.append({'id': other_user_id, 'shift': current_shift_for_other})

            involved_user_ids_now = {a['id'] for a in assignments_today}
            involved_user_ids_before = set(involved_user_ids_now)
            if old_shift and user_id not in involved_user_ids_now and old_dog == current_dog:
                involved_user_ids_before.add(user_id)
            all_potentially_involved = involved_user_ids_now.union(involved_user_ids_before)
            assignments_to_check = assignments_today

            print(
                f"    Hund '{current_dog}' T{day}. Beteiligte (Vorher/Nachher): {all_potentially_involved}. Aktuelle Assignments: {assignments_today}")

            print(f"    -> Entferne alte Konflikte für Hund '{current_dog}' T{day}...")
            for uid_involved in all_potentially_involved:
                remove_violation(uid_involved, day)

            print(f"    -> Prüfe neue Konflikte für Hund '{current_dog}' T{day}...")
            if len(assignments_to_check) > 1:
                for i in range(len(assignments_to_check)):
                    for j in range(i + 1, len(assignments_to_check)):
                        u1 = assignments_to_check[i];
                        u2 = assignments_to_check[j]
                        if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                            print(f"      -> Konflikt: {u1['id']}({u1['shift']}) vs {u2['id']}({u2['shift']})")
                            add_violation(u1['id'], day);
                            add_violation(u2['id'], day)

        print(f"[DM-Incr] Update abgeschlossen. Betroffene Zellen: {affected_cells}")
        return affected_cells

    def recalculate_daily_counts_for_day(self, date_obj, old_shift, new_shift):
        """Aktualisiert self.daily_counts für einen bestimmten Tag nach Schichtänderung."""

        # --- NEU (P5): Inkrementelle Updates müssen den P5-Cache invalidieren ---
        cache_key = (date_obj.year, date_obj.month)
        if cache_key in self.monthly_caches:
            print(f"[DM Cache] Entferne {cache_key} wegen Zählungs-Update aus P5-Cache.")
            # Wir löschen den Cache, da diese Funktion von außerhalb aufgerufen werden könnte
            # (z.B. durch shift_plan_actions) und die Daten inkonsistent werden.
            del self.monthly_caches[cache_key]
        # --- ENDE NEU ---

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

    def _get_app_shift_types(self):
        """Hilfsfunktion, um shift_types_data sicher vom Bootloader (app.app) oder der App (app) zu holen."""
        if hasattr(self.app, 'shift_types_data'):
            return self.app.shift_types_data
        if hasattr(self.app, 'app') and hasattr(self.app.app, 'shift_types_data'):
            return self.app.app.shift_types_data
        print("[WARNUNG] shift_types_data weder in app noch in app.app gefunden.")
        return {}

    def _preprocess_shift_times(self):
        """ Konvertiert Schichtzeiten in Minuten-Intervalle für schnelle Überlappungsprüfung. """

        # Diese Funktion muss nur einmal laufen, solange die Schicht-Typen geladen sind.
        # Wir prüfen, ob sie schon geladen sind, um unnötige Arbeit zu vermeiden.
        if self._preprocessed_shift_times:
            return

        self._preprocessed_shift_times.clear()
        self._warned_missing_times.clear()

        shift_types_data = self._get_app_shift_types()  # Nutzt die neue Hilfsfunktion

        if not shift_types_data:
            print("[WARNUNG] shift_types_data ist leer in _preprocess_shift_times.")
            return

        print("[DM] Verarbeite Schichtzeiten vor...")
        count = 0
        for abbrev, data in shift_types_data.items():
            start_time_str = data.get('start_time');
            end_time_str = data.get('end_time')
            if not start_time_str or not end_time_str: continue
            try:
                s_time = datetime.strptime(start_time_str, '%H:%M').time()
                e_time = datetime.strptime(end_time_str, '%H:%M').time()
                s_min = s_time.hour * 60 + s_time.minute
                e_min = e_time.hour * 60 + e_time.minute
                if e_min <= s_min: e_min += 24 * 60
                self._preprocessed_shift_times[abbrev] = (s_min, e_min);
                count += 1
            except ValueError:
                print(f"[WARNUNG] Ungültiges Zeitformat für Schicht '{abbrev}' in shift_types_data.")
        print(f"[DM] {count} Schichtzeiten erfolgreich vorverarbeitet.")

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
                    # Prüfe nur Daten im relevanten Monat (Performance)
                    if month_start <= current_date <= month_end:
                        processed[user_id_str][current_date] = status;
                    if current_date > month_end:
                        break  # OPTIMIERUNG: Brich ab, wenn das Ende des Monats überschritten ist
                    current_date += timedelta(days=1)
            except (ValueError, TypeError, KeyError) as e:
                print(f"[WARNUNG] Fehler beim Verarbeiten von Urlaub ID {req.get('id', 'N/A')}: {e}")

        return dict(processed)  # Konvertiere defaultdict zu dict für saubere Übergabe

    def get_min_staffing_for_date(self, current_date):
        """ Ermittelt die Mindestbesetzungsregeln für ein spezifisches Datum. """
        # Sicherer Zugriff auf die Regeln im Bootloader (app.app)
        rules_source = self.app
        if hasattr(self.app, 'app'):  # Wenn 'app' das MainAdminWindow ist
            rules_source = self.app.app

        rules = getattr(rules_source, 'staffing_rules', {});
        min_staffing = {}
        min_staffing.update(rules.get('Daily', {}))
        weekday = current_date.weekday()
        if weekday >= 5:  # Sa/So
            min_staffing.update(rules.get('Sa-So', {}))
        elif weekday == 4:  # Fr
            min_staffing.update(rules.get('Fr', {}))
        else:  # Mo-Do
            min_staffing.update(rules.get('Mo-Do', {}))

        # Feiertags-Check (nutzt die Funktion im Bootloader)
        if hasattr(rules_source, 'is_holiday') and rules_source.is_holiday(current_date):
            min_staffing.update(rules.get('Holiday', {}))

        return {k: int(v) for k, v in min_staffing.items() if
                isinstance(v, (int, str)) and str(v).isdigit() and int(v) >= 0}

    def calculate_total_hours_for_user(self, user_id_str, year, month):
        """ Berechnet die geschätzten Gesamtstunden für einen Benutzer im Monat. """
        # HINWEIS: Diese Funktion ist jetzt SEHR schnell, wenn der Monat im Cache ist,
        # da self.shift_schedule_data etc. bereits die korrekten (aktiven) Daten halten.
        total_hours = 0.0;
        try:
            user_id_int = int(user_id_str)
        except ValueError:
            print(f"[WARNUNG] Ungültige user_id_str in calculate_total_hours: {user_id_str}");
            return 0.0

        days_in_month = calendar.monthrange(year, month)[1]
        shift_types_data = self._get_app_shift_types()  # Nutzt Hilfsfunktion

        # Überstunden vom Vormonat (N.)
        prev_month_last_day = date(year, month, 1) - timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_month_last_day, year, month)
        if prev_shift == 'N.':
            shift_info_n = shift_types_data.get('N.')
            hours_overlap = 6.0  # Standard-Übertrag
            if shift_info_n and shift_info_n.get('end_time'):
                try:
                    end_time_n = datetime.strptime(shift_info_n['end_time'], '%H:%M').time();
                    hours_overlap = end_time_n.hour + end_time_n.minute / 60.0
                except ValueError:
                    pass
            total_hours += hours_overlap

        # Stunden des aktuellen Monats
        user_shifts_this_month = self.shift_schedule_data.get(user_id_str, {})
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')
            shift = user_shifts_this_month.get(date_str, "");
            vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date)
            request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)

            actual_shift_for_hours = shift
            if vacation_status == 'Genehmigt':
                actual_shift_for_hours = 'U'
            # (Ihre Logik prüft hier nur WF, nicht andere genehmigte Wünsche)
            elif request_info and request_info[1] == 'WF' and request_info[0] in ["Genehmigt", "Akzeptiert"]:
                actual_shift_for_hours = 'X'

            if actual_shift_for_hours in shift_types_data:
                hours = float(shift_types_data[actual_shift_for_hours].get('hours', 0.0))

                # Abzug der Überstunden am Monatsende
                if actual_shift_for_hours == 'N.' and day == days_in_month:
                    shift_info_n = shift_types_data.get('N.')
                    hours_to_deduct = 6.0  # Standard-Abzug
                    if shift_info_n and shift_info_n.get('end_time'):
                        try:
                            end_time_n = datetime.strptime(shift_info_n['end_time'], '%H:%M').time();
                            hours_to_deduct = end_time_n.hour + end_time_n.minute / 60.0
                        except ValueError:
                            pass
                    hours -= hours_to_deduct  # Ziehe den Übertrag ins nächste Monat ab

                total_hours += hours

        return round(total_hours, 2)

    def update_violation_set(self, year, month):
        """ Prüft den *gesamten* Monat auf Konflikte (Ruhezeit, Hunde) und füllt self.violation_cells. """
        # HINWEIS: Diese Funktion wird nur aufgerufen, wenn Daten neu von der DB geladen werden.
        # Gecachte Monate haben bereits ein fertiges self.violation_cells Set.
        print(f"[DM-Full] Starte volle Konfliktprüfung für {year}-{month:02d}...")
        self.violation_cells.clear();
        days_in_month = calendar.monthrange(year, month)[1]
        current_user_order = self.cached_users_for_month
        if not current_user_order:
            print("[WARNUNG] Benutzer-Cache leer in update_violation_set!");
            return

        # 1. Ruhezeitkonflikte (N -> T/6 und NEUE REGEL: N -> QA/S)
        for user in current_user_order:
            user_id = user.get('id');
            if user_id is None: continue;
            user_id_str = str(user_id)

            # Wir müssen vom letzten Tag des Vormonats starten
            current_check_date = date(year, month, 1) - timedelta(days=1);
            # Und bis zum Ende des Monats prüfen
            end_check_date = date(year, month, days_in_month)

            while current_check_date <= end_check_date:
                next_day_date = current_check_date + timedelta(days=1)

                # (Spezialfall für Monatsende: next_day_date könnte im Folgemonat sein)
                shift1 = self._get_shift_helper(user_id_str, current_check_date, year, month);
                shift2 = self._get_shift_helper(user_id_str, next_day_date, year, month)

                # (Ihre Logik: N. -> T., 6, QA, S)
                is_ruhezeit_violation = (shift1 == 'N.' and shift2 in ["T.", "6", "QA", "S"])

                if is_ruhezeit_violation:
                    # Markiere beide Tage, wenn sie im aktuellen Monat liegen
                    if current_check_date.month == month and current_check_date.year == year:
                        self.violation_cells.add((user_id, current_check_date.day))
                    if next_day_date.month == month and next_day_date.year == year:
                        self.violation_cells.add((user_id, next_day_date.day))

                current_check_date += timedelta(days=1)

        # 2. Hundekonflikte (zeitliche Überlappung am selben Tag)
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            dog_schedule_today = defaultdict(list)
            for user in current_user_order:
                dog = user.get('diensthund')
                if dog and dog != '---':
                    user_id = user.get('id');
                    if user_id is None: continue;
                    user_id_str = str(user_id)
                    shift = self._get_shift_helper(user_id_str, current_date, year, month)
                    if shift:
                        dog_schedule_today[dog].append({'id': user_id, 'shift': shift})

            # Prüfe jeden Hund einzeln
            for dog, assignments in dog_schedule_today.items():
                if len(assignments) > 1:
                    # Mehr als ein Mitarbeiter mit DIESEM Hund arbeitet heute
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            u1 = assignments[i];
                            u2 = assignments[j]
                            if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                                # Ihre Schichten überlappen sich!
                                self.violation_cells.add((u1['id'], day));
                                self.violation_cells.add((u2['id'], day))

        print(f"[DM-Full] Volle Konfliktprüfung abgeschlossen. Konflikte: {len(self.violation_cells)}")

    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlppung mit vorverarbeiteten Zeiten (Cache). """
        if shift1_abbrev in ['U', 'X', 'EU', 'WF', '', 'FREI'] or shift2_abbrev in ['U', 'X', 'EU', 'WF', '',
                                                                                    'FREI']: return False

        s1, e1 = self._preprocessed_shift_times.get(shift1_abbrev, (None, None))
        s2, e2 = self._preprocessed_shift_times.get(shift2_abbrev, (None, None))

        if s1 is None or s2 is None:
            if s1 is None and shift1_abbrev not in self._warned_missing_times:
                print(f"[WARNUNG] Zeit für Schicht '{shift1_abbrev}' fehlt im Cache (_check_time_overlap).")
                self._warned_missing_times.add(shift1_abbrev)
            if s2 is None and shift2_abbrev not in self._warned_missing_times:
                print(f"[WARNUNG] Zeit für Schicht '{shift2_abbrev}' fehlt im Cache (_check_time_overlap).")
                self._warned_missing_times.add(shift2_abbrev)
            return False

        # Standard-Überlappungsprüfung
        return (s1 < e2) and (s2 < e1)