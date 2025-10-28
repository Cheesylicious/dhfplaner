# gui/shift_plan_data_manager.py
from datetime import date, datetime, timedelta, time  # Importiere 'time'
import calendar
from collections import defaultdict
import traceback  # Import für detailliertere Fehlermeldungen

# DB Imports
from database.db_shifts import get_consolidated_month_data
from database.db_users import get_user_by_id, get_ordered_users_for_schedule
# NEU: Import der Konfigurationsfunktionen für die Persistenz
from database.db_core import load_config_json, save_config_json
# NEU: Import für die Event-Verwaltung (um den Dateizugriff zu ersetzen)
from gui.event_manager import EventManager
# NEU: Import des ShiftLockManagers (Wird in den neuen Dateien db_locks.py und gui/shift_lock_manager.py benötigt)
from gui.shift_lock_manager import ShiftLockManager


class ShiftPlanDataManager:
    """
    Verantwortlich für das Laden, Vorverarbeiten und Berechnen aller Daten,
    die für die Anzeige des Dienstplans benötigt werden (Staffing, Stunden, Konflikte).
    """

    # NEU: Eindeutiger Schlüssel für die DB-Speicherung der Generator-Einstellungen
    GENERATOR_CONFIG_KEY = "GENERATOR_SETTINGS_V1"

    def __init__(self, app):
        # super().__init__() # Super-Aufruf hier entfernt, da ShiftPlanDataManager nicht von tk.Frame erbt
        self.app = app
        # Caches für die Hauptdaten
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}
        self.violation_cells = set()  # Menge von Tupeln: (user_id, day_of_month)

        # Cache für Vormonats-Shifts
        self._prev_month_shifts = {}
        self.previous_month_shifts = {}

        # Cache für Folgemonats-Shifts (für den Generator)
        self._next_month_shifts_cache = None

        # Cache für vorverarbeitete Schichtzeiten
        self._preprocessed_shift_times = {}

        # Cache für Benutzer (wird in load_and_process_data gefüllt)
        self.cached_users_for_month = []

        # Set zur Nachverfolgung von Warnungen über fehlende Schichtzeiten
        self._warned_missing_times = set()

        # NEU: ShiftLockManager Instanz wird initialisiert
        self.shift_lock_manager = ShiftLockManager(app)

    # --- METHODE ZUR BEHEBUNG DES ATTRIBUTEERROR (get_previous_month_shifts) ---
    def get_previous_month_shifts(self):
        """Gibt die geladenen Schichtdaten des Vormonats für den Generator zurück."""
        if hasattr(self, 'previous_month_shifts'):
            return self.previous_month_shifts
        return {}

    # --- ENDE get_previous_month_shifts ---

    # --- METHODE ZUR BEHEBUNG DES AKTUELLEN ATTRIBUTEERROR (get_next_month_shifts) ---
    def get_next_month_shifts(self):
        """
        Gibt die Schichtdaten des Folgemonats aus dem Cache zurück.
        """
        if self._next_month_shifts_cache is None:
            # Hier müsste eigentlich die Logik zum Laden der Folgemonatsdaten stehen,
            # aber für die Generator-Helfer geben wir den Cache (leer) zurück.
            return {}

        return self._next_month_shifts_cache

    # --- ENDE get_next_month_shifts ---

    # --- NEUE METHODEN ZUR SPEICHERUNG DER GENERATOR-EINSTELLUNGEN ---

    def get_generator_config(self):
        """Lädt die Einstellungen des Schichtplan-Generators aus der Datenbank."""
        # Standardwerte mit neuem Schlüssel für priorisierte Partner
        default = {
            'max_consecutive_same_shift': 4,
            'enable_24h_planning': False,
            'preferred_partners_prioritized': []  # Verwendet den neuen Schlüssel
        }
        loaded = load_config_json(self.GENERATOR_CONFIG_KEY)

        # Migration von alter Struktur (ohne Priorität) zu neuer Struktur
        if loaded and 'preferred_partners' in loaded and 'preferred_partners_prioritized' not in loaded:
            print("[WARNUNG] Alte Partnerstruktur gefunden, migriere zu priorisierter Struktur mit Prio 1...")
            migrated_partners = []
            for pair in loaded.get('preferred_partners', []):
                if isinstance(pair, dict) and 'id_a' in pair and 'id_b' in pair:
                    try:
                        # Fügt jedem alten Paar die Standard-Priorität 1 hinzu
                        migrated_partners.append({
                            'id_a': int(pair['id_a']),
                            'id_b': int(pair['id_b']),
                            'priority': 1
                        })
                    except (ValueError, TypeError):
                        pass  # Ignoriere fehlerhafte alte Einträge
            loaded['preferred_partners_prioritized'] = migrated_partners

        # Standardwerte für neue Scores/Multiplikatoren hinzufügen
        default.update({
            'mandatory_rest_days_after_max_shifts': 2,
            'avoid_understaffing_hard': True,
            'ensure_one_weekend_off': False,
            'wunschfrei_respect_level': 75,
            'fairness_threshold_hours': 10.0,
            'min_hours_fairness_threshold': 20.0,
            'min_hours_score_multiplier': 5.0,
            'fairness_score_multiplier': 1.0,
            'isolation_score_multiplier': 30.0  # Standardwert muss hier übernommen werden
        })

        # Füllt die geladenen Daten mit den fehlenden Standardwerten
        final_config = default.copy()
        if loaded:
            final_config.update(loaded)

        return final_config  # Gibt geladene oder Standard-Config zurück

    def save_generator_config(self, config_data):
        """Speichert die Einstellungen des Schichtplan-Generators in die Datenbank."""
        # save_config_json gibt (True/False, message) zurück
        return save_config_json(self.GENERATOR_CONFIG_KEY, config_data)

    # --- ENDE NEUE METHODEN ---

    def _get_shift_helper(self, user_id_str, date_obj, current_year, current_month):
        """ Holt die *Arbeits*-Schicht für einen User an einem Datum, berücksichtigt Vormonat-Cache. """
        date_str = date_obj.strftime('%Y-%m-%d')
        shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str)

        is_previous_month = (date_obj.year < current_year or
                             (date_obj.year == current_year and date_obj.month < current_month))

        if shift is None and is_previous_month:
            # Vormonat-Cache nutzen
            # --- KORREKTUR: Zugriff auf _prev_month_shifts statt previous_month_shifts ---
            shift = self._prev_month_shifts.get(user_id_str, {}).get(date_str, "")
            # --- ENDE KORREKTUR ---
        elif shift is None:
            # Kein Eintrag für das Datum gefunden (weder aktuell noch Vormonat)
            shift = ""

        # Gebe leeren String zurück für Nicht-Arbeitstage (explizite Prüfung statt free_shifts_indicators)
        return shift if shift not in ["", "FREI", None, "U", "X", "EU", "WF", "U?"] else ""

    def load_and_process_data(self, year, month, progress_callback=None):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch. Ruft danach die volle Konfliktprüfung auf.
        """

        def update_progress(value, text):
            if progress_callback: progress_callback(value, text)

        update_progress(5, "Lade Benutzerreihenfolge...")

        first_day_current_month = date(year, month, 1)
        current_date_for_archive_check = datetime.combine(first_day_current_month, time(0, 0, 0))

        # Benutzer für den Planungszeitraum laden
        self.cached_users_for_month = get_ordered_users_for_schedule(include_hidden=True,
                                                                     for_date=current_date_for_archive_check)
        print(
            f"[DM Load] {len(self.cached_users_for_month)} Benutzer für {year}-{month} geladen (Stichtag: {current_date_for_archive_check}).")

        # --- KORREKTUR: Locks *hier* laden (war schon in der vorherigen Version drin, bleibt) ---
        update_progress(10, "Lade Schichtsicherungen...")
        try:
            # Rufe load_locks im ShiftLockManager auf, um den Cache zu aktualisieren
            self.shift_lock_manager.load_locks(year, month)
            print("[DM] Schichtsicherungen (Locks) geladen/aktualisiert.")
        except Exception as e:
            print(f"[FEHLER][DM] Laden der Schichtsicherungen fehlgeschlagen: {e}")
            # Optional: Hier Fehler behandeln oder weitermachen
        # --- ENDE KORREKTUR ---

        update_progress(15, "Lade alle Monatsdaten in einem Durchgang (DB-Optimierung)...") # Prozent angepasst
        # Konsolidierte Daten aus der DB holen
        consolidated_data = get_consolidated_month_data(year, month)
        if consolidated_data is None:
            print("[FEHLER] get_consolidated_month_data gab None zurück.")
            # Setze alle Caches auf leere Werte, um Folgefehler zu vermeiden
            self.shift_schedule_data, self.daily_counts, self.wunschfrei_data, self._prev_month_shifts, self.processed_vacations = {}, {}, {}, {}, {}
            self.violation_cells.clear()
            raise Exception("Fehler beim Abrufen der Kerndaten aus der Datenbank.")

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")
        # Daten in die Caches des DataManagers laden
        self.shift_schedule_data = consolidated_data.get('shifts', {})
        self.wunschfrei_data = consolidated_data.get('wunschfrei_requests', {})
        self._prev_month_shifts = consolidated_data.get('prev_month_shifts', {})  # Cache für Vormonat
        self.previous_month_shifts = self._prev_month_shifts  # Setze das öffentliche Attribut
        raw_vacations = consolidated_data.get('vacation_requests', [])
        self.processed_vacations = self._process_vacations(year, month, raw_vacations)

        # NEU: Lade globale Events direkt aus der DB
        try:
            # Stellt sicher, dass die App die Events für das Jahr geladen hat.
            # --- KORREKTUR: Zugriff über self.app ---
            self.app.global_events_data = EventManager.get_events_for_year(year)
            # --- ENDE KORREKTUR ---
            print(f"[DM Load] Globale Events für {year} aus Datenbank geladen.")
        except Exception as e:
            print(f"[FEHLER] Fehler beim Laden der globalen Events aus DB: {e}")
            # Wichtig: Fülle mit Leer-Dict, um Folgefehler in der App-Logik zu vermeiden
            # --- KORREKTUR: Zugriff über self.app ---
            self.app.global_events_data = {}
            # --- ENDE KORREKTUR ---

        # Neuberechnung der Tageszählungen (daily_counts) aus den gerade geladenen Schichtdaten
        print("[DM Load] Neuberechnung der Tageszählungen (daily_counts) aus Schichtdaten...")
        self.daily_counts.clear()  # Alte Zählungen löschen

        def should_count_shift(shift_abbr):
            # Definiert, welche Schichten für die Tageszählung relevant sind
            return shift_abbr and shift_abbr not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?']  # Liste anpassen bei Bedarf

        for user_id_str, shifts in self.shift_schedule_data.items():
            for date_str, shift in shifts.items():
                try:  # Sicherstellen, dass das Datum zum aktuellen Monat gehört
                    shift_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if shift_date.year != year or shift_date.month != month: continue
                except ValueError:
                    continue  # Ungültiges Datum ignorieren
                # Wenn Schicht gezählt werden soll, inkrementieren
                if should_count_shift(shift):
                    if date_str not in self.daily_counts: self.daily_counts[date_str] = {}
                    self.daily_counts[date_str][shift] = self.daily_counts[date_str].get(shift, 0) + 1
        print("[DM Load] Tageszählungen erfolgreich neu berechnet.")

        # Schichtzeiten vorverarbeiten (nachdem Schichtdaten geladen wurden)
        self._preprocess_shift_times()

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde)...")
        # Volle Konfliktprüfung für den gesamten Monat durchführen
        self.update_violation_set(year, month)

        update_progress(95, "Vorbereitung abgeschlossen.")

        # Geladene und verarbeitete Daten zurückgeben
        return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Aktualisiert das violation_cells Set gezielt nach einer Schichtänderung und gibt betroffene Zellen zurück."""
        print(f"[DM-Incr] Update für User {user_id} am {date_obj}: '{old_shift}' -> '{new_shift}'")
        affected_cells = set()
        day = date_obj.day;
        year = date_obj.year;
        month = date_obj.month
        user_id_str = str(user_id)

        # Hilfsfunktionen zum Hinzufügen/Entfernen von Violations
        def add_violation(uid, d):
            cell = (uid, d)
            if cell not in self.violation_cells:  # Korrekte Einrückung
                print(f"    -> ADD V: U{uid}, D{d}")
                self.violation_cells.add(cell)
                affected_cells.add(cell)

        def remove_violation(uid, d):
            cell = (uid, d)
            if cell in self.violation_cells:  # Korrekte Einrückung
                print(f"    -> REMOVE V: U{uid}, D{d}")
                self.violation_cells.discard(cell)
                affected_cells.add(cell)

        # 1. Ruhezeitkonflikte (N -> T/6) prüfen und aktualisieren
        print("  Prüfe Ruhezeit...")
        prev_day_obj = date_obj - timedelta(days=1);
        next_day_obj = date_obj + timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_day_obj, year, month)
        # Nächste Schicht direkt aus aktuellen Daten holen (könnte Folgemonat sein)
        next_shift = self.shift_schedule_data.get(user_id_str, {}).get(next_day_obj.strftime('%Y-%m-%d'), "")
        # Prüfen ob nächste Schicht eine Arbeitsschicht ist
        is_next_shift_work = next_shift not in ["", "FREI", None, "U", "X", "EU", "WF", "U?"]
        # Prüfen ob alte Schicht Konflikt war
        is_old_shift_conflict = old_shift not in ["", "N.", "U", "X", "EU", "WF", "U?"]
        # Prüfen ob neue Schicht Konflikt ist
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
        # Aktueller Hund des Users
        dog = user_data.get('diensthund') if user_data and user_data.get('diensthund') != '---' else None
        # Alter Hund des Users
        old_dog = user_data.get('diensthund') if user_data else None
        if old_dog == '---': old_dog = None

        involved_dogs = set()  # Hunde, deren Konflikte neu bewertet werden müssen
        if dog: involved_dogs.add(dog)
        if old_dog and old_dog != dog: involved_dogs.add(old_dog)
        if old_shift and not new_shift and old_dog: involved_dogs.add(old_dog)  # User hat Dienst entfernt
        # Fallback
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

        # Neubewertung für jeden betroffenen Hund
        for current_dog in involved_dogs:
            # Explizite Schleife statt List Comprehension
            assignments_today = []
            for other_user in self.cached_users_for_month:
                if other_user.get('diensthund') == current_dog:
                    other_user_id = other_user.get('id')
                    if other_user_id is None: continue
                    current_shift_for_other = new_shift if other_user_id == user_id else self._get_shift_helper(
                        str(other_user_id), date_obj, year, month)
                    if current_shift_for_other:  # Nur hinzufügen, wenn der User eine *Arbeits*-Schicht hat
                        assignments_today.append({'id': other_user_id, 'shift': current_shift_for_other})

            # User, die vorher/jetzt beteiligt waren/sind
            involved_user_ids_now = {a['id'] for a in assignments_today}
            involved_user_ids_before = set(involved_user_ids_now)
            if old_shift and user_id not in involved_user_ids_now and old_dog == current_dog:
                involved_user_ids_before.add(user_id)
            all_potentially_involved = involved_user_ids_now.union(involved_user_ids_before)

            # ACHTUNG: Hier wurde eine Variable 'assignments' verwendet, die nicht definiert ist.
            # Ich nehme an, es sollte assignments_today sein (wie in der Hundelogik oben).
            assignments_to_check = assignments_today

            print(
                f"    Hund '{current_dog}' T{day}. Beteiligte (Vorher/Nachher): {all_potentially_involved}. Aktuelle Assignments: {assignments_today}")

            # Entferne alte Konflikte
            print(f"    -> Entferne alte Konflikte für Hund '{current_dog}' T{day}...")
            for uid_involved in all_potentially_involved:
                remove_violation(uid_involved, day)

            # Prüfe neue Konflikte
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
        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[DM Counts] Aktualisiere Zählung für {date_str}: '{old_shift}' -> '{new_shift}'")
        # Stellen Sie sicher, dass wir den Tag initialisieren, wenn er fehlt
        if date_str not in self.daily_counts:
            self.daily_counts[date_str] = {}

        counts_today = self.daily_counts[date_str]

        def should_count_shift(shift_abbr):
            return shift_abbr and shift_abbr not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?']

        # Alte Schicht dekrementieren
        if should_count_shift(old_shift):
            counts_today[old_shift] = counts_today.get(old_shift, 1) - 1
            # SICHERHEITSKORREKTUR: Entferne den Schlüssel, wenn die Zählung 0 ist
            if counts_today[old_shift] <= 0:
                del counts_today[old_shift]

        # Neue Schicht inkrementieren
        if should_count_shift(new_shift):
            counts_today[new_shift] = counts_today.get(new_shift, 0) + 1

        # KORRIGIERTE LOGIK: Entferne den Tag-Eintrag nur, wenn das innere Dictionary (counts_today) leer ist.
        # counts_today ist ein Verweis auf self.daily_counts[date_str]
        if not counts_today and date_str in self.daily_counts:
            # DIESE ZEILE ist die KORREKTUR, um den KeyError zu beheben
            del self.daily_counts[date_str]

        print(f"[DM Counts] Neue Zählung für {date_str}: {self.daily_counts.get(date_str, {})}")

    def _preprocess_shift_times(self):
        """ Konvertiert Schichtzeiten in Minuten-Intervalle für schnelle Überlappungsprüfung. """
        self._preprocessed_shift_times.clear()
        self._warned_missing_times.clear()
        if not self.app.shift_types_data:
            print("[WARNUNG] shift_types_data ist leer in _preprocess_shift_times.")
            return
        print("[DM] Verarbeite Schichtzeiten vor...")
        count = 0
        for abbrev, data in self.app.shift_types_data.items():
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
        processed = defaultdict(dict);  # {user_id_str: {date_obj: status}}
        month_start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        month_end = date(year, month, last_day)

        for req in raw_vacations:
            user_id_str = str(req.get('user_id'))
            if not user_id_str: continue
            try:
                start_date = datetime.strptime(req['start_date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(req['end_date'], '%Y-%m-%d').date()
                status = req.get('status', 'Unbekannt')

                current_date = start_date
                while current_date <= end_date:
                    if month_start <= current_date <= month_end:
                        processed[user_id_str][current_date] = status;
                    current_date += timedelta(days=1)
            except (ValueError, TypeError, KeyError) as e:
                print(f"[WARNUNG] Fehler beim Verarbeiten von Urlaub ID {req.get('id', 'N/A')}: {e}")

        return dict(processed)

    def get_min_staffing_for_date(self, current_date):
        """ Ermittelt die Mindestbesetzungsregeln für ein spezifisches Datum. """
        rules = getattr(self.app, 'staffing_rules', {});
        min_staffing = {}
        min_staffing.update(rules.get('Daily', {}))
        weekday = current_date.weekday()
        if weekday >= 5:
            min_staffing.update(rules.get('Sa-So', {}))
        elif weekday == 4:
            min_staffing.update(rules.get('Fr', {}))
        else:
            min_staffing.update(rules.get('Mo-Do', {}))
        if hasattr(self.app, 'is_holiday') and self.app.is_holiday(current_date): min_staffing.update(
            rules.get('Holiday', {}))
        # Bereinigen: Nur gültige numerische Werte >= 0 zurückgeben
        return {k: int(v) for k, v in min_staffing.items() if
                isinstance(v, (int, str)) and str(v).isdigit() and int(v) >= 0}

    def calculate_total_hours_for_user(self, user_id_str, year, month):
        """ Berechnet die geschätzten Gesamtstunden für einen Benutzer im Monat. """
        total_hours = 0.0;
        try:
            user_id_int = int(user_id_str)
        except ValueError:
            print(f"[WARNUNG] Ungültige user_id_str in calculate_total_hours: {user_id_str}");
            return 0.0

        days_in_month = calendar.monthrange(year, month)[1]

        # Überhang von N.-Schicht aus Vormonat
        prev_month_last_day = date(year, month, 1) - timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_month_last_day, year, month)
        if prev_shift == 'N.':
            shift_info_n = self.app.shift_types_data.get('N.')
            hours_overlap = 6.0  # Fallback
            if shift_info_n and shift_info_n.get('end_time'):
                try:
                    end_time_n = datetime.strptime(shift_info_n['end_time'], '%H:%M').time();
                    hours_overlap = end_time_n.hour + end_time_n.minute / 60.0
                except ValueError:
                    pass  # Bei Fehler Fallback nutzen
            total_hours += hours_overlap

        # Tage des aktuellen Monats
        user_shifts_this_month = self.shift_schedule_data.get(user_id_str, {})
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')
            shift = user_shifts_this_month.get(date_str, "");
            vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date)
            request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)  # Tuple (status, shift)

            actual_shift_for_hours = shift
            if vacation_status == 'Genehmigt':
                actual_shift_for_hours = 'U'
            elif request_info and request_info[1] == 'WF' and request_info[0] in ["Genehmigt", "Akzeptiert"]:
                actual_shift_for_hours = 'X'

            if actual_shift_for_hours in self.app.shift_types_data:
                hours = float(self.app.shift_types_data[actual_shift_for_hours].get('hours', 0.0))
                # Korrektur für N.-Schicht am Monatsende
                if actual_shift_for_hours == 'N.' and day == days_in_month:
                    shift_info_n = self.app.shift_types_data.get('N.')
                    hours = 6.0  # Fallback
                    if shift_info_n and shift_info_n.get('start_time'):
                        try:
                            start_time_n = datetime.strptime(shift_info_n['start_time'], '%H:%M').time();
                            hours = 24.0 - (start_time_n.hour + start_time_n.minute / 60.0)
                        except ValueError:
                            pass  # Bei Fehler Fallback nutzen
                total_hours += hours

        return round(total_hours, 2)

    def update_violation_set(self, year, month):
        """ Prüft den *gesamten* Monat auf Konflikte (Ruhezeit, Hunde) und füllt self.violation_cells. """
        print(f"[DM-Full] Starte volle Konfliktprüfung für {year}-{month:02d}...")
        self.violation_cells.clear();
        days_in_month = calendar.monthrange(year, month)[1]
        current_user_order = self.cached_users_for_month
        if not current_user_order: print("[WARNUNG] Benutzer-Cache leer in update_violation_set!"); return

        # 1. Ruhezeitkonflikte (N -> T/6 und NEUE REGEL: N -> QA/S)
        for user in current_user_order:
            user_id = user.get('id');
            if user_id is None: continue;
            user_id_str = str(user_id)
            current_check_date = date(year, month, 1) - timedelta(days=1);
            end_check_date = date(year, month, days_in_month)
            while current_check_date < end_check_date:
                next_day_date = current_check_date + timedelta(days=1)
                shift1 = self._get_shift_helper(user_id_str, current_check_date, year, month);
                shift2 = self._get_shift_helper(user_id_str, next_day_date, year, month)

                # Prüfen auf N -> T/6 (bestehende Regel) oder N -> QA/S (neue Regel)
                is_ruhezeit_violation = (shift1 == 'N.' and shift2 in ["T.", "6", "QA", "S"])

                if is_ruhezeit_violation:
                    if current_check_date.month == month and current_check_date.year == year:
                        self.violation_cells.add((user_id, current_check_date.day))
                    if next_day_date.month == month and next_day_date.year == year:
                        self.violation_cells.add((user_id, next_day_date.day))

                current_check_date += timedelta(days=1)

        # 2. Hundekonflikte (zeitliche Überlappung am selben Tag)
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            dog_schedule_today = defaultdict(list)
            # Sammle alle Hundezuweisungen für diesen Tag
            for user in current_user_order:
                dog = user.get('diensthund')
                if dog and dog != '---':
                    user_id = user.get('id');
                    if user_id is None: continue;
                    user_id_str = str(user_id)
                    shift = self._get_shift_helper(user_id_str, current_date, year, month)
                    if shift: dog_schedule_today[dog].append({'id': user_id, 'shift': shift})
            # Prüfe jeden Hund auf Konflikte
            for dog, assignments in dog_schedule_today.items():
                if len(assignments) > 1:
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            u1 = assignments[i];
                            u2 = assignments[j]
                            if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                                self.violation_cells.add((u1['id'], day));
                                self.violation_cells.add((u2['id'], day))

        print(f"[DM-Full] Volle Konfliktprüfung abgeschlossen. Konflikte: {len(self.violation_cells)}")

    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlappung mit vorverarbeiteten Zeiten (Cache). """
        # Explizite Prüfung statt free_shifts_indicators
        if shift1_abbrev in ['U', 'X', 'EU', 'WF', '', 'FREI'] or shift2_abbrev in ['U', 'X', 'EU', 'WF', '',
                                                                                    'FREI']: return False

        s1, e1 = self._preprocessed_shift_times.get(shift1_abbrev, (None, None))
        s2, e2 = self._preprocessed_shift_times.get(shift2_abbrev, (None, None))

        if s1 is None or s2 is None:
            # Gib Warnung aus, wenn Zeit fehlt (nur einmal pro Schichtkürzel)
            if s1 is None and shift1_abbrev not in self._warned_missing_times:
                print(f"[WARNUNG] Zeit für Schicht '{shift1_abbrev}' fehlt im Cache (_check_time_overlap).")
                self._warned_missing_times.add(shift1_abbrev)
            if s2 is None and shift2_abbrev not in self._warned_missing_times:
                print(f"[WARNUNG] Zeit für Schicht '{shift2_abbrev}' fehlt im Cache (_check_time_overlap).")
                self._warned_missing_times.add(shift2_abbrev)
            return False  # Kein Konflikt feststellbar

        # Korrekte Überlappungsprüfung
        return (s1 < e2) and (s2 < e1)