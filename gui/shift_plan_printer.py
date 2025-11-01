# gui/shift_plan_printer.py
import tkinter as tk
from tkinter import messagebox
from datetime import date, datetime, timedelta
import calendar
import webbrowser
import os
import tempfile

class ShiftPlanPrinter:
    """
    Verantwortlich für die Erstellung einer HTML-Version des Dienstplans
    zum Drucken im Webbrowser.
    """

    def __init__(self, master, app, data_manager, users_to_render, year, month, month_name):
        self.master = master
        self.app = app
        self.dm = data_manager
        self.users = users_to_render  # Die Liste der zu rendernden Benutzer
        self.year = year
        self.month = month
        self.month_name = month_name

        # Hole relevante Daten-Caches direkt vom DataManager
        self.shifts_data = getattr(self.dm, 'shift_schedule_data', {})
        self.processed_vacations = getattr(self.dm, 'processed_vacations', {})
        self.wunschfrei_data = getattr(self.dm, 'wunschfrei_data', {})

        # Hole Vormonats-Daten (wird für "Ü"-Spalte benötigt)
        # HINWEIS: get_previous_month_shifts() stellt sicher, dass die Daten geladen sind,
        # wenn sie nicht bereits im Cache (processed_vacations_prev etc.) sind.
        self.prev_month_shifts = self.dm.get_previous_month_shifts()
        self.processed_vacations_prev = getattr(self.dm, 'processed_vacations_prev', {})
        self.wunschfrei_data_prev = getattr(self.dm, 'processed_vacations_prev', {})

    def _get_display_text_for_prev_month(self, user_id_str, prev_date_obj):
        """
        Ermittelt den Anzeigetext für die Übertrags-Spalte.
        (Kopiert von ShiftPlanRenderer, da hier dieselbe Logik benötigt wird)
        """
        prev_date_str = prev_date_obj.strftime('%Y-%m-%d')

        # 1. Rohe Schicht holen (aus Vormonats-Cache des DM)
        raw_shift = self.prev_month_shifts.get(user_id_str, {}).get(prev_date_str, "")

        # 2. Urlaubs- und Wunschdaten des Vormonats holen
        vacation_status = self.processed_vacations_prev.get(user_id_str, {}).get(prev_date_obj)
        request_info = self.wunschfrei_data_prev.get(user_id_str, {}).get(prev_date_str)

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

    def generate_and_open_html(self):
        """Erzeugt das HTML für den Druck und öffnet es im Browser."""
        # (Dies ist die verschobene Methode print_shift_plan)
        if not self.users:
            messagebox.showinfo("Drucken", "Keine Benutzer zum Drucken vorhanden.", parent=self.master)
            return

        # Hole Vormonats-Datum
        prev_month_last_day = date(self.year, self.month, 1) - timedelta(days=1)

        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        violation_bg = rules.get('violation_bg', "#FF5555")
        prev_month_bg = "#F0F0F0"

        html = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>Dienstplan {self.month_name}</title>
            <style>
                body {{ font-family: Segoe UI, Arial, sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; font-size: 11px; table-layout: fixed; }}
                th, td {{ border: 1px solid #ccc; padding: 4px; text-align: center; overflow: hidden; white-space: nowrap; }}
                th {{ background-color: #E0E0E0; font-weight: bold; }}
                .weekend {{ background-color: {weekend_bg}; }}
                .holiday {{ background-color: {holiday_bg}; }}
                .violation {{ background-color: {violation_bg}; color: white; }}
                .prev-month-col {{ background-color: {prev_month_bg}; font-style: italic; color: #555; width: 35px; }}
                .name-col {{ text-align: left; font-weight: bold; width: 140px; }}
                .dog-col {{ text-align: left; width: 90px; }}
                .day-col {{ width: 35px; }}
                .hours-col {{ font-weight: bold; width: 40px; }}
        """
        for abbrev, data in self.app.shift_types_data.items():
            if data.get('color'):
                fg = self.app.get_contrast_color(data['color'])
                html += f" .shift-{abbrev} {{ background-color: {data['color']}; color: {fg}; }}\n"
        html += """
            </style>
        </head>
        <body>
            <h1>Dienstplan für {self.month_name}</h1>
            <table>
                <thead>
                    <tr>
                        <th class="name-col">Name</th>
                        <th class="dog-col">Diensthund</th>
                        <th class="day-col">Ü</th>
        """
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        for day in range(1, days_in_month + 1):
            current_date = date(self.year, self.month, day)
            day_class = "day-col"
            if self.app.is_holiday(current_date):
                day_class += " holiday"
            elif current_date.weekday() >= 5:
                day_class += " weekend"
            html += f'<th class="{day_class}">{day}<br>{day_map[current_date.weekday()]}</th>'
        html += '<th class="hours-col">Std.</th></tr></thead><tbody>'

        for user in self.users:
            user_id_str = str(user['id'])
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, self.year, self.month)
            html += f"""
                <tr>
                    <td class="name-col">{user['vorname']} {user['name']}</td>
                    <td class="dog-col">{user.get('diensthund', '---')}</td>
            """

            # "Ü"-Zelle im Druck
            prev_shift_display = self._get_display_text_for_prev_month(user_id_str, prev_month_last_day)
            if prev_shift_display == "": prev_shift_display = "&nbsp;"

            shift_abbrev_prev = prev_shift_display.replace("&nbsp;", "").replace("?", "").replace("(A)", "").replace(
                "T./N.", "T/N").replace("WF", "X")
            td_class_prev = "prev-month-col"
            bg_color_style_prev = ""

            bg_color_prev = ""
            is_holiday_prev = self.app.is_holiday(prev_month_last_day)
            is_weekend_prev = prev_month_last_day.weekday() >= 5

            if is_holiday_prev:
                bg_color_prev = holiday_bg
            elif is_weekend_prev:
                bg_color_prev = weekend_bg

            shift_data_prev = self.app.shift_types_data.get(shift_abbrev_prev)
            if shift_data_prev and shift_data_prev.get('color'):
                if shift_abbrev_prev in ["U", "X", "EU"]:
                    bg_color_prev = shift_data_prev['color']
                elif not is_holiday_prev and not is_weekend_prev:
                    bg_color_prev = shift_data_prev['color']

            vacation_status_prev = self.processed_vacations_prev.get(user_id_str, {}).get(prev_month_last_day)
            request_info_prev = self.wunschfrei_data_prev.get(user_id_str, {}).get(
                prev_month_last_day.strftime('%Y-%m-%d'))

            if prev_shift_display == "U?":
                bg_color_prev = rules.get('Ausstehend', 'orange')
            elif request_info_prev and request_info_prev[0] == 'Ausstehend' and (
                    "?" in prev_shift_display or prev_shift_display == "WF"):
                bg_color_prev = rules.get('Admin_Ausstehend', '#E0B0FF') if request_info_prev[
                                                                                2] == 'admin' else rules.get(
                    'Ausstehend', 'orange')

            if bg_color_prev:
                fg_color_prev = self.app.get_contrast_color(bg_color_prev)
                bg_color_style_prev = f' style="background-color: {bg_color_prev}; color: {fg_color_prev}; font-style: italic;"'

            if not bg_color_prev and shift_abbrev_prev in self.app.shift_types_data:
                td_class_prev += f" shift-{shift_abbrev_prev}"

            html += f'<td class="{td_class_prev}"{bg_color_style_prev}>{prev_shift_display}</td>'

            # Tageszellen
            for day in range(1, days_in_month + 1):
                current_date = date(self.year, self.month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                display_text_from_schedule = self.shifts_data.get(user_id_str, {}).get(date_str, "&nbsp;")
                vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date)
                request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)

                final_display_text = display_text_from_schedule
                if vacation_status == 'Genehmigt':
                    final_display_text = 'U'
                elif vacation_status == 'Ausstehend':
                    final_display_text = "U?"
                elif request_info:
                    status, requested_shift, requested_by, _ = request_info
                    if status == 'Ausstehend':
                        if requested_by == 'admin':
                            final_display_text = f"{requested_shift}(A)?"
                        else:
                            if requested_shift == 'WF':
                                final_display_text = 'WF'
                            elif requested_shift == 'T/N':
                                final_display_text = 'T/N?'
                            else:
                                final_display_text = f"{requested_shift}?"
                    elif (
                            "Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and display_text_from_schedule == "&nbsp;":
                        final_display_text = 'X'

                lock_char_print = ""
                if hasattr(self.dm, 'shift_lock_manager'):
                    lock_status_print = self.dm.shift_lock_manager.get_lock_status(user_id_str, date_str)
                    if lock_status_print is not None:
                        lock_char_print = "&#128274;"  # HTML-Code für Schloss
                text_with_lock_print = f"{lock_char_print}{final_display_text}".replace("&nbsp;", "").strip()
                if not text_with_lock_print: text_with_lock_print = "&nbsp;"

                shift_abbrev_for_style = final_display_text.replace("&nbsp;", "").replace("?", "").replace("(A)",
                                                                                                           "").replace(
                    "T./N.", "T/N").replace("WF", "X")
                td_class = "day-col"
                is_weekend = current_date.weekday() >= 5
                is_holiday = self.app.is_holiday(current_date)
                is_violation = (user['id'], day) in self.dm.violation_cells

                bg_color_style = ""
                if is_violation:
                    td_class += " violation"
                else:
                    bg_color = ""
                    if is_holiday:
                        bg_color = holiday_bg
                    elif is_weekend:
                        bg_color = weekend_bg
                    shift_data = self.app.shift_types_data.get(shift_abbrev_for_style)
                    if shift_data and shift_data.get('color'):
                        if shift_abbrev_for_style in ["U", "X", "EU"]:
                            bg_color = shift_data['color']
                        elif not is_holiday and not is_weekend:
                            bg_color = shift_data['color']
                    if final_display_text == "U?":
                        bg_color = rules.get('Ausstehend', 'orange')
                    elif request_info and request_info[0] == 'Ausstehend' and (
                            "?" in final_display_text or final_display_text == "WF"):
                        bg_color = rules.get('Admin_Ausstehend', '#E0B0FF') if request_info[
                                                                                   2] == 'admin' else rules.get(
                            'Ausstehend', 'orange')
                    if bg_color:
                        fg_color = self.app.get_contrast_color(bg_color)
                        bg_color_style = f' style="background-color: {bg_color}; color: {fg_color};"'
                    if not bg_color_style and shift_abbrev_for_style in self.app.shift_types_data:
                        td_class += f" shift-{shift_abbrev_for_style}"
                html += f'<td class="{td_class}"{bg_color_style}>{text_with_lock_print}</td>'
            html += f'<td class="hours-col">{total_hours}</td></tr>'
        html += """</tbody></table></body></html>"""

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
                f.write(html)
                filepath = f.name
            webbrowser.open(f"file://{os.path.realpath(filepath)}")
            messagebox.showinfo("Drucken",
                                "Der Dienstplan wurde in deinem Webbrowser geöffnet.\n\n"
                                "Nutze dort die Druckfunktion (Strg+P).\n\n"
                                "Datei: " + filepath, parent=self.master)
        except Exception as e:
            messagebox.showerror("Fehler", f"Plan konnte nicht zum Drucken geöffnet werden:\n{e}", parent=self.master)