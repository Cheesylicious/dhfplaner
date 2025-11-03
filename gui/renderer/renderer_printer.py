# gui/renderer/renderer_printer.py
# NEU: Ausgelagerte Logik für die HTML-Druckfunktion (Regel 4)

import webbrowser
import os
import tempfile
from tkinter import messagebox
from datetime import date, timedelta


class RendererPrinter:
    """
    Verantwortlich für die Erstellung einer HTML-Druckansicht des Dienstplans.
    (Ausgelagert aus ShiftPlanRenderer nach Regel 4).
    """

    def __init__(self, renderer_instance):
        self.renderer = renderer_instance
        # Zugriff auf die Hauptkomponenten über die Renderer-Referenz
        self.app = self.renderer.app
        self.dm = self.renderer.dm
        self.master = self.renderer.master

    def print_shift_plan(self, year, month, month_name):
        """Erzeugt das HTML für den Druck und öffnet es im Browser."""

        # Greife auf die Daten zu, die der Renderer berechnet hat
        users = self.renderer.users_to_render
        if not users:
            messagebox.showinfo("Drucken", "Keine Benutzer zum Drucken vorhanden.", parent=self.master)
            return

        # Hole aktuelle Daten aus dem DM
        shifts_data = self.dm.shift_schedule_data
        wunschfrei_data = self.dm.wunschfrei_data
        processed_vacations = self.dm.processed_vacations

        # Vormonats-Daten (vom Renderer geladen)
        prev_month_last_day = date(year, month, 1) - timedelta(days=1)
        processed_vacations_prev = self.renderer.processed_vacations_prev
        wunschfrei_data_prev = self.renderer.wunschfrei_data_prev

        # Tagesdaten-Cache (vom Renderer/Styling-Helper)
        # Greife auf die Helfer-Instanz des Renderers zu
        styling_helper = self.renderer.styling_helper

        # Stelle sicher, dass der day_data_cache des Renderers gefüllt ist
        days_in_month = (date(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31
        if not self.renderer.day_data_cache or list(self.renderer.day_data_cache.keys())[-1] != days_in_month:
            print("[Renderer Print] Lade Tagesdaten neu für Druckansicht.")
            styling_helper._pre_calculate_day_data(year, month)

        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        violation_bg = rules.get('violation_bg', "#FF5555")  # Für Druck
        prev_month_bg = "#F0F0F0"  # (Leichtes Grau)

        html = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>Dienstplan {month_name}</title>
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
            <h1>Dienstplan für {month_name}</h1>
            <table>
                <thead>
                    <tr>
                        <th class="name-col">Name</th>
                        <th class="dog-col">Diensthund</th>
                        <th class="day-col">Ü</th>
        """

        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        for day in range(1, days_in_month + 1):
            day_data = styling_helper.get_day_data(day)  # Nutze Helfer

            day_class = "day-col"
            if day_data['is_holiday']:
                day_class += " holiday"
            elif day_data['is_weekend']:
                day_class += " weekend"
            html += f'<th class="{day_class}">{day}<br>{day_map[date(year, month, day).weekday()]}</th>'
        html += '<th class="hours-col">Std.</th></tr></thead><tbody>'

        for user in users:
            user_id_str = str(user['id'])
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, year, month)
            html += f"""
                <tr>
                    <td class="name-col">{user['vorname']} {user['name']}</td>
                    <td class="dog-col">{user.get('diensthund', '---')}</td>
            """

            # "Ü"-Zelle im Druck (nutze Helfer)
            prev_shift_display = styling_helper._get_display_text_for_prev_month(user_id_str, prev_month_last_day)
            if prev_shift_display == "": prev_shift_display = "&nbsp;"

            shift_abbrev_prev = prev_shift_display.replace("&nbsp;", "").replace("?", "").replace("(A)", "").replace(
                "T./N.", "T/N").replace("WF", "X")
            td_class_prev = "prev-month-col"
            bg_color_style_prev = ""

            # Farb-Logik für "Ü" (vereinfacht, basierend auf _apply_prev_month_cell_color)
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

            vacation_status_prev = processed_vacations_prev.get(user_id_str, {}).get(prev_month_last_day)
            request_info_prev = wunschfrei_data_prev.get(user_id_str, {}).get(
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
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                display_text_from_schedule = shifts_data.get(user_id_str, {}).get(date_str,
                                                                                  "&nbsp;")
                vacation_status = processed_vacations.get(user_id_str, {}).get(current_date)
                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)

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
                        lock_char_print = "&#128274;"

                text_with_lock_print = f"{lock_char_print}{final_display_text}".replace("&nbsp;", "").strip()
                if not text_with_lock_print: text_with_lock_print = "&nbsp;"

                shift_abbrev_for_style = final_display_text.replace("&nbsp;", "").replace("?", "").replace("(A)",
                                                                                                           "").replace(
                    "T./N.", "T/N").replace("WF", "X")

                day_data = styling_helper.get_day_data(day)

                td_class = "day-col";
                is_weekend = day_data['is_weekend']
                is_holiday = day_data['is_holiday']

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
                f.write(html);
                filepath = f.name
            webbrowser.open(f"file://{os.path.realpath(filepath)}")
            messagebox.showinfo("Drucken",
                                "Der Dienstplan wurde in deinem Webbrowser geöffnet.\n\n"
                                "Nutze dort die Druckfunktion (Strg+P).\n\n"
                                "Datei: " + filepath, parent=self.master)
        except Exception as e:
            messagebox.showerror("Fehler", f"Plan konnte nicht zum Drucken geöffnet werden:\n{e}", parent=self.master)