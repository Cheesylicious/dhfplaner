# gui/shift_plan_data_manager.py
from datetime import date, datetime, timedelta
import calendar
from collections import defaultdict

# DB Imports - Nur die konsolidierte Funktion importieren
from database.db_shifts import get_consolidated_month_data


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
        self.violation_cells = set()

        # Cache für Vormonats-Shifts (Performance-Optimierung)
        self._prev_month_shifts = {}
        self._prev_month_shifts_month = (0, 0)

        # NEU: Cache für vorverarbeitete Schichtzeiten zur schnelleren Konfliktprüfung
        self._preprocessed_shift_times = {}

    def load_and_process_data(self, year, month, progress_callback=None):
        """
        Führt den konsolidierten DB-Abruf im Worker-Thread durch.
        """

        def update_progress(value, text):
            if progress_callback:
                progress_callback(value, text)

        # --- 1. Konsolidierter DB-Abruf (Reduzierung der Round-Trips) ---
        update_progress(10, "Lade alle Monatsdaten in einem Durchgang (DB-Optimierung)...")
        consolidated_data = get_consolidated_month_data(year, month)

        if consolidated_data is None:
            raise Exception("Fehler beim Abrufen der konsolidierten Daten.")

        update_progress(60, "Verarbeite Schicht- und Antragsdaten...")

        # --- 2. Daten aus konsolidiertem Ergebnis in Caches füllen ---
        self.shift_schedule_data = consolidated_data['shifts']
        self.daily_counts = consolidated_data['daily_counts']
        self.wunschfrei_data = consolidated_data['wunschfrei_requests']
        self._prev_month_shifts = consolidated_data['prev_month_shifts']

        # Urlaubsdaten verarbeiten
        raw_vacations = consolidated_data['vacation_requests']
        self.processed_vacations = self._process_vacations(year, month, raw_vacations)

        # NEU: Schichtzeiten einmalig vorverarbeiten
        self._preprocess_shift_times()

        update_progress(80, "Prüfe Konflikte (Ruhezeit, Hunde) und Staffing...")

        # --- 3. Schwere Berechnungen / Konfliktprüfung ---
        self.update_violation_set(year, month)

        update_progress(95, "Vorbereitung abgeschlossen.")

        return self.shift_schedule_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts

    def _preprocess_shift_times(self):
        """
        Konvertiert alle Schichtzeiten einmalig in Minuten seit Mitternacht,
        um die Berechnung von Überschneidungen zu beschleunigen.
        """
        self._preprocessed_shift_times.clear()

        for abbrev, data in self.app.shift_types_data.items():
            start_time_str = data.get('start_time')
            end_time_str = data.get('end_time')

            if not start_time_str or not end_time_str:
                continue

            try:
                s = datetime.strptime(start_time_str, '%H:%M').time()
                e = datetime.strptime(end_time_str, '%H:%M').time()

                s_min = s.hour * 60 + s.minute
                e_min = e.hour * 60 + e.minute

                # Wenn die Endzeit vor der Startzeit liegt (über Mitternacht), 24h addieren
                if e_min <= s_min:
                    e_min += 24 * 60

                self._preprocessed_shift_times[abbrev] = (s_min, e_min)
            except ValueError:
                # Ungültiges Zeitformat, ignorieren
                continue

    def _process_vacations(self, year, month, raw_vacations):
        """Konvertiert Rohdaten der Urlaubsanträge in ein datumsbasiertes Dictionary."""
        # Nimmt die rohe Liste der Urlaubsanträge aus dem konsolidierten Abruf entgegen.
        processed = defaultdict(dict)
        for req in raw_vacations:
            user_id_str = str(req['user_id'])
            try:
                # WICHTIG: Urlaubsdaten müssen für den gesamten Zeitraum korrekt verarbeitet werden
                start = datetime.strptime(req['start_date'], '%Y-%m-%d').date()
                end = datetime.strptime(req['end_date'], '%Y-%m-%d').date()
                current_date = start
                while current_date <= end:
                    if current_date.year == year and current_date.month == month:
                        processed[user_id_str][current_date] = req['status']
                    current_date += timedelta(days=1)
            except (ValueError, TypeError):
                continue
        return dict(processed)

    def get_min_staffing_for_date(self, current_date):
        """Ermittelt die Mindestbesetzungsregel basierend auf Wochentag/Feiertag."""
        rules, min_staffing = self.app.staffing_rules, {}
        min_staffing.update(rules.get('Daily', {}))
        if self.app.is_holiday(current_date):
            min_staffing.update(rules.get('Holiday', {}))
        elif current_date.weekday() >= 5:
            min_staffing.update(rules.get('Sa-So', {}))
        elif current_date.weekday() == 4:
            min_staffing.update(rules.get('Fr', {}))
        else:
            min_staffing.update(rules.get('Mo-Do', {}))
        return {k: int(v) for k, v in min_staffing.items() if str(v).isdigit()}

    def calculate_total_hours_for_user(self, user_id_str, year, month):
        """Berechnet die Gesamtstunden für einen Benutzer in einem Monat (nutzt Cache)."""
        total_hours = 0
        days_in_month = calendar.monthrange(year, month)[1]
        prev_month_date = date(year, month, 1) - timedelta(days=1)

        # Nutze den gecachten Vormonats-Shift
        prev_month_last_day_str = prev_month_date.strftime('%Y-%m-%d')

        if self._prev_month_shifts.get(user_id_str, {}).get(prev_month_last_day_str) == 'N.':
            total_hours += 6

        user_shifts = self.shift_schedule_data.get(user_id_str, {})

        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            shift = user_shifts.get(date_str, "")
            if shift in self.app.shift_types_data:
                hours = self.app.shift_types_data[shift].get('hours', 0)
                # Nachtdienst-Sonderregel am Monatsende
                if shift == 'N.' and day == days_in_month:
                    hours = 6
                total_hours += hours
        return total_hours

    def update_violation_set(self, year, month):
        """Prüft auf Ruhezeit- und Diensthund-Konflikte und aktualisiert die Menge."""
        self.violation_cells.clear()
        days_in_month = calendar.monthrange(year, month)[1]
        current_user_order = self.app.current_shift_plan_users

        # 1. Ruhezeitverletzung (Nachtdienst)
        for user in current_user_order:
            user_id_str = str(user['id'])
            for day in range(1, days_in_month):
                date1 = date(year, month, day).strftime('%Y-%m-%d')
                date2 = date(year, month, day + 1).strftime('%Y-%m-%d')
                shift1 = self.shift_schedule_data.get(user_id_str, {}).get(date1, "")
                shift2 = self.shift_schedule_data.get(user_id_str, {}).get(date2, "")

                if shift1 == 'N.' and shift2 not in ['', 'FREI', 'N.', 'U', 'X', 'EU']:
                    self.violation_cells.add((user['id'], day))
                    self.violation_cells.add((user['id'], day + 1))

        # 2. Hundekonflikt
        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime('%Y-%m-%d')
            dog_schedule = defaultdict(list)

            for user in current_user_order:
                dog = user.get('diensthund')
                if dog and dog != '---':
                    shift = self.shift_schedule_data.get(str(user['id']), {}).get(date_str)
                    if shift:
                        dog_schedule[dog].append((user['id'], shift))

            for assignments in dog_schedule.values():
                if len(assignments) > 1:
                    for i in range(len(assignments)):
                        for j in range(i + 1, len(assignments)):
                            # NUTZT DEN VORVERARBEITETEN CACHE FÜR SCHNELLERE PRÜFUNG
                            if self._check_time_overlap_optimized(assignments[i][1], assignments[j][1]):
                                self.violation_cells.add((assignments[i][0], day))
                                self.violation_cells.add((assignments[j][0], day))

    def _check_time_overlap_optimized(self, shift1_abbrev, shift2_abbrev):
        """Prüft, ob sich zwei Schichten zeitmäßig überschneiden (Optimierte Version)."""

        # 1. Schnelle Prüfung auf Freischichten
        if shift1_abbrev in ['U', 'X', 'EU', 'WF', '', 'FREI'] or shift2_abbrev in ['U', 'X', 'EU', 'WF', '', 'FREI']:
            return False

        # 2. Abruf der vorverarbeiteten Zeiten (in Minuten)
        s1_min, e1_min = self._preprocessed_shift_times.get(shift1_abbrev, (None, None))
        s2_min, e2_min = self._preprocessed_shift_times.get(shift2_abbrev, (None, None))

        # Wenn eine der Schichten keine gültigen Zeiten hat, können wir nicht prüfen
        if s1_min is None or s2_min is None:
            return False

        # 3. Optimierte Überlappungsprüfung (Ausschlussprinzip)
        # Die Schichten überschneiden sich, wenn der Start der einen VOR dem Ende der anderen liegt
        # UND der Endpunkt der einen NACH dem Startpunkt der anderen liegt.
        return max(s1_min, s2_min) < min(e1_min, e2_min)