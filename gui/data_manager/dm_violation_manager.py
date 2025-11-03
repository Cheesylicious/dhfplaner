# gui/data_manager/dm_violation_manager.py
# NEU: Ausgelagerte Logik für Konflikt- und Verletzungsprüfungen (Regel 4)

from datetime import date, datetime, timedelta
from collections import defaultdict
import calendar


class ViolationManager:
    """
    Verwaltet die Erkennung, Aktualisierung und Zwischenspeicherung
    von Regelverletzungen (Hunde, Ruhezeiten) im DataManager.
    (Ausgelagert nach Regel 4).
    """

    def __init__(self, data_manager):
        self.dm = data_manager
        self.app = data_manager.app  # Zugriff auf die Haupt-App

        # Cache für vorverarbeitete Schichtzeiten
        self._preprocessed_shift_times = {}
        # Set zur Nachverfolgung von Warnungen
        self._warned_missing_times = set()

    def _get_app_shift_types(self):
        """Hilfsfunktion, um shift_types_data sicher vom Bootloader (app.app) oder der App (app) zu holen."""
        if hasattr(self.app, 'shift_types_data'):
            return self.app.shift_types_data
        if hasattr(self.app, 'app') and hasattr(self.app.app, 'shift_types_data'):
            return self.app.app.shift_types_data
        print("[WARNUNG] shift_types_data weder in app noch in app.app gefunden.")
        return {}

    def _get_shift_helper(self, user_id_str, date_obj, current_year, current_month):
        """
        Holt die *Arbeits*-Schicht für einen User an einem Datum.
        Greift auf die aktiven Caches des DataManagers zu.
        """
        date_str = date_obj.strftime('%Y-%m-%d')

        # Greift auf die Caches des DM zu
        shift = self.dm.shift_schedule_data.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = self.dm._prev_month_shifts.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = self.dm.next_month_shifts.get(user_id_str, {}).get(date_str)
        if shift is None:
            shift = ""

        return shift if shift not in ["", "FREI", None, "U", "X", "EU", "WF", "U?"] else ""

    def preprocess_shift_times(self):
        """
        Konvertiert Schichtzeiten in Minuten-Intervalle für schnelle Überlappungsprüfung.
        Wird vom DataManager aufgerufen.
        """
        if self._preprocessed_shift_times:
            return

        self._preprocessed_shift_times.clear()
        self._warned_missing_times.clear()

        shift_types_data = self._get_app_shift_types()

        if not shift_types_data:
            print("[WARNUNG] shift_types_data ist leer in _preprocess_shift_times.")
            return

        print("[DM/Violation] Verarbeite Schichtzeiten vor...")
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
        print(f"[DM/Violation] {count} Schichtzeiten erfolgreich vorverarbeitet.")

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

    def update_violation_set(self, year, month):
        """
        Prüft den *gesamten* Monat auf Konflikte (Ruhezeit, Hunde)
        und füllt das violation_cells-Set im DataManager.
        """
        print(f"[DM/Violation] Starte volle Konfliktprüfung für {year}-{month:02d}...")

        # Stelle sicher, dass die Schichtzeiten geladen sind
        self.preprocess_shift_times()

        self.dm.violation_cells.clear();

        # Zugriff auf die gecachten User im DM
        current_user_order = self.dm.cached_users_for_month
        if not current_user_order:
            print("[WARNUNG] Benutzer-Cache leer in update_violation_set!");
            return

        # 1. Ruhezeitkonflikte (N -> T/6 und NEUE REGEL: N -> QA/S)
        for user in current_user_order:
            user_id = user.get('id');
            if user_id is None: continue;
            user_id_str = str(user_id)

            current_check_date = date(year, month, 1) - timedelta(days=1);
            # Korrigierte Monatsende-Berechnung
            days_in_month_for_loop = calendar.monthrange(year, month)[1]
            end_check_date = date(year, month, days_in_month_for_loop)

            while current_check_date <= end_check_date:
                next_day_date = current_check_date + timedelta(days=1)

                shift1 = self._get_shift_helper(user_id_str, current_check_date, year, month);
                shift2 = self._get_shift_helper(user_id_str, next_day_date, year, month)

                is_ruhezeit_violation = (shift1 == 'N.' and shift2 in ["T.", "6", "QA", "S"])

                if is_ruhezeit_violation:
                    if current_check_date.month == month and current_check_date.year == year:
                        self.dm.violation_cells.add((user_id, current_check_date.day))
                    if next_day_date.month == month and next_day_date.year == year:
                        self.dm.violation_cells.add((user_id, next_day_date.day))

                current_check_date += timedelta(days=1)

        # 2. Hundekonflikte (zeitliche Überlappung am selben Tag)
        days_in_month = calendar.monthrange(year, month)[1]
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

            for dog, assignments in dog_schedule_today.items():
                if len(assignments) > 1:
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            u1 = assignments[i];
                            u2 = assignments[j]
                            if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                                self.dm.violation_cells.add((u1['id'], day));
                                self.dm.violation_cells.add((u2['id'], day))

        print(f"[DM/Violation] Volle Konfliktprüfung abgeschlossen. Konflikte: {len(self.dm.violation_cells)}")

    def update_violations_incrementally(self, user_id, date_obj, old_shift, new_shift):
        """Aktualisiert das violation_cells Set gezielt nach einer Schichtänderung und gibt betroffene Zellen zurück."""

        # P5-Cache-Invalidierung (wird im DM selbst aufgerufen)
        # ...

        print(f"[DM/Violation-Incr] Update für User {user_id} am {date_obj}: '{old_shift}' -> '{new_shift}'")
        affected_cells = set()
        day = date_obj.day;
        year = date_obj.year;
        month = date_obj.month
        user_id_str = str(user_id)

        def add_violation(uid, d):
            cell = (uid, d)
            if cell not in self.dm.violation_cells:
                print(f"    -> ADD V: U{uid}, D{d}")
                self.dm.violation_cells.add(cell)
                affected_cells.add(cell)

        def remove_violation(uid, d):
            cell = (uid, d)
            if cell in self.dm.violation_cells:
                print(f"    -> REMOVE V: U{uid}, D{d}")
                self.dm.violation_cells.discard(cell)
                affected_cells.add(cell)

        # 1. Ruhezeitkonflikte
        print("  Prüfe Ruhezeit...")
        prev_day_obj = date_obj - timedelta(days=1);
        next_day_obj = date_obj + timedelta(days=1)
        prev_shift = self._get_shift_helper(user_id_str, prev_day_obj, year, month)
        next_shift = self._get_shift_helper(user_id_str, next_day_obj, year, month)

        # N. -> T/6/QA/S
        is_old_shift_conflict = old_shift in ["T.", "6", "QA", "S"]
        is_new_shift_conflict = new_shift in ["T.", "6", "QA", "S"]
        is_next_shift_conflict = next_shift in ["T.", "6", "QA", "S"]

        # a) Alte Konflikte entfernen
        # Fall 1: Die geänderte Schicht war 'N.'
        if old_shift == 'N.' and is_next_shift_conflict:
            remove_violation(user_id, day)
            if next_day_obj.month == month and next_day_obj.year == year:
                remove_violation(user_id, day + 1)
        # Fall 2: Die Schicht davor war 'N.' und die geänderte war ein Konflikt
        if prev_shift == 'N.' and is_old_shift_conflict:
            if prev_day_obj.month == month and prev_day_obj.year == year:
                remove_violation(user_id, day - 1)
            remove_violation(user_id, day)

        # b) Neue Konflikte hinzufügen
        # Fall 1: Die geänderte Schicht ist 'N.' und die nächste ist ein Konflikt
        if new_shift == 'N.' and is_next_shift_conflict:
            add_violation(user_id, day)
            if next_day_obj.month == month and next_day_obj.year == year:
                add_violation(user_id, day + 1)
        # Fall 2: Die Schicht davor ist 'N.' und die geänderte ist ein Konflikt
        if prev_shift == 'N.' and is_new_shift_conflict:
            if prev_day_obj.month == month and prev_day_obj.year == year:
                add_violation(user_id, day - 1)
            add_violation(user_id, day)

        # 2. Hundekonflikte
        print("  Prüfe Hundekonflikt...")
        user_data = next((u for u in self.dm.cached_users_for_month if u.get('id') == user_id), None)
        dog = user_data.get('diensthund') if user_data and user_data.get('diensthund') != '---' else None
        old_dog = user_data.get('diensthund') if user_data else None
        if old_dog == '---': old_dog = None

        involved_dogs = set()
        if dog: involved_dogs.add(dog)
        if old_dog and old_dog != dog: involved_dogs.add(old_dog)
        if old_shift and not new_shift and old_dog: involved_dogs.add(old_dog)

        # Finde alle Hunde, die an diesem Tag (potenziell) involviert waren oder sind
        if not involved_dogs and (old_shift or new_shift):
            for other_user in self.dm.cached_users_for_month:
                other_dog = other_user.get('diensthund')
                if other_dog and other_dog != '---':
                    other_id = other_user.get('id')
                    if other_id is None: continue
                    # Prüfe, ob der andere User an diesem Tag *jetzt* eine Schicht hat
                    other_shift_exists = self._get_shift_helper(str(other_id), date_obj, year, month)
                    if other_shift_exists:
                        involved_dogs.add(other_dog)
                    # Prüfe, ob der *geänderte* User (der die Schleife ausgelöst hat) diesen Hund hat
                    elif (other_id == user_id and dog == other_dog):
                        involved_dogs.add(other_dog)

        print(f"    -> Hunde zu prüfen für Tag {day}: {involved_dogs}")

        for current_dog in involved_dogs:
            assignments_today = []
            for other_user in self.dm.cached_users_for_month:
                if other_user.get('diensthund') == current_dog:
                    other_user_id = other_user.get('id')
                    if other_user_id is None: continue
                    # WICHTIG: Nutze den *neuen* Wert für den aktuellen User
                    current_shift_for_other = new_shift if other_user_id == user_id else self._get_shift_helper(
                        str(other_user_id), date_obj, year, month)

                    if current_shift_for_other:
                        assignments_today.append({'id': other_user_id, 'shift': current_shift_for_other})

            # Finde alle User (mit diesem Hund), die *vorher* oder *nachher* betroffen sind/waren
            involved_user_ids_now = {a['id'] for a in assignments_today}
            involved_user_ids_before = set(involved_user_ids_now)

            if old_shift and not new_shift and user_id not in involved_user_ids_now and old_dog == current_dog:
                involved_user_ids_before.add(user_id)

            all_potentially_involved = involved_user_ids_now.union(involved_user_ids_before)

            print(
                f"    Hund '{current_dog}' T{day}. Beteiligte (Vorher/Nachher): {all_potentially_involved}. Aktuelle Assignments: {assignments_today}")

            print(f"    -> Entferne alte Konflikte für Hund '{current_dog}' T{day}...")
            for uid_involved in all_potentially_involved:
                remove_violation(uid_involved, day)

            print(f"    -> Prüfe neue Konflikte für Hund '{current_dog}' T{day}...")
            if len(assignments_today) > 1:
                for i in range(len(assignments_today)):
                    for j in range(i + 1, len(assignments_today)):
                        u1 = assignments_today[i];
                        u2 = assignments_today[j]
                        if self._check_time_overlap_optimized(u1['shift'], u2['shift']):
                            print(f"      -> Konflikt: {u1['id']}({u1['shift']}) vs {u2['id']}({u2['shift']})")
                            add_violation(u1['id'], day);
                            add_violation(u2['id'], day)

        print(f"[DM/Violation-Incr] Update abgeschlossen. Betroffene Zellen: {affected_cells}")
        return affected_cells