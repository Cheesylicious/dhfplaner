# gui/shift_plan_data_manager.py
from datetime import date, datetime, timedelta
import calendar
from collections import defaultdict
import traceback  # Import für detailliertere Fehlermeldungen

# DB Imports
from database.db_shifts import get_consolidated_month_data
from database.db_users import get_user_by_id, get_ordered_users_for_schedule


class ShiftPlanDataManager:
    """
    Verantwortlich für das Laden, Vorverarbeiten und Berechnen aller Daten,
    die für die Anzeige des Dienstplans benötigt werden (Staffing, Stunden, Konflikte).
    """

    def __init__(self, app):
        self.app = app
        # Caches für die Hauptdaten
        self.shift_schedule_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}
        self.violation_cells = set()  # Menge von Tupeln: (user_id, day_of_month)

        # Cache für Vormonats-Shifts
        self._prev_month_shifts = {}

        # Cache für vorverarbeitete Schichtzeiten
        self._preprocessed_shift_times = {}

        # Cache für Benutzer (wird in load_and_process_data gefüllt)
        self.cached_users_for_month = []

        # Set zur Nachverfolgung von Warnungen über fehlende Schichtzeiten
        self._warned_missing_times = set()

    def _get_shift_helper(self, user_id_str, date_obj, current_year, current_month):
        """ Holt die Schicht für einen User an einem Datum, berücksichtigt Vormonat-Cache. """
        date_str = date_obj.strftime('%Y-%m-%d')
        shift = self.shift_schedule_data.get(user_id_str, {}).get(date_str)

        is_previous_month = False
        if date_obj.year < current_year:
            is_previous_month = True
        elif date_obj.year == current_year and date_obj.month < current_month:
            is_previous_month = True

        if shift is None and is_previous_month:
            shift = self._prev_month_shifts.get(user_id_str, {}).get(date_str, "")
        elif shift is None:
            shift = ""

        return shift if shift not in ["", "FREI", None] else ""

    def load_and_process_data(self, year, month, progress_callback=None):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch. Ruft danach die volle Konfliktprüfung auf.
        """

        def update_progress(value, text):
            if progress_callback: progress_callback(value, text)

        update_progress(5, "Lade Benutzerreihenfolge...")
        current_date_for_archive_check = date(year, month, 1)
        self.cached_users_for_month = get_ordered_users_for_schedule(include_hidden=True,
                                                                     for_date=current_date_for_archive_check)
        print(f"[DM Load] {len(self.cached_users_for_month)} Benutzer für {year}-{month} geladen (inkl. versteckter).")

        update_progress(10, "Lade alle Monatsdaten in einem Durchgang (DB-Optimierung)...")
        consolidated_data = get_consolidated_month_data(year, month)
        if consolidated_data is None:
            print("[FEHLER] get_consolidated_month_data gab None zurück.")
            self.shift_schedule_data, self.daily_counts, self.wunschfrei_data, self._prev_month_shifts, self.processed_vacations = {}, {}, {}, {}, {}
            self.violation_cells.clear()
            raise Exception("Fehler beim Abrufen der Kerndaten aus der Datenbank.")

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")
        self.shift_schedule_data = consolidated_data.get('shifts', {})

        # --- KORREKTUR START ---
        # self.daily_counts = consolidated_data.get('daily_counts', {}) # <-- ENTFERNT: Diese Daten sind veraltet.

        # Stattdessen: Berechne daily_counts jedes Mal neu aus den frisch geladenen shift_schedule_data
        print("[DM Load] Neuberechnung der Tageszählungen (daily_counts) aus Schichtdaten...")
        self.daily_counts.clear()  # Alte (potenziell veraltete) Daten löschen

        def should_count_shift(shift_abbr):
            # Dieselbe Logik wie in recalculate_daily_counts_for_day
            return shift_abbr and shift_abbr not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?']

        # Iteriere über die gerade geladenen Schichtdaten
        for user_id_str, shifts in self.shift_schedule_data.items():
            for date_str, shift in shifts.items():
                # Prüfen, ob das Datum im aktuellen Monat liegt (wichtig!)
                try:
                    shift_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if shift_date.year != year or shift_date.month != month:
                        continue  # Schicht gehört nicht zum aktuellen Monat
                except ValueError:
                    continue  # Ungültiges Datum überspringen

                # Wenn die Schicht gezählt werden soll, füge sie hinzu
                if should_count_shift(shift):
                    if date_str not in self.daily_counts:
                        self.daily_counts[date_str] = {}
                    counts_today = self.daily_counts[date_str]
                    counts_today[shift] = counts_today.get(shift, 0) + 1
        print("[DM Load] Tageszählungen erfolgreich neu berechnet.")
        # --- KORREKTUR ENDE ---

        self.wunschfrei_data = consolidated_data.get('wunschfrei_requests', {})
        self._prev_month_shifts = consolidated_data.get('prev_month_shifts', {})
        raw_vacations = consolidated_data.get('vacation_requests', [])
        self.processed_vacations = self._process_vacations(year, month, raw_vacations)

        self._preprocess_shift_times()  # Muss nach Laden der Schichtdaten erfolgen

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde) und Staffing...")
        self.update_violation_set(year, month)

        update_progress(95, "Vorbereitung abgeschlossen.")

        return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Aktualisiert das violation_cells Set gezielt und gibt betroffene Zellen zurück."""
        print(f"[DM-Incr] Update für User {user_id} am {date_obj}: '{old_shift}' -> '{new_shift}'")
        affected_cells = set()
        day = date_obj.day;
        year = date_obj.year;
        month = date_obj.month
        user_id_str = str(user_id)

        def add_violation(uid, d):
            cell = (uid, d);
            if cell not in self.violation_cells: print(f"    -> ADD V: U{uid}, D{d}"); self.violation_cells.add(
                cell); affected_cells.add(cell)

        def remove_violation(uid, d):
            cell = (uid, d);
            if cell in self.violation_cells: print(f"    -> REMOVE V: U{uid}, D{d}"); self.violation_cells.discard(
                cell); affected_cells.add(cell)

        # 1. Ruhezeit
        print("  Prüfe Ruhezeit...")
        prev_day_obj = date_obj - timedelta(days=1);
        next_day_obj = date_obj + timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_day_obj, year, month)
        # next_shift direkt holen (kann Folgemonat sein)
        next_shift = self.shift_schedule_data.get(user_id_str, {}).get(next_day_obj.strftime('%Y-%m-%d'), "")
        next_shift = next_shift if next_shift not in ["", "FREI", None] else ""

        # a) Alte entfernen
        if old_shift == 'N.':
            remove_violation(user_id, day)
            if next_day_obj.month == month and next_day_obj.year == year: remove_violation(user_id, day + 1)
        if prev_shift == 'N.' and old_shift not in ["", "N.", "U", "X", "EU"]:
            if prev_day_obj.month == month and prev_day_obj.year == year: remove_violation(user_id, day - 1)
            remove_violation(user_id, day)
        # b) Neue hinzufügen
        if new_shift == 'N.' and next_shift not in ["", "N.", "U", "X", "EU"]:
            add_violation(user_id, day)
            if next_day_obj.month == month and next_day_obj.year == year: add_violation(user_id, day + 1)
        if prev_shift == 'N.' and new_shift not in ["", "N.", "U", "X", "EU"]:
            if prev_day_obj.month == month and prev_day_obj.year == year: add_violation(user_id, day - 1)
            add_violation(user_id, day)

        # 2. Hundekonflikt
        print("  Prüfe Hundekonflikt...")
        user_data = next((u for u in self.cached_users_for_month if u['id'] == user_id), None)
        dog = user_data.get('diensthund') if user_data else None

        if dog and dog != '---':
            assignments_today = []
            for other_user in self.cached_users_for_month:
                if other_user.get('diensthund') == dog:
                    other_user_id = other_user['id'];
                    other_user_id_str = str(other_user_id)
                    current_shift = new_shift if other_user_id == user_id else self._get_shift_helper(other_user_id_str,
                                                                                                      date_obj, year,
                                                                                                      month)
                    if current_shift: assignments_today.append({'id': other_user_id, 'shift': current_shift})
            involved_user_ids = set(a['id'] for a in assignments_today)
            if old_shift: involved_user_ids.add(user_id)  # User auch prüfen, wenn er Dienst entfernt hat
            print(f"    Hund '{dog}' T{day}. Beteiligte: {involved_user_ids}. Assignments: {assignments_today}")
            print(f"    -> Entferne alte Konflikte für Hund '{dog}' T{day}...")
            for uid_involved in involved_user_ids: remove_violation(uid_involved, day)
            print(f"    -> Prüfe neue Konflikte für Hund '{dog}' T{day}...")
            if len(assignments_today) > 1:
                for i in range(len(assignments_today)):
                    for j in range(i + 1, len(assignments_today)):
                        u1, u2 = assignments_today[i], assignments_today[j]
                        if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                            print(f"      -> Konflikt: {u1['id']}({u1['shift']}) vs {u2['id']}({u2['shift']})")
                            add_violation(u1['id'], day);
                            add_violation(u2['id'], day)
        else:  # User hat keinen Hund oder keinen Dienst mehr
            remove_violation(user_id, day)  # Sicherstellen, dass er selbst keinen Konflikt hat
            old_dog = user_data.get('diensthund') if user_data else None  # Hund *vor* Änderung?
            if old_shift and old_dog and old_dog != '---':  # Nur prüfen, wenn er vorher Dienst MIT Hund hatte
                remaining_assignments = [];
                involved_user_ids = set()
                for other_user in self.cached_users_for_month:
                    if other_user['id'] == user_id: continue  # Ignoriere aktuellen User
                    if other_user.get('diensthund') == old_dog:
                        other_shift = self._get_shift_helper(str(other_user['id']), date_obj, year, month)
                        if other_shift:
                            assign_data = {'id': other_user['id'], 'shift': other_shift}
                            remaining_assignments.append(assign_data);
                            involved_user_ids.add(other_user['id'])
                print(f"    User {user_id} entfernt. Prüfe Rest für Hund '{old_dog}' T{day}...")
                for uid_involved in involved_user_ids: remove_violation(uid_involved, day)  # Alte entfernen
                if len(remaining_assignments) > 1:  # Neue prüfen
                    for i in range(len(remaining_assignments)):
                        for j in range(i + 1, len(remaining_assignments)):
                            u1, u2 = remaining_assignments[i], remaining_assignments[j]
                            if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                                print(f"      -> Rest-Konflikt: {u1['id']}({u1['shift']}) vs {u2['id']}({u2['shift']})")
                                add_violation(u1['id'], day);
                                add_violation(u2['id'], day)

        print(f"[DM-Incr] Update abgeschlossen. Betroffene Zellen: {affected_cells}")
        return affected_cells

    def recalculate_daily_counts_for_day(self, date_obj, old_shift, new_shift):
        """Aktualisiert self.daily_counts für einen bestimmten Tag nach Schichtänderung."""
        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[DM Counts] Aktualisiere Zählung für {date_str}: '{old_shift}' -> '{new_shift}'")
        if date_str not in self.daily_counts: self.daily_counts[date_str] = {}
        counts_today = self.daily_counts[date_str]

        def should_count_shift(shift_abbr):
            return shift_abbr and shift_abbr not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?']

        # Alte Schicht dekrementieren
        if should_count_shift(old_shift):
            counts_today[old_shift] = counts_today.get(old_shift, 1) - 1
            if counts_today[old_shift] <= 0 and old_shift in counts_today: del counts_today[old_shift]
        # Neue Schicht inkrementieren
        if should_count_shift(new_shift):
            counts_today[new_shift] = counts_today.get(new_shift, 0) + 1
        # Bereinigen, falls Tag leer ist
        if not counts_today and date_str in self.daily_counts: del self.daily_counts[date_str]
        print(f"[DM Counts] Neue Zählung für {date_str}: {self.daily_counts.get(date_str, {})}")

    def _preprocess_shift_times(self):
        """ Konvertiert Schichtzeiten in Minuten für schnelle Überlappungsprüfung. """
        self._preprocessed_shift_times.clear()
        self._warned_missing_times.clear()  # Warnungen zurücksetzen
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
                s = datetime.strptime(start_time_str, '%H:%M').time();
                e = datetime.strptime(end_time_str, '%H:%M').time()
                s_min = s.hour * 60 + s.minute;
                e_min = e.hour * 60 + e.minute
                if e_min <= s_min: e_min += 24 * 60  # Über Mitternacht
                self._preprocessed_shift_times[abbrev] = (s_min, e_min);
                count += 1
            except ValueError:
                print(f"[WARNUNG] Ungültiges Zeitformat für Schicht '{abbrev}'.")
        print(f"[DM] {count} Schichtzeiten erfolgreich vorverarbeitet.")

    def _process_vacations(self, year, month, raw_vacations):
        """ Verarbeitet Urlaubsanträge für den gegebenen Monat. """
        processed = defaultdict(dict);
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        for req in raw_vacations:
            user_id_str = str(req['user_id'])
            try:
                start = datetime.strptime(req['start_date'], '%Y-%m-%d').date();
                end = datetime.strptime(req['end_date'], '%Y-%m-%d').date()
                current_date = max(start, month_start);
                last_date_to_check = min(end, month_end)
                while current_date <= last_date_to_check:
                    processed[user_id_str][current_date] = req['status'];
                    current_date += timedelta(days=1)
            except (ValueError, TypeError) as e:
                print(f"[WARNUNG] Urlaub ID {req.get('id')} Fehler: {e}")
        return dict(processed)

    def get_min_staffing_for_date(self, current_date):
        """ Ermittelt Mindestbesetzung für ein Datum. """
        rules = getattr(self.app, 'staffing_rules', {});
        min_staffing = {}
        min_staffing.update(rules.get('Daily', {}))
        if current_date.weekday() >= 5:
            min_staffing.update(rules.get('Sa-So', {}))
        elif current_date.weekday() == 4:
            min_staffing.update(rules.get('Fr', {}))
        else:
            min_staffing.update(rules.get('Mo-Do', {}))
        if hasattr(self.app, 'is_holiday') and self.app.is_holiday(current_date):
            min_staffing.update(rules.get('Holiday', {}))
        return {k: int(v) for k, v in min_staffing.items() if
                isinstance(v, (int, str)) and str(v).isdigit() and int(v) >= 0}

    def calculate_total_hours_for_user(self, user_id_str, year, month):
        """ Berechnet Gesamtstunden für einen User im Monat. """
        total_hours = 0.0;
        days_in_month = calendar.monthrange(year, month)[1]
        prev_month_last_day = date(year, month, 1) - timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_month_last_day, year, month)
        if prev_shift == 'N.':
            shift_info = self.app.shift_types_data.get('N.')
            if shift_info and shift_info.get('end_time'):
                try:
                    end_time = datetime.strptime(shift_info['end_time'],
                                                 '%H:%M').time(); total_hours += end_time.hour + end_time.minute / 60.0
                except ValueError:
                    total_hours += 6.0
            else:
                total_hours += 6.0
        user_shifts = self.shift_schedule_data.get(user_id_str, {})
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')
            shift = user_shifts.get(date_str, "");
            vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date)
            request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)
            actual_shift_for_hours = shift
            if vacation_status == 'Genehmigt':
                actual_shift_for_hours = 'U'
            elif request_info and ("Akzeptiert" in request_info[0] or "Genehmigt" in request_info[0]) and request_info[
                1] == 'WF':
                actual_shift_for_hours = 'X'
            if actual_shift_for_hours in self.app.shift_types_data:
                hours = float(
                    self.app.shift_types_data[actual_shift_for_hours].get('hours', 0.0))  # Konvertiere zu float
                if actual_shift_for_hours == 'N.' and day == days_in_month:
                    shift_info = self.app.shift_types_data.get('N.')
                    if shift_info and shift_info.get('start_time'):
                        try:
                            start_time = datetime.strptime(shift_info['start_time'], '%H:%M').time(); hours = 24.0 - (
                                        start_time.hour + start_time.minute / 60.0)
                        except ValueError:
                            hours = 6.0
                    else:
                        hours = 6.0
                total_hours += hours
        return round(total_hours, 2)

    def update_violation_set(self, year, month):
        """ Prüft *gesamten* Monat auf Konflikte (nur bei initialem Laden). """
        print(f"[DM-Full] Starte volle Konfliktprüfung für {year}-{month:02d}...")
        self.violation_cells.clear();
        days_in_month = calendar.monthrange(year, month)[1]
        current_user_order = self.cached_users_for_month
        if not current_user_order: print("[WARNUNG] Benutzer-Cache leer!"); return

        # 1. Ruhezeit
        for user in current_user_order:
            user_id_str = str(user['id'])
            current_check_date = date(year, month, 1) - timedelta(days=1)
            end_check_date = date(year, month, days_in_month)
            while current_check_date < end_check_date:
                next_day_date = current_check_date + timedelta(days=1)
                shift1 = self._get_shift_helper(user_id_str, current_check_date, year, month)
                shift2 = self._get_shift_helper(user_id_str, next_day_date, year, month)
                if shift1 == 'N.' and shift2 not in ["", "N.", "U", "X", "EU"]:
                    if current_check_date.month == month and current_check_date.year == year: self.violation_cells.add(
                        (user['id'], current_check_date.day))
                    if next_day_date.month == month and next_day_date.year == year: self.violation_cells.add(
                        (user['id'], next_day_date.day))
                current_check_date += timedelta(days=1)

        # 2. Hundekonflikt
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            dog_schedule = defaultdict(list)
            for user in current_user_order:
                dog = user.get('diensthund')
                if dog and dog != '---':
                    user_id_str = str(user['id'])
                    shift = self._get_shift_helper(user_id_str, current_date, year, month)
                    if shift: dog_schedule[dog].append({'id': user['id'], 'shift': shift})
            for dog, assignments in dog_schedule.items():
                if len(assignments) > 1:
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            u1, u2 = assignments[i], assignments[j]
                            if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                                self.violation_cells.add((u1['id'], day));
                                self.violation_cells.add((u2['id'], day))
        print(f"[DM-Full] Volle Konfliktprüfung abgeschlossen. Konflikte: {len(self.violation_cells)}")

    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """ Prüft Zeitüberlappung mit Cache. """
        if shift1_abbrev in ['U', 'X', 'EU', 'WF', ''] or shift2_abbrev in ['U', 'X', 'EU', 'WF', '']: return False
        s1, e1 = self._preprocessed_shift_times.get(shift1_abbrev, (None, None))
        s2, e2 = self._preprocessed_shift_times.get(shift2_abbrev, (None, None))
        if s1 is None or s2 is None:
            # --- KORREKTUR INDENTATION ---
            # Diese Warnungen gehören *innerhalb* des if-Blocks
            warned = False
            if s1 is None and shift1_abbrev not in self._warned_missing_times:
                print(f"[WARNVNG] Zeit für Schicht '{shift1_abbrev}' fehlt im Cache (_check_time_overlap).")
                self._warned_missing_times.add(shift1_abbrev)
                warned = True
            if s2 is None and shift2_abbrev not in self._warned_missing_times:
                print(f"[WARNUNG] Zeit für Schicht '{shift2_abbrev}' fehlt im Cache (_check_time_overlap).")
                self._warned_missing_times.add(shift2_abbrev)
                warned = True
            # --- ENDE KORREKTUR INDENTATION ---
            return False  # Wichtig: Hier False zurückgeben, wenn Zeiten fehlen
        # Korrekte Überlappungsprüfung
        overlap = (s1 < e2) and (s2 < e1)
        return overlap

# Kein Code nach der Klassendefinition