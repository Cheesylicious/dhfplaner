# gui/data_manager/dm_helpers.py
# NEU: Ausgelagerte Hilfsfunktionen für den DataManager (Regel 4)
# KORRIGIERT: Fügt die fehlende Methode calculate_user_shift_totals_from_db
# hinzu, die zur Initialisierung des Ist-Stunden-Caches benötigt wird.

from datetime import date, datetime, timedelta, time
import calendar
from collections import defaultdict
from database.db_core import load_config_json, save_config_json


class DataManagerHelpers:
    """
    Kapselt Hilfsfunktionen für den ShiftPlanDataManager,
    insbesondere für Berechnungen (Stunden, Mindestbesetzung)
    und die Verarbeitung von Anträgen.
    (Ausgelagert nach Regel 4).
    """

    GENERATOR_CONFIG_KEY = "GENERATOR_SETTINGS_V1"

    def __init__(self, data_manager):
        self.dm = data_manager
        self.app = data_manager.app  # Zugriff auf die Haupt-App

    def _get_app_shift_types(self):
        """Hilfsfunktion, um shift_types_data sicher vom Bootloader (app.app) oder der App (app) zu holen."""
        if hasattr(self.app, 'shift_types_data'):
            return self.app.shift_types_data
        if hasattr(self.app, 'app') and hasattr(self.app.app, 'shift_types_data'):
            return self.app.app.shift_types_data
        print("[WARNUNG] shift_types_data weder in app noch in app.app gefunden.")
        return {}

    # --- Generator Config Methoden ---
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

    # --- Datenverarbeitungs-Methoden ---

    def process_vacations(self, year, month, raw_vacations):
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

    # --- NEU: HINZUGEFÜGT FÜR DIE LADE-LOGIK (Fix für Attribute Error) ---
    def calculate_user_shift_totals_from_db(self, shift_data, user_data_map, shift_types_data):
        """
        Berechnet die Ist-Stunden-Totals für alle Benutzer im aktuellen Monat.
        (Wird im Worker-Thread ausgeführt und ist der langsame Schritt)
        """
        year = self.dm.year
        month = self.dm.month
        totals_cache = defaultdict(dict)

        # Iteriere über alle Benutzer im aktuellen Kontext
        for user_id_str in self.dm.user_data_map:
            # WICHTIG: Wir delegieren die komplexe Berechnung an die bereits existierende Funktion
            total_hours = self.calculate_total_hours_for_user(user_id_str, year, month)

            # Speichere die Ist-Stunden
            totals_cache[user_id_str]['hours_total'] = total_hours

            # Speichere die Schicht-Counts (grob, da die genaue Berechnung aufwendiger ist)
            # Die Ist-Stunden sind der kritische Wert für den Live-Update-Bug.
            totals_cache[user_id_str]['shifts_total'] = len(self.dm.shift_schedule_data.get(user_id_str, {}))

        return dict(totals_cache)

    # --- ENDE NEU ---

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

        # Greift auf den ViolationManager (vm) des DM zu für den Shift-Helper
        prev_shift = self.dm.vm._get_shift_helper(user_id_str, prev_month_last_day, year, month)

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

        # Stunden des aktuellen Monats (Zugriff auf DM-Caches)
        user_shifts_this_month = self.dm.shift_schedule_data.get(user_id_str, {})
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')
            shift = user_shifts_this_month.get(date_str, "");
            vacation_status = self.dm.processed_vacations.get(user_id_str, {}).get(current_date)
            request_info = self.dm.wunschfrei_data.get(user_id_str, {}).get(date_str)

            actual_shift_for_hours = shift
            if vacation_status == 'Genehmigt':
                actual_shift_for_hours = 'U'
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
                    hours -= hours_to_deduct

                total_hours += hours

        return round(total_hours, 2)