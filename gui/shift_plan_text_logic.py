# gui/shift_plan_text_logic.py
from datetime import date


class ShiftPlanTextLogic:
    """
    Diese Klasse kapselt die Logik zur Bestimmung des Anzeigetextes für
    eine beliebige Zelle im Dienstplan (inkl. "Ü"-Spalte und Lock-Symbol).
    Sie greift auf die Caches des DataManagers zu.
    """

    def __init__(self, data_manager):
        self.dm = data_manager

    def get_display_text_for_prev_month(self, user_id_str, prev_date_obj):
        """Ermittelt den Anzeigetext für die Übertrags-Spalte."""
        prev_date_str = prev_date_obj.strftime('%Y-%m-%d')

        # --- KORREKTUR START ---
        # Daten aus den Vormonats-Caches des DM holen
        # self.dm.prev_month_shifts existiert nicht.
        # Wir müssen die Methode get_previous_month_shifts() aufrufen,
        # die uns das Dictionary mit den Schichten zurückgibt.
        prev_month_shifts_data = self.dm.get_previous_month_shifts()
        raw_shift = prev_month_shifts_data.get(user_id_str, {}).get(prev_date_str, "")
        # --- KORREKTUR ENDE ---

        # Diese Caches werden durch get_previous_month_shifts() im DM gesetzt
        vacation_status = self.dm.processed_vacations_prev.get(user_id_str, {}).get(prev_date_obj)
        request_info = self.dm.wunschfrei_data_prev.get(user_id_str, {}).get(prev_date_str)

        final_display_text = raw_shift

        if vacation_status == 'Genehmigt':
            final_display_text = 'U'
        elif vacation_status == 'Ausstehend':
            final_display_text = "U?"
        elif request_info:
            status, requested_shift, requested_by, _ = request_info
            if status == 'Ausstehend':
                if requested_by == 'admin':
                    final_display_text = f"{requested_shift} (A)?"
                else:
                    if requested_shift == 'WF':
                        final_display_text = 'WF'
                    elif requested_shift == 'T/N':
                        final_display_text = 'T./N.?'
                    else:
                        final_display_text = f"{requested_shift}?"
            # Akzeptiertes Wunschfrei 'X' nur anzeigen, wenn *keine* andere Schicht eingetragen ist
            elif ("Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and not raw_shift:
                final_display_text = 'X'

        # "Ü"-Spalte benötigt kein Lock-Symbol, daher direkte Rückgabe
        return final_display_text

    def get_display_text_for_cell(self, user_id_str, date_obj):
        """
        Ermittelt den finalen Anzeigetext für eine Zelle im aktuellen Monat,
        inklusive des Lock-Symbols.

        Gibt ein Tupel zurück: (text_mit_lock, text_ohne_lock, request_info)
        """
        date_str = date_obj.strftime('%Y-%m-%d')

        # 1. Daten aus den aktuellen Caches des DM holen
        display_text_from_schedule = self.dm.shift_schedule_data.get(user_id_str, {}).get(date_str, "")
        vacation_status = self.dm.processed_vacations.get(user_id_str, {}).get(date_obj)
        request_info = self.dm.wunschfrei_data.get(user_id_str, {}).get(date_str)  # Holt Tupel oder None

        # 2. Logik zur Bestimmung des Textes *ohne* Lock
        final_display_text_no_lock = ""
        if display_text_from_schedule:
            final_display_text_no_lock = display_text_from_schedule

        if vacation_status == 'Genehmigt':
            final_display_text_no_lock = 'U'
        elif vacation_status == 'Ausstehend':
            final_display_text_no_lock = "U?"
        elif request_info:
            status, requested_shift, requested_by, _ = request_info
            if status == 'Ausstehend':
                if requested_by == 'admin':
                    final_display_text_no_lock = f"{requested_shift} (A)?"
                else:
                    if requested_shift == 'WF':
                        final_display_text_no_lock = 'WF'
                    elif requested_shift == 'T/N':
                        final_display_text_no_lock = 'T./N.?'
                    else:
                        final_display_text_no_lock = f"{requested_shift}?"
            elif (
                    "Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and not display_text_from_schedule:
                final_display_text_no_lock = 'X'

        # 3. Lock-Symbol hinzufügen
        lock_char = ""
        if hasattr(self.dm, 'shift_lock_manager'):
            lock_status = self.dm.shift_lock_manager.get_lock_status(user_id_str, date_str)
            if lock_status is not None:
                lock_char = "🔒"

        text_with_lock = f"{lock_char}{final_display_text_no_lock}".strip()

        return text_with_lock, final_display_text_no_lock, request_info