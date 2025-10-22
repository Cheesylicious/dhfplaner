# gui/shift_plan_renderer.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
import calendar
import webbrowser
import os
import tempfile

from database.db_shifts import get_ordered_shift_abbrevs
from database.db_users import get_ordered_users_for_schedule


class ShiftPlanRenderer:
    """
    Verantwortlich für die Erstellung der visuellen Darstellung des Dienstplangrids
    und die Anwendung aller Farben/Stile.
    """

    def __init__(self, master, app, data_manager, action_handler):
        self.master = master  # Referenz auf den Tab (z.B. für messagebox)
        self.app = app
        self.dm = data_manager
        self.ah = action_handler  # Zur Übergabe an Klick-Events
        self.plan_grid_frame = None
        self.grid_widgets = {}  # Speichert Referenzen auf Grid-Elemente

        # KORREKTUR: Reduzierung der Chunk-Größe von 5 auf 1 für maximale visuelle Flüssigkeit
        self.current_user_row = 0
        self.ROW_CHUNK_SIZE = 1  # <-- ÄNDERUNG: Nur 1 Zeile pro Frame-Update

    def set_plan_grid_frame(self, frame):
        """Setzt den Frame, in den das Grid gezeichnet werden soll."""
        self.plan_grid_frame = frame

    def build_shift_plan_grid(self, year, month, data_ready=False):
        """
        Startet den Zeichenprozess.
        """
        self.year, self.month = year, month

        # Beim Rendern alter Inhalte zerstöre den alten Inhalt
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()

        # FIX: MUSS VOR DEM ZEICHNEN ZURÜCKGESETZT WERDEN
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        users = get_ordered_users_for_schedule()

        if data_ready:
            # Daten aus dem Cache des Data Managers abrufen
            shifts_data = self.dm.shift_schedule_data
            processed_vacations = self.dm.processed_vacations
            wunschfrei_data = self.dm.wunschfrei_data
            daily_counts = self.dm.daily_counts
        else:
            # Synchroner Ladevorgang (Fallback / Refresh einer einzelnen Zelle)
            shifts_data, processed_vacations, wunschfrei_data, daily_counts = self.dm.load_and_process_data(year, month)

        self.users = users
        self.shifts_data = shifts_data
        self.processed_vacations = processed_vacations
        self.wunschfrei_data = wunschfrei_data
        self.daily_counts = daily_counts

        # NEU: Globale Grid-Konfiguration
        days_in_month = calendar.monthrange(year, month)[1]
        MIN_NAME_WIDTH, MIN_DOG_WIDTH = 150, 100
        self.plan_grid_frame.grid_columnconfigure(0, minsize=MIN_NAME_WIDTH)
        self.plan_grid_frame.grid_columnconfigure(1, minsize=MIN_DOG_WIDTH)
        for day_col in range(2, days_in_month + 3):
            self.plan_grid_frame.grid_columnconfigure(day_col, weight=1)

        # Starte den Header-Zeichenprozess
        self._draw_header_rows(year, month)

        # Starte das Chunked Rendering der Benutzer-Zeilen
        self.current_user_row = 0
        self._draw_rows_in_chunks()

    def _draw_header_rows(self, year, month):
        """Zeichnet die Kopfzeilen des Grids."""
        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        rules = self.app.staffing_rules.get('Colors', {})
        header_bg = "#E0E0E0"
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        ausbildung_bg = rules.get('quartals_ausbildung_bg', "#ADD8E6")
        schiessen_bg = rules.get('schiessen_bg', "#FFB6C1")

        # Header Rows (0 and 1)
        tk.Label(self.plan_grid_frame, text="Mitarbeiter", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black",
                 padx=5, pady=5, bd=1, relief="solid").grid(row=0, column=0, columnspan=2, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Name", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=1, column=0, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Diensthund", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black",
                 padx=5, pady=5, bd=1, relief="solid").grid(row=1, column=1, sticky="nsew")

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_abbr = day_map[current_date.weekday()]
            is_weekend = current_date.weekday() >= 5
            event_type = self.app.get_event_type(current_date)

            bg = header_bg
            if self.app.is_holiday(current_date):
                bg = holiday_bg
            elif event_type == "Quartals Ausbildung":
                bg = ausbildung_bg
            elif event_type == "Schießen":
                bg = schiessen_bg
            elif is_weekend:
                bg = weekend_bg

            tk.Label(self.plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), bg=bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=0, column=day + 1, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=str(day), font=("Segoe UI", 9), bg=bg, fg="black", padx=5, pady=5, bd=1,
                     relief="solid").grid(row=1, column=day + 1, sticky="nsew")

        tk.Label(self.plan_grid_frame, text="Std.", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=0, column=days_in_month + 2, rowspan=2, sticky="nsew")

    def _draw_rows_in_chunks(self):
        """Zeichnet Benutzerzeilen in kleinen Paketen, um die UI reaktionsfähig zu halten."""
        users = self.users
        days_in_month = calendar.monthrange(self.year, self.month)[1]

        start_index = self.current_user_row
        end_index = min(start_index + self.ROW_CHUNK_SIZE, len(users))

        # --- Zeichne den aktuellen Block ---
        for i in range(start_index, end_index):
            user_data_row = users[i]
            current_row = i + 2  # Startet nach den 2 Header-Zeilen
            user_id, user_id_str = user_data_row['id'], str(user_data_row['id'])

            # FIX: Defensive Programmierung für 'cells'
            if 'cells' not in self.grid_widgets:
                self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
            self.grid_widgets['cells'][user_id_str] = {}

            # Name und Diensthund
            tk.Label(self.plan_grid_frame, text=f"{user_data_row['vorname']} {user_data_row['name']}",
                     font=("Segoe UI", 10, "bold"), bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid",
                     anchor="w").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=user_data_row.get('diensthund', '---'), font=("Segoe UI", 10),
                     bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=current_row, column=1,
                                                                                        sticky="nsew")

            # Gesamtstunden
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, self.year, self.month)
            total_hours_label = tk.Label(self.plan_grid_frame, text=str(total_hours), font=("Segoe UI", 10, "bold"),
                                         bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e")
            total_hours_label.grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            self.grid_widgets['user_totals'][user_id_str] = total_hours_label

            # Tägliche Schichtzellen
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')

                # Bestimme den anzuzeigenden Text (Logik aus dem Original)
                display_text = self.shifts_data.get(user_id_str, {}).get(date_str, "")
                vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date_obj)
                request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)

                if vacation_status == 'Genehmigt':
                    display_text = 'U'
                elif vacation_status == 'Ausstehend':
                    display_text = "U?"
                elif request_info:
                    status, requested_shift, requested_by, _ = request_info
                    if status == 'Ausstehend':
                        if requested_by == 'admin':
                            display_text = f"{requested_shift} (A)?"
                        else:
                            if requested_shift == 'WF':
                                display_text = 'WF'
                            elif requested_shift == 'T/N':
                                display_text = 'T./N.?'
                            else:
                                display_text = f"{requested_shift}?"
                    elif "Akzeptiert" in status or "Genehmigt" in status:
                        if requested_shift == 'WF': display_text = 'X'

                frame = tk.Frame(self.plan_grid_frame, bd=1, relief="solid")
                frame.grid(row=current_row, column=day + 1, sticky="nsew")
                label = tk.Label(frame, text=display_text, font=("Segoe UI", 10))
                label.pack(expand=True, fill="both")

                is_admin_request = request_info and request_info[2] == 'admin' and request_info[0] == 'Ausstehend'

                # Bindings
                label.bind("<Button-1>",
                           lambda e, uid=user_id, d=day, y=self.year, m=self.month: self.ah.on_grid_cell_click(e, uid,
                                                                                                               d, y, m))
                if '?' in display_text or display_text == 'WF' or is_admin_request:
                    label.bind("<Button-3>",
                               lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))

                self.grid_widgets['cells'][user_id_str][day] = {'frame': frame, 'label': label}

        self.current_user_row = end_index

        # --- Nächster Schritt oder Abschluss ---
        if self.current_user_row < len(users):
            # Weiterzeichnen: Gebe Kontrolle an UI zurück und rufe in 1ms erneut auf
            self.master.after(1, self._draw_rows_in_chunks)
        else:
            # Alle Benutzer gezeichnet, zeichne die Zusammenfassungszeilen
            self.master.after(1, self._draw_summary_rows)

    def _draw_summary_rows(self):
        """Zeichnet die Fußzeilen (Tageszählungen/Staffing) und schließt das Rendern ab."""
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        header_bg, summary_bg = "#E0E0E0", "#D0D0FF"
        daily_counts = self.daily_counts

        current_row = len(self.users) + 2

        # Spacer
        tk.Label(self.plan_grid_frame, text="", bg=header_bg, bd=0).grid(row=current_row, column=0,
                                                                         columnspan=days_in_month + 3, sticky="nsew",
                                                                         pady=1)
        current_row += 1

        for item in ordered_abbrevs_to_show:
            abbrev = item['abbreviation']

            if 'daily_counts' not in self.grid_widgets:
                self.grid_widgets['daily_counts'] = {}

            self.grid_widgets['daily_counts'][abbrev] = {}

            tk.Label(self.plan_grid_frame, text=abbrev, font=("Segoe UI", 9, "bold"), bg=summary_bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=item.get('name', 'N/A'), font=("Segoe UI", 9), bg=summary_bg,
                     fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="w").grid(row=current_row, column=1,
                                                                                        sticky="nsew")
            for day in range(1, days_in_month + 1):
                current_date = date(self.year, self.month, day)
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)

                display_text = ""
                if not (abbrev == "6" and (not is_friday or is_holiday)):
                    count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                    min_required = self.dm.get_min_staffing_for_date(current_date).get(abbrev)
                    display_text = f"{count}/{min_required}" if min_required is not None else str(count)

                count_label = tk.Label(self.plan_grid_frame, text=display_text, font=("Segoe UI", 9), bd=1,
                                       relief="solid")
                count_label.grid(row=current_row, column=day + 1, sticky="nsew")
                self.grid_widgets['daily_counts'][abbrev][day] = count_label

            tk.Label(self.plan_grid_frame, text="---", font=("Segoe UI", 9), bg=summary_bg, fg="black", padx=5, pady=5,
                     bd=1, relief="solid", anchor="e").grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            current_row += 1

        # Abschluss: Farben anwenden und Scrollregion konfigurieren
        self.apply_grid_colors(self.year, self.month)

        # Trigger den finalen Aufräum-Schritt im Tab
        self.master._finalize_ui_after_render()

    def apply_grid_colors(self, year, month):
        """Wendet Farben und Markierungen auf das bestehende Grid an."""
        days_in_month = calendar.monthrange(year, month)[1]
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        pending_color = rules.get('Ausstehend', 'orange')
        admin_pending_color = rules.get('Admin_Ausstehend', '#E0B0FF')
        summary_bg = "#D0D0FF"

        users = get_ordered_users_for_schedule()

        # Sicherstellen, dass die DM-Caches aktuell sind und die Konflikte neu berechnet wurden
        self.dm.update_violation_set(year, month)

        processed_vacations = self.dm.processed_vacations
        wunschfrei_data = self.dm.wunschfrei_data
        daily_counts = self.dm.daily_counts

        # --- User Grid Zellen einfärben ---
        for user in users:
            user_id, user_id_str = user['id'], str(user['id'])
            for day in range(1, days_in_month + 1):
                cell_widgets = self.grid_widgets['cells'].get(user_id_str, {}).get(day)
                if not cell_widgets: continue

                frame = cell_widgets['frame']
                label = cell_widgets['label']
                current_date = date(year, month, day)
                is_weekend = current_date.weekday() >= 5
                is_holiday = self.app.is_holiday(current_date)

                # Normalisierung des angezeigten Textes für den Shift-Daten-Lookup
                original_text = label.cget("text")
                shift_abbrev = original_text.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF",
                                                                                                                  "X").replace(
                    "T.", "T").replace("N.", "N")

                shift_data = self.app.shift_types_data.get(shift_abbrev)
                vacation_status = processed_vacations.get(user_id_str, {}).get(current_date)
                request_info = wunschfrei_data.get(user_id_str, {}).get(current_date.strftime('%Y-%m-%d'))

                bg_color = "white"
                if is_holiday:
                    bg_color = holiday_bg
                elif is_weekend:
                    bg_color = weekend_bg

                if shift_data and shift_data.get('color'):
                    if shift_abbrev in ["U", "X", "EU"]:
                        bg_color = shift_data['color']
                    elif not is_holiday and not is_weekend:
                        bg_color = shift_data['color']

                if vacation_status == 'Ausstehend':
                    bg_color = pending_color
                elif request_info and request_info[0] == 'Ausstehend':
                    if request_info[2] == 'admin':
                        bg_color = admin_pending_color
                    else:
                        bg_color = pending_color

                if (user['id'], day) in self.dm.violation_cells:
                    bg_color = rules.get('violation_bg', "#FF5555")
                    fg_color = "white"
                else:
                    fg_color = self.app.get_contrast_color(bg_color)

                label.config(bg=bg_color, fg=fg_color)

                frame.config(bg="black", bd=1)
                if vacation_status == 'Ausstehend':
                    frame.config(bg="gold", bd=2)

        # --- Daily Counts einfärben ---
        for item in get_ordered_shift_abbrevs(include_hidden=False):
            abbrev = item['abbreviation']

            if 'daily_counts' not in self.grid_widgets:
                continue

            day_map = self.grid_widgets['daily_counts'].get(abbrev, {})

            for day, label in day_map.items():
                current_date = date(year, month, day)
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)

                bg = summary_bg

                if abbrev != "6":
                    if is_holiday:
                        bg = holiday_bg
                    elif current_date.weekday() >= 5:
                        bg = weekend_bg

                if abbrev == "6" and (not is_friday or is_holiday):
                    label.config(bg=bg, bd=0)
                    continue

                count = daily_counts.get(current_date.strftime('%Y-%m-%d'), {}).get(abbrev, 0)
                min_req = self.dm.get_min_staffing_for_date(current_date).get(abbrev)

                if min_req is not None:
                    if count < min_req:
                        bg = rules.get('alert_bg', "#FF5555")
                    elif count > min_req:
                        bg = rules.get('overstaffed_bg', "#FFFF99")
                    else:
                        bg = rules.get('success_bg', "#90EE90")

                label.config(bg=bg, fg=self.app.get_contrast_color(bg), bd=1)

    def print_shift_plan(self, year, month, month_name):
        """Erzeugt das HTML für den Druck und öffnet es im Browser."""
        users = get_ordered_users_for_schedule()
        shifts_data = self.dm.shift_schedule_data
        wunschfrei_data = self.dm.wunschfrei_data
        processed_vacations = self.dm.processed_vacations
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")

        # ... (HTML-Generierung wie im Originalcode) ...
        html = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>Dienstplan {month_name}</title>
            <style>
                body {{ font-family: Segoe UI, Arial, sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
                th, td {{ border: 1px solid #ccc; padding: 6px; text-align: center; }}
                th {{ background-color: #E0E0E0; }}
                .weekend {{ background-color: {weekend_bg}; }}
                .holiday {{ background-color: {holiday_bg}; }}
                .name-col {{ text-align: left; font-weight: bold; width: 140px; }}
                .dog-col {{ text-align: left; width: 90px; }}
                .hours-col {{ font-weight: bold; width: 40px; }}
            </style>
        </head>
        <body>
            <h1>Dienstplan für {month_name}</h1>
            <table>
                <thead>
                    <tr>
                        <th class="name-col">Name</th>
                        <th class="dog-col">Diensthund</th>
        """

        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_class = ""
            if self.app.is_holiday(current_date):
                day_class = "holiday"
            elif current_date.weekday() >= 5:
                day_class = "weekend"
            html += f'<th class="{day_class}">{day}<br>{day_map[current_date.weekday()]}</th>'

        html += '<th class="hours-col">Std.</th>'
        html += """
                </tr>
            </thead>
            <tbody>
        """

        for user in users:
            user_id_str = str(user['id'])
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, year, month)
            html += f"""
                <tr>
                    <td class="name-col">{user['vorname']} {user['name']}</td>
                    <td class="dog-col">{user.get('diensthund', '---')}</td>
            """
            for day in range(1, days_in_month + 1):
                current_date = date(year, month, day)
                date_str = current_date.strftime('%Y-%m-%d')

                display_text = shifts_data.get(user_id_str, {}).get(date_str, "&nbsp;")
                vacation_status = processed_vacations.get(user_id_str, {}).get(current_date)
                if vacation_status == 'Genehmigt': display_text = 'U'

                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)
                if request_info and ("Akzeptiert" in request_info[0] or "Genehmigt" in request_info[0]) and \
                        request_info[1] == 'WF':
                    display_text = 'X'

                bg_color = ""
                is_weekend = current_date.weekday() >= 5
                is_holiday = self.app.is_holiday(current_date)

                if is_holiday:
                    bg_color = holiday_bg
                elif is_weekend:
                    bg_color = weekend_bg

                shift_data = self.app.shift_types_data.get(display_text)

                if shift_data and shift_data.get('color'):
                    if display_text in ["U", "X", "EU"]:
                        bg_color = shift_data['color']
                    elif not is_holiday and not is_weekend:
                        bg_color = shift_data['color']

                text_color = self.app.get_contrast_color(bg_color) if bg_color else "black"
                html += f'<td style="background-color: {bg_color or "white"}; color: {text_color};">{display_text}</td>'

            html += f'<td class="hours-col">{total_hours}</td></tr>'

        html += """
            </tbody>
        </table>
        </body>
        </html>
        """

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
                f.write(html)
                filepath = f.name

            webbrowser.open(f"file://{os.path.realpath(filepath)}")
            messagebox.showinfo("Drucken",
                                "Der Dienstplan wurde in deinem Webbrowser geöffnet.\n\nBitte nutze dort die Druckfunktion (normalerweise Strg+P oder Cmd+P).",
                                parent=self.master)
        except Exception as e:
            messagebox.showerror("Fehler", f"Der Plan konnte nicht zum Drucken geöffnet werden:\n{e}",
                                 parent=self.master)