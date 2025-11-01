# gui/shift_plan_styler.py
import tkinter as tk
from datetime import date


class ShiftPlanStyler:
    """
    Verantwortlich für die gesamte Farb- und Stil-Logik des Dienstplangrids.
    Diese Klasse liest Daten aus dem DataManager und der App-Konfiguration (Rules),
    um die korrekten Farben für Zellen, Rahmen und Text zu bestimmen.
    """

    def __init__(self, app, data_manager):
        self.app = app
        self.dm = data_manager
        self.rules = self.app.staffing_rules.get('Colors', {})

        # Häufig verwendete Farben aus den Rules cachen
        self.weekend_bg = self.rules.get('weekend_bg', "#EAF4FF")
        self.holiday_bg = self.rules.get('holiday_bg', "#FFD700")
        self.pending_color = self.rules.get('Ausstehend', 'orange')
        self.admin_pending_color = self.rules.get('Admin_Ausstehend', '#E0B0FF')
        self.violation_bg = self.rules.get('violation_bg', "#FF5555")
        self.summary_bg = "#D0D0FF"
        self.prev_month_bg = "#F0F0F0"  # Standard-Hintergrund für Vormonat (leicht grau)

    def apply_prev_month_cell_color(self, user_id, date_obj, frame, label, display_text_no_lock):
        """Wendet Farbe auf die Übertrags-Zelle ("Ü") an."""
        user_id_str = str(user_id)
        is_weekend = date_obj.weekday() >= 5
        is_holiday = self.app.is_holiday(date_obj)
        date_str = date_obj.strftime('%Y-%m-%d')

        shift_abbrev = display_text_no_lock.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF",
                                                                                                                 "X")
        shift_data = self.app.shift_types_data.get(shift_abbrev)

        # Vormonats-Daten nutzen
        vacation_status = self.dm.processed_vacations_prev.get(user_id_str, {}).get(date_obj)
        request_info = self.dm.wunschfrei_data_prev.get(user_id_str, {}).get(date_str)

        bg_color = self.prev_month_bg
        if is_holiday:
            bg_color = self.holiday_bg
        elif is_weekend:
            bg_color = self.weekend_bg

        if shift_data and shift_data.get('color'):
            if shift_abbrev in ["U", "X", "EU"]:
                bg_color = shift_data['color']
            elif not is_holiday and not is_weekend:
                bg_color = shift_data['color']

        if display_text_no_lock == "U?":
            bg_color = self.pending_color
        elif request_info and request_info[0] == 'Ausstehend':
            if "?" in display_text_no_lock or display_text_no_lock == "WF":
                bg_color = self.admin_pending_color if request_info[2] == 'admin' else self.pending_color

        # Keine Konfliktprüfung (is_violation) für Vormonat
        fg_color = self.app.get_contrast_color(bg_color)
        frame_border_color = "#AAAAAA"
        frame_border_width = 1  # Grauer Rand

        if display_text_no_lock == "U?":
            frame_border_color = "orange"
            frame_border_width = 2
        elif request_info and request_info[0] == 'Ausstehend' and (
                "?" in display_text_no_lock or display_text_no_lock == "WF"):
            frame_border_color = "purple" if request_info[2] == 'admin' else "orange"
            frame_border_width = 2

        if label.winfo_exists():
            label.config(bg=bg_color, fg=fg_color, font=("Segoe UI", 10, "italic"))  # Sicherstellen, dass es kursiv ist
        if frame.winfo_exists():
            frame.config(bg=frame_border_color, bd=frame_border_width)

    def apply_cell_color(self, user_id, day, date_obj, frame, label, final_display_text_no_lock):
        """Wendet Farbe auf eine einzelne Zelle an, basierend auf dem finalen Text *ohne* Lock-Symbol."""
        user_id_str = str(user_id)
        is_weekend = date_obj.weekday() >= 5
        is_holiday = self.app.is_holiday(date_obj)
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
            bg_color = self.holiday_bg
        elif is_weekend:
            bg_color = self.weekend_bg

        # Schichtfarbe nur anwenden, wenn vorhanden und passend
        if shift_data and shift_data.get('color'):
            if shift_abbrev in ["U", "X", "EU"]:
                bg_color = shift_data['color']  # Immer Schichtfarbe
            elif not is_holiday and not is_weekend:
                bg_color = shift_data['color']  # Nur an normalen Tagen

        # Statusfarben überschreiben (falls relevant für den finalen Text *ohne* Lock)
        if final_display_text_no_lock == "U?":
            bg_color = self.pending_color  # Urlaub ausstehend
        elif request_info and request_info[0] == 'Ausstehend':  # Wunsch ausstehend
            # Prüfe, ob der finale Text *ohne Lock* die Anfrage anzeigt
            if "?" in final_display_text_no_lock or final_display_text_no_lock == "WF":
                bg_color = self.admin_pending_color if request_info[2] == 'admin' else self.pending_color

        # Konfliktprüfung
        is_violation = (user_id, day) in self.dm.violation_cells
        fg_color = self.app.get_contrast_color(bg_color)
        frame_border_color = "black"
        frame_border_width = 1

        if is_violation:
            bg_color = self.violation_bg
            fg_color = "white"
            frame_border_color = "darkred"
            frame_border_width = 2
        # Rahmen nur für *sichtbare* ausstehende Anträge (prüfe Text *ohne Lock*)
        elif final_display_text_no_lock == "U?":
            frame_border_color = "orange"
            frame_border_width = 2
        elif request_info and request_info[0] == 'Ausstehend' and (
                "?" in final_display_text_no_lock or final_display_text_no_lock == "WF"):
            frame_border_color = "purple" if request_info[2] == 'admin' else "orange"
            frame_border_width = 2

        # Stelle sicher, dass Widgets noch existieren
        if label.winfo_exists():
            label.config(bg=bg_color, fg=fg_color)
        if frame.winfo_exists():
            frame.config(bg=frame_border_color, bd=frame_border_width)

    def apply_daily_count_color(self, abbrev, day, date_obj, label, count, min_req):
        """Wendet Farbe auf ein einzelnes Tageszählungs-Label an."""
        is_friday = date_obj.weekday() == 4
        is_holiday = self.app.is_holiday(date_obj)
        is_weekend = date_obj.weekday() >= 5

        bg = self.summary_bg
        border_width = 1

        if not (abbrev == "6" and (not is_friday or is_holiday)):
            if is_holiday:
                bg = self.holiday_bg
            elif is_weekend:
                bg = self.weekend_bg

        if abbrev == "6" and (not is_friday or is_holiday):
            border_width = 0
        elif min_req is not None and min_req > 0:
            if count < min_req:
                bg = self.rules.get('alert_bg', "#FF5555")
            elif count > min_req and self.rules.get('overstaffed_bg'):
                bg = self.rules.get('overstaffed_bg', "#FFFF99")
            elif count == min_req and self.rules.get('success_bg'):
                bg = self.rules.get('success_bg', "#90EE90")

        if label.winfo_exists():
            label.config(bg=bg, fg=self.app.get_contrast_color(bg), bd=border_width)