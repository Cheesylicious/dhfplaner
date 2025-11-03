# gui/renderer/renderer_draw.py
# NEU: Ausgelagerte Logik für das initiale Zeichnen des Grids (Regel 4)
# ANGEPASST: Fügt <Enter> Bindings für Tastatur-Shortcuts hinzu

import tkinter as tk
from tkinter import ttk
from datetime import date, timedelta
import calendar
from database.db_shifts import get_ordered_shift_abbrevs


class RendererDraw:
    """
    Verantwortlich für das initiale Zeichnen (Erstellen der Widgets)
    des gesamten Schichtplan-Grids.
    (Ausgelagert aus ShiftPlanRenderer nach Regel 4).
    """

    def __init__(self, renderer_instance):
        self.renderer = renderer_instance
        # Zugriff auf die Hauptkomponenten über die Renderer-Referenz
        self.app = self.renderer.app
        self.dm = self.renderer.dm
        self.ah = self.renderer.ah
        self.styling = self.renderer.styling_helper  # Zugriff auf den Styling-Helfer

    def _draw_header_rows(self, year, month):
        """Zeichnet die Kopfzeilen (Tage, Datum etc.)."""
        plan_grid_frame = self.renderer.plan_grid_frame
        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        rules = self.app.staffing_rules.get('Colors', {})
        header_bg = "#E0E0E0";
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700");
        ausbildung_bg = rules.get('quartals_ausbildung_bg', "#ADD8E6")
        schiessen_bg = rules.get('schiessen_bg', "#FFB6C1")

        tk.Label(plan_grid_frame, text="Mitarbeiter", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black",
                 padx=5, pady=5, bd=1, relief="solid").grid(row=0, column=0, columnspan=3, sticky="nsew")
        tk.Label(plan_grid_frame, text="Name", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=1, column=0, sticky="nsew")
        tk.Label(plan_grid_frame, text="Diensthund", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black",
                 padx=5, pady=5, bd=1, relief="solid").grid(row=1, column=1, sticky="nsew")
        tk.Label(plan_grid_frame, text="Ü", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black", padx=5, pady=5,
                 bd=1, relief="solid").grid(row=1, column=2, sticky="nsew")

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            day_data = self.styling.get_day_data(day)  # Nutze Helfer

            day_abbr = day_map[current_date.weekday()]
            is_weekend = day_data['is_weekend']
            event_type = day_data['event_type']
            is_holiday = day_data['is_holiday']

            bg = header_bg
            if is_holiday:
                bg = holiday_bg
            elif event_type == "Quartals Ausbildung":
                bg = ausbildung_bg
            elif event_type == "Schießen":
                bg = schiessen_bg
            elif is_weekend:
                bg = weekend_bg

            tk.Label(plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), bg=bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=0, column=day + 2, sticky="nsew")
            tk.Label(plan_grid_frame, text=str(day), font=("Segoe UI", 9), bg=bg, fg="black", padx=5, pady=5, bd=1,
                     relief="solid").grid(row=1, column=day + 2, sticky="nsew")

        tk.Label(plan_grid_frame, text="Std.", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black", padx=5,
                 pady=5, bd=1, relief="solid").grid(row=0, column=days_in_month + 3, rowspan=2, sticky="nsew")

    def _draw_rows_in_chunks(self):
        """ Zeichnet Benutzerzeilen in Paketen. """
        # Zugriff auf die geteilten Attribute des Renderers
        plan_grid_frame = self.renderer.plan_grid_frame
        if not plan_grid_frame or not plan_grid_frame.winfo_exists(): return

        users = self.renderer.users_to_render
        if not users: return

        days_in_month = calendar.monthrange(self.renderer.year, self.renderer.month)[1]
        start_index = self.renderer.current_user_row
        end_index = min(start_index + self.renderer.ROW_CHUNK_SIZE, len(users))

        prev_month_last_day = date(self.renderer.year, self.renderer.month, 1) - timedelta(days=1)

        for i in range(start_index, end_index):
            user_data_row = users[i];
            current_row = i + 2
            user_id, user_id_str = user_data_row['id'], str(user_data_row['id'])

            if user_id_str not in self.renderer.grid_widgets['cells']:
                self.renderer.grid_widgets['cells'][user_id_str] = {}

            # Name & Hund
            tk.Label(plan_grid_frame, text=f"{user_data_row['vorname']} {user_data_row['name']}",
                     font=("Segoe UI", 10, "bold"), bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid",
                     anchor="w").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(plan_grid_frame, text=user_data_row.get('diensthund', '---'), font=("Segoe UI", 10),
                     bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=current_row, column=1,
                                                                                        sticky="nsew")

            # Stunden
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, self.renderer.year, self.renderer.month)
            # --- KORREKTUR (Regel 2): Stunden korrekt formatieren ---
            total_hours_label = tk.Label(plan_grid_frame, text=f"{total_hours:.1f}", font=("Segoe UI", 10, "bold"),
                                         bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e")
            # --- ENDE KORREKTUR ---
            total_hours_label.grid(row=current_row, column=days_in_month + 3, sticky="nsew")
            self.renderer.grid_widgets['user_totals'][user_id_str] = total_hours_label

            # "Ü"-Zelle (delegiert an Styling-Helfer)
            prev_shift_display = self.styling._get_display_text_for_prev_month(user_id_str, prev_month_last_day)
            frame_ue = tk.Frame(plan_grid_frame, bd=1, relief="solid")
            frame_ue.grid(row=current_row, column=2, sticky="nsew")
            label_ue = tk.Label(frame_ue, text=prev_shift_display, font=("Segoe UI", 10, "italic"), anchor="center")
            label_ue.pack(expand=True, fill="both", padx=1, pady=1)
            self.styling._apply_prev_month_cell_color(user_id, prev_month_last_day, frame_ue, label_ue,
                                                      prev_shift_display)
            self.renderer.grid_widgets['cells'][user_id_str][0] = {'frame': frame_ue, 'label': label_ue}

            # --- NEU (Für Tastatur-Shortcuts) ---
            # Binde Hover-Events an die "Ü"-Zelle (Tag 0)
            label_ue.bind("<Enter>", lambda e, uid=user_id: self.renderer.set_hovered_cell(uid, 0))
            frame_ue.bind("<Enter>", lambda e, uid=user_id: self.renderer.set_hovered_cell(uid, 0))
            # --- ENDE NEU ---

            # Tageszellen
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.renderer.year, self.renderer.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')

                # Textbestimmung (Logik bleibt hier, da sie datenabhängig ist)
                display_text_from_schedule = self.renderer.shifts_data.get(user_id_str, {}).get(date_str, "")
                vacation_status = self.renderer.processed_vacations.get(user_id_str, {}).get(current_date_obj)
                request_info = self.renderer.wunschfrei_data.get(user_id_str, {}).get(date_str)

                final_display_text = ""
                if display_text_from_schedule:
                    final_display_text = display_text_from_schedule
                if vacation_status == 'Genehmigt':
                    final_display_text = 'U'
                elif vacation_status == 'Ausstehend':
                    final_display_text = "U?"
                elif request_info:
                    # --- KORREKTUR: Sicheres Entpacken von request_info ---
                    try:
                        status, requested_shift, requested_by, _ = request_info
                    except (TypeError, ValueError):
                        status, requested_shift, requested_by = None, None, None
                    # --- ENDE KORREKTUR ---

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
                    elif (
                            "Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and not display_text_from_schedule:
                        final_display_text = 'X'

                # Lock-Symbol hinzufügen
                lock_char = ""
                if hasattr(self.dm, 'shift_lock_manager'):
                    lock_status = self.dm.shift_lock_manager.get_lock_status(user_id_str, date_str)
                    if lock_status is not None:
                        lock_char = "🔒"
                text_with_lock = f"{lock_char}{final_display_text}".strip()

                # Widget Erstellung
                frame = tk.Frame(plan_grid_frame, bd=1, relief="solid", bg="black")
                frame.grid(row=current_row, column=day + 2, sticky="nsew")
                label = tk.Label(frame, text=text_with_lock, font=("Segoe UI", 10), anchor="center")
                label.pack(expand=True, fill="both", padx=1, pady=1)

                # Farbe anwenden (delegiert an Styling-Helfer)
                self.styling.apply_cell_color(user_id, day, current_date_obj, frame, label, final_display_text)

                # Bindings (ActionHandler wird über self.ah erreicht)
                is_admin_request_pending = request_info and request_info[2] == 'admin' and request_info[
                    0] == 'Ausstehend'
                needs_context_menu = '?' in final_display_text or final_display_text == 'WF' or is_admin_request_pending

                label.bind("<Button-1>",
                           lambda e, uid=user_id, d=day, y=self.renderer.year,
                                  m=self.renderer.month: self.ah.on_grid_cell_click(e, uid,
                                                                                    d, y, m))
                if needs_context_menu:
                    label.bind("<Button-3>",
                               lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))
                else:
                    label.unbind("<Button-3>")

                # --- NEU (Für Tastatur-Shortcuts) ---
                # Binde Hover-Events an die Tageszelle (Tag 1-31)
                label.bind("<Enter>", lambda e, uid=user_id, d=day: self.renderer.set_hovered_cell(uid, d))
                frame.bind("<Enter>", lambda e, uid=user_id, d=day: self.renderer.set_hovered_cell(uid, d))
                # --- ENDE NEU ---

                self.renderer.grid_widgets['cells'][user_id_str][day] = {'frame': frame, 'label': label}

        self.renderer.current_user_row = end_index

        # Nächsten Chunk planen (Aufruf an den Haupt-Renderer)
        if self.renderer.current_user_row < len(users):
            if self.renderer.master and self.renderer.master.winfo_exists():
                self.renderer.master.after(1, self.renderer._draw_rows_in_chunks)
        else:
            if self.renderer.master and self.renderer.master.winfo_exists():
                self.renderer.master.after(1, self.renderer._draw_summary_rows)

    def _draw_summary_rows(self):
        """ Zeichnet die unteren Zählzeilen. """
        plan_grid_frame = self.renderer.plan_grid_frame
        if not plan_grid_frame or not plan_grid_frame.winfo_exists(): return

        days_in_month = calendar.monthrange(self.renderer.year, self.renderer.month)[1]
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        header_bg, summary_bg = "#E0E0E0", "#D0D0FF"
        current_row = len(self.renderer.users_to_render) + 2

        tk.Label(plan_grid_frame, text="", bg=header_bg, bd=0).grid(row=current_row, column=0,
                                                                    columnspan=days_in_month + 4, sticky="nsew",
                                                                    pady=1)
        current_row += 1

        if 'daily_counts' not in self.renderer.grid_widgets:
            self.renderer.grid_widgets['daily_counts'] = {}

        for item in ordered_abbrevs_to_show:
            abbrev = item['abbreviation']
            self.renderer.grid_widgets['daily_counts'][abbrev] = {}  # Leeres Dict für den Tag

            tk.Label(plan_grid_frame, text=abbrev, font=("Segoe UI", 9, "bold"), bg=summary_bg, fg="black", padx=5,
                     pady=5, bd=1, relief="solid").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(plan_grid_frame, text=item.get('name', 'N/A'), font=("Segoe UI", 9), bg=summary_bg,
                     fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="w").grid(row=current_row, column=1,
                                                                                        sticky="nsew")
            tk.Label(plan_grid_frame, text="", font=("Segoe UI", 9), bg=summary_bg, bd=1, relief="solid").grid(
                row=current_row, column=2, sticky="nsew")

            for day in range(1, days_in_month + 1):
                current_date = date(self.renderer.year, self.renderer.month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                is_friday = current_date.weekday() == 4

                day_data = self.styling.get_day_data(day)  # Nutze Styling-Helfer
                is_holiday = day_data['is_holiday']

                count = self.renderer.daily_counts.get(date_str, {}).get(abbrev, 0)
                min_req = self.dm.get_min_staffing_for_date(current_date).get(abbrev)

                display_text = str(count)
                # --- KORREKTUR (Regel 2): Logik zur Zählanzeige ---
                if min_req is not None and min_req > 0:
                    display_text = f"{count}/{min_req}"
                elif min_req is None and count == 0:
                    display_text = ""  # Zeige 0 nicht an, wenn nicht geplant
                # --- ENDE KORREKTUR ---

                if abbrev == "6" and (not is_friday or is_holiday): display_text = ""

                count_label = tk.Label(plan_grid_frame, text=display_text, font=("Segoe UI", 9), bd=1,
                                       relief="solid", anchor="center")
                count_label.grid(row=current_row, column=day + 2, sticky="nsew")
                self.renderer.grid_widgets['daily_counts'][abbrev][day] = count_label

                # Farbe anwenden (delegiert an Styling-Helfer)
                self.styling.apply_daily_count_color(abbrev, day, current_date, count_label, count, min_req)

            tk.Label(plan_grid_frame, text="---", font=("Segoe UI", 9), bg=summary_bg, fg="black", padx=5, pady=5,
                     bd=1, relief="solid", anchor="e").grid(row=current_row, column=days_in_month + 3, sticky="nsew")
            current_row += 1

        # Abschluss: UI im Tab finalisieren (Aufruf an den Haupt-Renderer)
        if self.renderer.master and self.renderer.master.winfo_exists():
            if hasattr(self.renderer.master, '_finalize_ui_after_render'):
                self.renderer.master._finalize_ui_after_render()
            else:
                print("[FEHLER] Renderer-Master (ShiftPlanTab) hat keine _finalize_ui_after_render Methode.")