# gui/shift_plan_calculator.py
from datetime import date, datetime, timedelta
import calendar


class ShiftPlanCalculator:
    """
    Verantwortlich für alle Berechnungen im Zusammenhang mit dem Dienstplan,
    wie z.B. die Ermittlung von Gesamtstunden oder Mindestbesetzung.
    Liest Daten aus dem DataManager und der App-Konfiguration.
    """

    def __init__(self, app, data_manager):
        self.app = app
        self.dm = data_manager  # Referenz auf den DataManager, um Caches zu lesen

    def _get_app_shift_types(self):
        """Hilfsfunktion, um shift_types_data sicher vom Bootloader (app.app) oder der App (app) zu holen."""
        if hasattr(self.app, 'shift_types_data'):
            return self.app.shift_types_data
        if hasattr(self.app, 'app') and hasattr(self.app.app, 'shift_types_data'):
            return self.app.app.shift_types_data
        print("[WARNUNG] shift_types_data weder in app noch in app.app gefunden (Calculator).")
        return {}

    # --- KORREKTUR: Entferne die fehlerhafte, duplizierte _get_shift_helper ---
    # def _get_shift_helper(self, user_id_str, date_obj):
    #    ... (FEHLERHAFTE IMPLEMENTIERUNG ENTFERNT) ...
    # --- ENDE KORREKTUR ---

    def get_min_staffing_for_date(self, current_date):
        """ Ermittelt die Mindestbesetzungsregeln für ein spezifisches Datum. """
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
        total_hours = 0.0;
        try:
            user_id_int = int(user_id_str)
        except ValueError:
            print(f"[WARNUNG] Ungültige user_id_str in calculate_total_hours: {user_id_str}");
            return 0.0

        try:
            days_in_month = calendar.monthrange(year, month)[1]
        except ValueError:
            print(f"[FEHLER] Ungültiges Datum in calculate_total_hours: Y={year} M={month}")
            return 0.0

        shift_types_data = self._get_app_shift_types()

        # Überstunden vom Vormonat (N.)
        prev_month_last_day = date(year, month, 1) - timedelta(days=1)

        # --- KORREKTUR: Rufe die ZENTRALE Funktion im DataManager auf ---
        prev_shift = self.dm._get_shift_helper(user_id_str, prev_month_last_day, year, month)

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
        # Greife auf die Caches im DataManager zu
        user_shifts_this_month = self.dm.shift_schedule_data.get(user_id_str, {})
        processed_vacations_user = self.dm.processed_vacations.get(user_id_str, {})
        wunschfrei_data_user = self.dm.wunschfrei_data.get(user_id_str, {})

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')

            # --- KORREKTUR: Rufe die ZENTRALE Funktion im DataManager auf ---
            # (Diese Funktion prüft user_shifts_this_month selbst, aber zur Sicherheit
            # greifen wir hier direkt auf den Monats-Cache zu, WENN der DM-Helper
            # auch den Vormonat prüft, was er beim Stunden zählen nicht tun soll.
            # WARTEN...
            # Nein, der Bug war, dass _get_shift_helper im Calculator
            # NICHT den 'shift_schedule_data' Cache verwendet hat, sondern
            # die Caches (prev_month etc.) direkt abgefragt hat.

            # Die Original-Stundenberechnung (die funktioniert hat) hat
            # die Schichten DIREKT aus den Caches 'shift_schedule_data',
            # 'processed_vacations' etc. gelesen, OHNE _get_shift_helper.

            # Wir behalten die Original-Logik der Stundenberechnung bei,
            # die direkt auf die Caches zugreift, aber stellen sicher,
            # dass der _get_shift_helper (der nur für den Vormonatstag
            # gebraucht wird) auf den DM zeigt.

            shift = user_shifts_this_month.get(date_str, "");  # <- Diese Zeile ist korrekt

            vacation_status = processed_vacations_user.get(current_date)
            request_info = wunschfrei_data_user.get(date_str)

            actual_shift_for_hours = shift
            if vacation_status == 'Genehmigt':
                actual_shift_for_hours = 'U'
            elif request_info and request_info[1] == 'WF' and request_info[0] in ["Genehmigt", "Akzeptiert"]:
                actual_shift_for_hours = 'X'

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