# gui/renderer/renderer_styling.py
# NEU: Ausgelagerte Logik für Farben, Stile und Caching (Regel 4)

import calendar
from datetime import date


class RendererStyling:
    """
    Verantwortlich für die Berechnung von Stilen, Farben und
    speziellen Texten (z.B. Vormonat) für den ShiftPlanRenderer.
    (Ausgelagert nach Regel 4).
    """

    def __init__(self, renderer_instance):
        self.renderer = renderer_instance
        # Zugriff auf die Hauptkomponenten über die Renderer-Referenz
        self.app = self.renderer.app
        self.dm = self.renderer.dm

        # Cache für Feiertage/Events, um redundante App-Aufrufe zu vermeiden
        # Dieser Cache wird vom Renderer (dem Besitzer dieser Klasse) verwaltet
        # self.day_data_cache = {} # VERALTET: Der Renderer selbst hält diesen Cache

    def _pre_calculate_day_data(self, year, month):
        """Berechnet und cached Feiertage und Events für jeden Tag des Monats.
        Dies verhindert Hunderte von redundanten Aufrufen im Render-Loop (Regel 2)."""
        # Der Cache wird im Haupt-Renderer gespeichert (self.renderer.day_data_cache)
        self.renderer.day_data_cache = {}
        days_in_month = calendar.monthrange(year, month)[1]
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            # Diese App-Aufrufe passieren jetzt nur einmal pro Tag
            self.renderer.day_data_cache[day] = {
                'is_holiday': self.app.is_holiday(current_date),
                'event_type': self.app.get_event_type(current_date),
                'is_weekend': current_date.weekday() >= 5
            }
        print(f"[Renderer/Styling] Vorbereiten der Tagesdaten für {year}-{month:02d} abgeschlossen.")

    def get_day_data(self, day):
        """Gibt die gecachten Daten für einen bestimmten Tag zurück."""
        # Greift auf den Cache im Haupt-Renderer zu
        return self.renderer.day_data_cache.get(day, {'is_holiday': False, 'event_type': None, 'is_weekend': False})

    def _get_display_text_for_prev_month(self, user_id_str, prev_date_obj):
        """Ermittelt den Anzeigetext für die Übertrags-Spalte."""
        prev_date_str = prev_date_obj.strftime('%Y-%m-%d')

        # 1. Rohe Schicht holen (aus Vormonats-Cache des DM)
        # Greift auf die Daten zu, die der Renderer im Haupt-Grid-Build geladen hat
        raw_shift = self.renderer.prev_month_shifts.get(user_id_str, {}).get(prev_date_str, "")

        # 2. Urlaubs- und Wunschdaten des Vormonats holen
        vacation_status = self.renderer.processed_vacations_prev.get(user_id_str, {}).get(prev_date_obj)
        request_info = self.renderer.wunschfrei_data_prev.get(user_id_str, {}).get(prev_date_str)

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

        return final_display_text

    def _apply_prev_month_cell_color(self, user_id, date_obj, frame, label, display_text_no_lock):
        """Wendet Farbe auf die Übertrags-Zelle an."""
        user_id_str = str(user_id)
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF");
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        pending_color = rules.get('Ausstehend', 'orange');
        admin_pending_color = rules.get('Admin_Ausstehend', '#E0B0FF')

        is_weekend = date_obj.weekday() >= 5;
        is_holiday = self.app.is_holiday(
            date_obj)  # Bleibt: Nutzt App, da es Vormonatsdaten sind, die nicht im Cache sind
        date_str = date_obj.strftime('%Y-%m-%d')

        shift_abbrev = display_text_no_lock.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF",
                                                                                                                 "X")
        shift_data = self.app.shift_types_data.get(shift_abbrev)

        # Vormonats-Daten nutzen (aus dem Renderer-Speicher)
        vacation_status = self.renderer.processed_vacations_prev.get(user_id_str, {}).get(date_obj)
        request_info = self.renderer.wunschfrei_data_prev.get(user_id_str, {}).get(date_str)

        bg_color = "#F0F0F0"  # Standard-Hintergrund für Vormonat (leicht grau)
        if is_holiday:
            bg_color = holiday_bg
        elif is_weekend:
            bg_color = weekend_bg

        if shift_data and shift_data.get('color'):
            if shift_abbrev in ["U", "X", "EU"]:
                bg_color = shift_data['color']
            elif not is_holiday and not is_weekend:
                bg_color = shift_data['color']

        if display_text_no_lock == "U?":
            bg_color = pending_color
        elif request_info and request_info[0] == 'Ausstehend':
            if "?" in display_text_no_lock or display_text_no_lock == "WF":
                bg_color = admin_pending_color if request_info[2] == 'admin' else pending_color

        # Keine Konfliktprüfung (is_violation) für Vormonat
        fg_color = self.app.get_contrast_color(bg_color)
        frame_border_color = "#AAAAAA";
        frame_border_width = 1  # Grauer Rand

        if display_text_no_lock == "U?":
            frame_border_color = "orange";
            frame_border_width = 2
        elif request_info and request_info[0] == 'Ausstehend' and (
                "?" in display_text_no_lock or display_text_no_lock == "WF"):
            frame_border_color = "purple" if request_info[2] == 'admin' else "orange";
            frame_border_width = 2

        if label.winfo_exists(): label.config(bg=bg_color, fg=fg_color,
                                              font=("Segoe UI", 10, "italic"))  # Sicherstellen, dass es kursiv ist
        if frame.winfo_exists(): frame.config(bg=frame_border_color, bd=frame_border_width)

    def apply_cell_color(self, user_id, day, date_obj, frame, label, final_display_text_no_lock):
        """Wendet Farbe auf eine einzelne Zelle an, basierend auf dem finalen Text *ohne* Lock-Symbol."""
        user_id_str = str(user_id)
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF");
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        pending_color = rules.get('Ausstehend', 'orange');
        admin_pending_color = rules.get('Admin_Ausstehend', '#E0B0FF')

        # --- KORREKTUR (Regel 2): Nutze den Cache ---
        day_data = self.get_day_data(day)
        is_weekend = day_data['is_weekend']
        is_holiday = day_data['is_holiday']
        # --- ENDE KORREKTUR ---

        date_str = date_obj.strftime('%Y-%m-%d')

        # Normalisiere den Text *ohne Lock* für Schicht-Lookup und Farbfindung
        shift_abbrev = final_display_text_no_lock.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace(
            "WF", "X")

        shift_data = self.app.shift_types_data.get(shift_abbrev)
        # Statusinformationen aus DM holen (für Rahmen etc.)
        vacation_status = self.dm.processed_vacations.get(user_id_str, {}).get(date_obj)
        request_info = self.dm.wunschfrei_data.get(user_id_str, {}).get(date_str)

        # --- Farb-Logik ---
        bg_color = "white"  # Standard-Hintergrund
        if is_holiday:
            bg_color = holiday_bg
        elif is_weekend:
            bg_color = weekend_bg

        # Schichtfarbe nur anwenden, wenn vorhanden und passend
        if shift_data and shift_data.get('color'):
            if shift_abbrev in ["U", "X", "EU"]:
                bg_color = shift_data['color']  # Immer Schichtfarbe
            elif not is_holiday and not is_weekend:
                bg_color = shift_data['color']  # Nur an normalen Tagen

        # Statusfarben überschreiben (falls relevant für den finalen Text *ohne* Lock)
        if final_display_text_no_lock == "U?":
            bg_color = pending_color  # Urlaub ausstehend
        elif request_info and request_info[0] == 'Ausstehend':  # Wunsch ausstehend
            # Prüfe, ob der finale Text *ohne Lock* die Anfrage anzeigt
            if "?" in final_display_text_no_lock or final_display_text_no_lock == "WF":
                bg_color = admin_pending_color if request_info[2] == 'admin' else pending_color

        # Konfliktprüfung
        is_violation = (user_id, day) in self.dm.violation_cells
        fg_color = self.app.get_contrast_color(bg_color)
        frame_border_color = "black";
        frame_border_width = 1

        if is_violation:
            bg_color = rules.get('violation_bg', "#FF5555")
            fg_color = "white"
            frame_border_color = "darkred";
            frame_border_width = 2
        # Rahmen nur für *sichtbare* ausstehende Anträge (prüfe Text *ohne Lock*)
        elif final_display_text_no_lock == "U?":
            frame_border_color = "orange";
            frame_border_width = 2
        elif request_info and request_info[0] == 'Ausstehend' and (
                "?" in final_display_text_no_lock or final_display_text_no_lock == "WF"):
            frame_border_color = "purple" if request_info[2] == 'admin' else "orange";
            frame_border_width = 2

        # Stelle sicher, dass Widgets noch existieren
        if label.winfo_exists(): label.config(bg=bg_color, fg=fg_color)
        if frame.winfo_exists(): frame.config(bg=frame_border_color, bd=frame_border_width)

    def apply_daily_count_color(self, abbrev, day, date_obj, label, count, min_req):
        """Wendet Farbe auf ein einzelnes Tageszählungs-Label an."""
        # (Diese Funktion nutzt nun den Cache)
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF");
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        summary_bg = "#D0D0FF"
        is_friday = date_obj.weekday() == 4;

        # --- KORREKTUR (Regel 2): Nutze den Cache ---
        day_data = self.get_day_data(day)
        is_holiday = day_data['is_holiday']
        is_weekend = day_data['is_weekend']
        # --- ENDE KORREKTUR ---

        bg = summary_bg;
        border_width = 1
        if not (abbrev == "6" and (not is_friday or is_holiday)):
            if is_holiday:
                bg = holiday_bg
            elif is_weekend:
                bg = weekend_bg
        if abbrev == "6" and (not is_friday or is_holiday):
            border_width = 0
        elif min_req is not None and min_req > 0:
            if count < min_req:
                bg = rules.get('alert_bg', "#FF5555")
            elif count > min_req and rules.get('overstaffed_bg'):
                bg = rules.get('overstaffed_bg', "#FFFF99")
            elif count == min_req and rules.get('success_bg'):
                bg = rules.get('success_bg', "#90EE90")
        if label.winfo_exists(): label.config(bg=bg, fg=self.app.get_contrast_color(bg), bd=border_width)