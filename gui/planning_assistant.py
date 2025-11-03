# gui/planning_assistant.py
# NEUE DATEI (Refactoring nach Regel 4 & Lösung für Regel 2)

from collections import defaultdict
from datetime import timedelta


# HINWEIS: Diese Klasse importiert KEINE DB-Funktionen.
# Sie arbeitet ausschließlich mit den gecachten Daten des DataManagers (Regel 2).

class PlanningAssistant:
    """
    Stellt Logik zur Validierung von manuellen Schicht-Einträgen
    in Echtzeit bereit (z.B. für Dropdown-Menüs oder Tastatur-Shortcuts).

    Diese Klasse nutzt AUSSCHLIESSLICH die gecachten Daten des
    ShiftPlanDataManager, um Datenbank-Latenzen (Regel 2) zu vermeiden.
    """

    def __init__(self, data_manager):
        """
        Initialisiert den Assistenten mit einer Referenz zum DataManager.

        Args:
            data_manager (ShiftPlanDataManager): Die Instanz, die alle Caches hält.
        """
        self.dm = data_manager
        self.app = data_manager.app  # Dies ist MainAdminWindow (aus ShiftPlanTab)

        # Zugriff auf die Helfer des DataManagers
        # vm (ViolationManager) und helpers (DataManagerHelpers)
        self.vm = self.dm.vm
        self.helpers = self.dm.helpers

        # Lade Schicht-Typ-Daten (Start/Endzeiten) aus dem App-Kontext
        try:
            # self.app ist MainAdminWindow, .app ist der Bootloader
            self.shift_types_data = self.app.app.shift_types_data
        except AttributeError:
            print("[PlanningAssistant] WARNUNG: shift_types_data nicht gefunden.")
            self.shift_types_data = {}

        # Indikatoren für "harte" Arbeitstage (relevant für Konsekutiv-Zählung)
        self.hard_work_indicators = {
            s for s, data in self.shift_types_data.items()
            if float(data.get('hours', 0.0)) > 0 and s not in ['U', 'EU']
        }
        self.hard_work_indicators.update(['T.', 'N.', '6', '24', 'QA', 'S'])
        self.free_shifts_indicators = {"", "FREI", "U", "X", "EU", "WF", "U?"}

    def _get_previous_raw_shift(self, user_id_str, check_date_obj, year, month):
        """
        Holt die *Roh*-Schicht (inkl. "FREI") vom Vortag aus dem Cache.
        (N->T/6 Prüfung)
        """
        check_date_str = check_date_obj.strftime('%Y-%m-%d')

        # 1. Prüfe, ob das Datum im Vormonat liegt
        if check_date_obj.month != month:
            shift = self.dm.get_previous_month_shifts().get(user_id_str, {}).get(check_date_str)
            return shift  # Gibt Schicht oder None zurück

        # 2. Wenn im aktuellen Monat, prüfe den Haupt-Cache
        shift = self.dm.shift_schedule_data.get(user_id_str, {}).get(check_date_str)
        return shift  # Gibt Schicht oder None zurück

    def _get_previous_work_shift(self, user_id_str, check_date_obj, year, month):
        """
        Holt die letzte *Arbeits*-Schicht (ignoriert "FREI") aus dem Cache.
        Nutzt den Helfer des ViolationManagers, der Vormonat/Cache korrekt prüft.
        """
        return self.vm._get_shift_helper(user_id_str, check_date_obj, year, month)

    def _count_consecutive_shifts(self, user_id_str, current_date_obj, year, month):
        """
        Zählt fortlaufende Arbeitstage (rückwärts) nur anhand des Caches.
        """
        count = 0
        current_check = current_date_obj - timedelta(days=1)

        while True:
            # Nutze den Roh-Shift-Helfer dieser Klasse
            shift = self._get_previous_raw_shift(user_id_str, current_check, year, month)

            if shift and shift in self.hard_work_indicators:
                count += 1
                current_check -= timedelta(days=1)
            else:
                break
        return count

    def get_conflicts_for_shift(self, user_id, date_obj, target_shift_abbrev):
        """
        Prüft eine potenzielle Schicht auf alle harten Konflikte (N->T, Hund, Max).
        Gibt eine Liste von Konflikt-Gründen zurück.
        Nutzt NUR CACHE-DATEN (Regel 2).
        """

        # 0. Initialisierung (Daten aus dem DM holen)
        year = self.dm.year
        month = self.dm.month

        if year == 0:  # DataManager wurde noch nie geladen
            return ["Datenmanager ist nicht initialisiert."]

        user_id_str = str(user_id)
        # Greife auf die user_data_map zu, die der DM jetzt lädt
        user_data = self.dm.user_data_map.get(user_id)
        if not user_data:
            return ["Benutzerdaten nicht gefunden."]

        user_dog = user_data.get('diensthund')

        conflicts = []

        # 1. (N->T/6) und (N->QA/S) Ruhezeitkonflikt
        prev_date_obj = date_obj - timedelta(days=1)
        prev_shift = self._get_previous_work_shift(user_id_str, prev_date_obj, year, month)

        if prev_shift == 'N.' and target_shift_abbrev in ["T.", "6", "QA", "S"]:
            conflicts.append("N->T/6/QA/S (Ruhezeit)")

        # 2. Hundekonflikt (Zeitliche Überlappung)
        if user_dog and user_dog != '---':
            date_str = date_obj.strftime('%Y-%m-%d')

            # Finde alle anderen User mit demselben Hund an diesem Tag
            for other_user_id, other_user_data in self.dm.user_data_map.items():
                if other_user_id == user_id:
                    continue  # Sich selbst ignorieren

                if other_user_data.get('diensthund') == user_dog:
                    # Hole die Schicht des *anderen* Users aus dem Cache
                    other_shift = self.dm.shift_schedule_data.get(str(other_user_id), {}).get(date_str)

                    if other_shift and other_shift not in self.free_shifts_indicators:
                        # Nutze den schnellen, optimierten Overlap-Check des VM
                        if self.vm._check_time_overlap_optimized(target_shift_abbrev, other_shift):
                            conflicts.append(
                                f"Hund (mit {other_user_data.get('username', 'ID ' + str(other_user_id))})")
                            break  # Ein Hundekonflikt reicht

        # 3. Max. Konsekutive Schichten (Hard Limit)
        # (Wir nutzen hier die HARD_MAX-Konstante, da dies eine harte Blockade ist)
        hard_max = 8  # Fallback-Wert
        try:
            # Versuche, die Einstellung aus dem Generator zu lesen, falls geladen
            # (app.app ist der Bootloader)
            if hasattr(self.app.app, 'shift_plan_generator') and self.app.app.shift_plan_generator:
                hard_max = self.app.app.shift_plan_generator.HARD_MAX_CONSECUTIVE_SHIFTS
        except AttributeError:
            pass  # Nutze Fallback

        consecutive_days = self._count_consecutive_shifts(user_id_str, date_obj, year, month)
        if consecutive_days >= hard_max:
            conflicts.append(f"Max. {hard_max} Tage in Folge")

        # 4. User-Ausschluss (z.B. "Plant nie T.")
        try:
            # Greife auf die (bereits geladene) Generator-Config zu
            user_pref = self.app.app.shift_plan_generator.user_preferences[user_id_str]
            if target_shift_abbrev in user_pref.get('shift_exclusions', []):
                conflicts.append(f"Persönl. Ausschluss")
        except (AttributeError, KeyError):
            # Fallback, wenn Generator (und damit Config) nicht initialisiert wurde
            pass

        return conflicts