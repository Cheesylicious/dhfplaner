# gui/shift_plan_renderer.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
import calendar

# --- Importiere die ausgelagerten Klassen ---
from .shift_plan_printer import ShiftPlanPrinter
from .shift_plan_styler import ShiftPlanStyler
from .shift_plan_text_logic import ShiftPlanTextLogic
from .shift_plan_widget_factory import ShiftPlanWidgetFactory  # HINZUGEFÜGT

from database.db_shifts import get_ordered_shift_abbrevs


class ShiftPlanRenderer:
    """
    Verantwortlich für die Koordination der Dienstplan-Darstellung.

    Delegiert die Aufgaben an:
    - ShiftPlanWidgetFactory (Erstellung der Tkinter-Widgets)
    - ShiftPlanStyler (Farbgebung)
    - ShiftPlanTextLogic (Textbestimmung)
    - ShiftPlanPrinter (Druck-Export)
    """

    def __init__(self, master, app, data_manager, action_handler):
        self.master = master
        self.app = app
        self.dm = data_manager
        self.ah = action_handler

        # Logik-Instanzen
        self.styler = ShiftPlanStyler(app, data_manager)
        self.text_logic = ShiftPlanTextLogic(data_manager)

        self.plan_grid_frame = None
        self.widget_factory = None  # Wird in build_shift_plan_grid initialisiert

        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        self.current_user_row = 0
        self.ROW_CHUNK_SIZE = 5

        self.year = 0
        self.month = 0
        self.users_to_render = []

    def set_plan_grid_frame(self, frame):
        """Setzt den Frame, in den das Grid gezeichnet werden soll."""
        self.plan_grid_frame = frame

    def build_shift_plan_grid(self, year, month, data_ready=False):
        """ Startet den (Neu-)Zeichenprozess des gesamten Grids. """
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists():
            print("[FEHLER] plan_grid_frame nicht gesetzt oder zerstört in build_shift_plan_grid.")
            return

        print(f"[Renderer] Baue Grid für {year}-{month:02d}...")
        self.year, self.month = year, month

        # --- NEU: Widget Factory instanziieren ---
        # Braucht den Parent-Frame, um Widgets darin zu erstellen
        self.widget_factory = ShiftPlanWidgetFactory(self.plan_grid_frame)
        # --- ENDE NEU ---

        # Zerstöre alte Widgets und setze Widget-Referenzen zurück
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        # Benutzerliste vom DM holen
        all_users_from_dm = self.dm.cached_users_for_month
        self.users_to_render = [user for user in all_users_from_dm if user.get('is_visible', 1) == 1]
        print(f"[Renderer] {len(self.users_to_render)} Benutzer werden gerendert.")

        # Daten holen (sicherstellen, dass Caches für Logik-Klassen geladen sind)
        if data_ready:
            self.dm.get_previous_month_shifts()  # Vormonat sicherstellen
            # Hauptdaten sollten schon im Cache sein
            self.daily_counts = getattr(self.dm, 'daily_counts', {})
        else:
            print("[WARNUNG] Renderer führt synchronen Daten-Reload durch!")
            try:
                _, _, _, self.daily_counts = self.dm.load_and_process_data(year, month)
                self.dm.get_previous_month_shifts()  # Vormonat laden
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim synchronen Laden der Daten im Renderer:\n{e}",
                                     parent=self.master)
                self.daily_counts = {}

        # Grid konfigurieren
        days_in_month = calendar.monthrange(year, month)[1]
        MIN_NAME_WIDTH, MIN_DOG_WIDTH, MIN_UE_WIDTH = 150, 100, 35
        for i in range(self.plan_grid_frame.grid_size()[0]): self.plan_grid_frame.grid_columnconfigure(i, weight=0,
                                                                                                       minsize=0)
        self.plan_grid_frame.grid_columnconfigure(0, minsize=MIN_NAME_WIDTH, weight=0)
        self.plan_grid_frame.grid_columnconfigure(1, minsize=MIN_DOG_WIDTH, weight=0)
        self.plan_grid_frame.grid_columnconfigure(2, minsize=MIN_UE_WIDTH, weight=0)
        for day_col in range(3, days_in_month + 3):
            self.plan_grid_frame.grid_columnconfigure(day_col, weight=1, minsize=35)
        self.plan_grid_frame.grid_columnconfigure(days_in_month + 3, weight=0, minsize=40)

        # Zeichnen starten
        self._draw_header_rows(year, month)
        self.current_user_row = 0

        if self.users_to_render:
            self._draw_rows_in_chunks()
        else:
            self._draw_summary_rows()

    def _draw_header_rows(self, year, month):
        """Erstellt die Kopfzeilen-Widgets mithilfe der WidgetFactory."""
        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        rules = self.app.staffing_rules.get('Colors', {})
        header_bg = "#E0E0E0"
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        ausbildung_bg = rules.get('quartals_ausbildung_bg', "#ADD8E6")
        schiessen_bg = rules.get('schiessen_bg', "#FFB6C1")

        # --- ANPASSUNG: Nutze WidgetFactory ---
        self.widget_factory.create_header_label(
            "Mitarbeiter", ("Segoe UI", 10, "bold"), header_bg, "black", 0, 0, colspan=3
        )
        self.widget_factory.create_header_label(
            "Name", ("Segoe UI", 9, "bold"), header_bg, "black", 1, 0
        )
        self.widget_factory.create_header_label(
            "Diensthund", ("Segoe UI", 9, "bold"), header_bg, "black", 1, 1
        )
        self.widget_factory.create_header_label(
            "Ü", ("Segoe UI", 9, "bold"), header_bg, "black", 1, 2
        )

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

            self.widget_factory.create_header_label(
                day_abbr, ("Segoe UI", 9, "bold"), bg, "black", 0, day + 2
            )
            self.widget_factory.create_header_label(
                str(day), ("Segoe UI", 9), bg, "black", 1, day + 2
            )

        self.widget_factory.create_header_label(
            "Std.", ("Segoe UI", 10, "bold"), header_bg, "black", 0, days_in_month + 3, rowspan=2
        )
        # --- ENDE ANPASSUNG ---

    def _draw_rows_in_chunks(self):
        """ Zeichnet Benutzerzeilen in Paketen. """
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        users = self.users_to_render
        if not users: return
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        start_index = self.current_user_row
        end_index = min(start_index + self.ROW_CHUNK_SIZE, len(users))

        prev_month_last_day = date(self.year, self.month, 1) - timedelta(days=1)

        for i in range(start_index, end_index):
            user_data_row = users[i];
            current_row = i + 2
            user_id, user_id_str = user_data_row['id'], str(user_data_row['id'])

            if user_id_str not in self.grid_widgets['cells']: self.grid_widgets['cells'][user_id_str] = {}

            # --- ANPASSUNG: Nutze WidgetFactory ---
            # Name & Hund
            self.widget_factory.create_user_info_label(
                f"{user_data_row['vorname']} {user_data_row['name']}",
                ("Segoe UI", 10, "bold"), current_row, 0, anchor="w"
            )
            self.widget_factory.create_user_info_label(
                user_data_row.get('diensthund', '---'),
                ("Segoe UI", 10), current_row, 1, anchor="center"
            )

            # Stunden
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, self.year, self.month)
            total_hours_label = self.widget_factory.create_user_info_label(
                str(total_hours), ("Segoe UI", 10, "bold"), current_row, days_in_month + 3, anchor="e"
            )
            self.grid_widgets['user_totals'][user_id_str] = total_hours_label
            # --- ENDE ANPASSUNG ---

            # "Ü"-Zelle
            prev_shift_display = self.text_logic.get_display_text_for_prev_month(user_id_str, prev_month_last_day)

            # Widget erstellen
            cell_ue = self.widget_factory.create_grid_cell(
                prev_shift_display, ("Segoe UI", 10, "italic"), current_row, 2
            )

            # Logik anwenden
            self.styler.apply_prev_month_cell_color(
                user_id, prev_month_last_day, cell_ue['frame'], cell_ue['label'], prev_shift_display
            )
            self.grid_widgets['cells'][user_id_str][0] = cell_ue

            # Tageszellen
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')

                # 1. Text bestimmen
                text_with_lock, final_display_text, request_info = self.text_logic.get_display_text_for_cell(
                    user_id_str, current_date_obj
                )

                # 2. Widget erstellen
                cell = self.widget_factory.create_grid_cell(
                    text_with_lock, ("Segoe UI", 10), current_row, day + 2
                )
                label = cell['label']
                frame = cell['frame']

                # 3. Farbe anwenden
                self.styler.apply_cell_color(user_id, day, current_date_obj, frame, label, final_display_text)

                # 4. Bindings anwenden
                is_admin_request_pending = request_info and request_info[2] == 'admin' and request_info[
                    0] == 'Ausstehend'
                needs_context_menu = '?' in final_display_text or final_display_text == 'WF' or is_admin_request_pending

                label.bind("<Button-1>",
                           lambda e, uid=user_id, d=day, y=self.year, m=self.month: self.ah.on_grid_cell_click(e, uid,
                                                                                                               d, y, m))
                if needs_context_menu:
                    label.bind("<Button-3>",
                               lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))
                else:
                    label.unbind("<Button-3>")

                # 5. Referenz speichern
                self.grid_widgets['cells'][user_id_str][day] = cell

        self.current_user_row = end_index

        # Nächsten Chunk planen oder Zusammenfassung zeichnen
        if self.current_user_row < len(users):
            if self.master and self.master.winfo_exists():
                self.master.after(1, self._draw_rows_in_chunks)
        else:
            if self.master and self.master.winfo_exists():
                self.master.after(1, self._draw_summary_rows)

    def _draw_summary_rows(self):
        """ Zeichnet die unteren Zählzeilen. """
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        ordered_abbrevs_to_show = get_ordered_shift_abbrevs(include_hidden=False)
        header_bg, summary_bg = "#E0E0E0", "#D0D0FF"
        current_row = len(self.users_to_render) + 2

        # --- ANPASSUNG: Nutze WidgetFactory ---
        self.widget_factory.create_spacer_label(current_row, 0, days_in_month + 4, bg=header_bg)
        current_row += 1

        if 'daily_counts' not in self.grid_widgets: self.grid_widgets['daily_counts'] = {}

        for item in ordered_abbrevs_to_show:
            abbrev = item['abbreviation']
            self.grid_widgets['daily_counts'][abbrev] = {}

            self.widget_factory.create_summary_label(
                abbrev, ("Segoe UI", 9, "bold"), current_row, 0, anchor="center", bg=summary_bg
            )
            self.widget_factory.create_summary_label(
                item.get('name', 'N/A'), ("Segoe UI", 9), current_row, 1, anchor="w", bg=summary_bg
            )
            self.widget_factory.create_summary_label(
                "", ("Segoe UI", 9), current_row, 2, anchor="center", bg=summary_bg
            )  # Leere "Ü" Zelle

            for day in range(1, days_in_month + 1):
                current_date = date(self.year, self.month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)

                count = self.daily_counts.get(date_str, {}).get(abbrev, 0)
                min_req = self.dm.get_min_staffing_for_date(current_date).get(abbrev)

                display_text = str(count)
                if min_req is not None: display_text = f"{count}/{min_req}"
                if abbrev == "6" and (not is_friday or is_holiday): display_text = ""

                # Widget erstellen
                count_label = self.widget_factory.create_summary_label(
                    display_text, ("Segoe UI", 9), current_row, day + 2, anchor="center", bg=summary_bg
                )

                # Referenz speichern
                self.grid_widgets['daily_counts'][abbrev][day] = count_label

                # Farbe anwenden
                self.styler.apply_daily_count_color(abbrev, day, current_date, count_label, count, min_req)

            self.widget_factory.create_summary_label(
                "---", ("Segoe UI", 9), current_row, days_in_month + 3, anchor="e", bg=summary_bg
            )
            current_row += 1
        # --- ENDE ANPASSUNG ---

        if self.master and self.master.winfo_exists():
            self.master._finalize_ui_after_render()

    # --- Gezielte Update-Methoden (BLEIBEN UNVERÄNDERT) ---
    # Sie greifen auf self.grid_widgets zu, die korrekt befüllt werden.

    def update_cell_display(self, user_id, day, date_obj):
        """Aktualisiert Text und Farbe einer einzelnen Zelle."""
        user_id_str = str(user_id)
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        if not any(u['id'] == user_id for u in self.users_to_render): return
        if day == 0: return

        cell_widgets = self.grid_widgets.get('cells', {}).get(user_id_str, {}).get(day)
        if not cell_widgets or not cell_widgets['label'].winfo_exists(): return

        frame = cell_widgets['frame'];
        label = cell_widgets['label']
        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[Renderer Update Cell] User: {user_id}, Day: {day}")

        # 1. Neuen Text bestimmen (via TextLogic)
        text_with_lock, final_display_text, request_info = self.text_logic.get_display_text_for_cell(
            user_id_str, date_obj
        )

        print(f"  -> Final Display Text (with lock): '{text_with_lock}'")
        label.config(text=text_with_lock)

        # 2. Bindings anpassen
        is_admin_request_pending = request_info and request_info[2] == 'admin' and request_info[0] == 'Ausstehend'
        needs_context_menu = '?' in final_display_text or final_display_text == 'WF' or is_admin_request_pending
        current_binding = label.bind("<Button-3>")

        if needs_context_menu and not current_binding:
            print(f"  -> Binding Button-3 HINZUGEFÜGT für '{final_display_text}'")
            label.bind("<Button-3>",
                       lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))
        elif not needs_context_menu and current_binding:
            print(f"  -> Binding Button-3 ENTFERNT für '{final_display_text}'")
            label.unbind("<Button-3>")

        # 3. Farbe anwenden (via Styler)
        self.styler.apply_cell_color(user_id, day, date_obj, frame, label, final_display_text)

    def update_user_total_hours(self, user_id):
        """Aktualisiert die Gesamtstundenanzeige für einen Benutzer."""
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        if not any(u['id'] == user_id for u in self.users_to_render): return
        user_id_str = str(user_id)
        total_label = self.grid_widgets.get('user_totals', {}).get(user_id_str)
        if total_label and total_label.winfo_exists():
            new_total = self.dm.calculate_total_hours_for_user(user_id_str, self.year, self.month)
            print(f"[Renderer Update Hours] User: {user_id}, New Total: {new_total}")
            total_label.config(text=str(new_total))

    def update_daily_counts_for_day(self, day, date_obj):
        """Aktualisiert alle Zähl-Labels für einen bestimmten Tag."""
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[Renderer Update Counts] Day: {day}")

        current_counts_for_day = self.dm.daily_counts.get(date_str, {})
        min_staffing_for_day = self.dm.get_min_staffing_for_date(date_obj)

        for abbrev, day_map in self.grid_widgets.get('daily_counts', {}).items():
            count_label = day_map.get(day)
            if count_label and count_label.winfo_exists():
                count = current_counts_for_day.get(abbrev, 0)
                min_req = min_staffing_for_day.get(abbrev)

                display_text = str(count)
                if min_req is not None: display_text = f"{count}/{min_req}"
                is_friday = date_obj.weekday() == 4;
                is_holiday = self.app.is_holiday(date_obj)
                if abbrev == "6" and (not is_friday or is_holiday): display_text = ""

                count_label.config(text=display_text)
                self.styler.apply_daily_count_color(abbrev, day, date_obj, count_label, count, min_req)

    def update_conflict_markers(self, updated_cells):
        """Aktualisiert die Farbe von Zellen basierend auf Konfliktänderungen."""
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        print(f"[Renderer Update Conflicts] Zellen: {updated_cells}")
        if not updated_cells: return

        for user_id, day in updated_cells:
            if day == 0: continue

            if any(u['id'] == user_id for u in self.users_to_render):
                cell_widgets = self.grid_widgets.get('cells', {}).get(str(user_id), {}).get(day)
                if cell_widgets and cell_widgets['frame'].winfo_exists():
                    try:
                        date_obj = date(self.year, self.month, day)
                        full_text = cell_widgets['label'].cget("text")
                        current_text_no_lock = full_text.lstrip("🔒")

                        self.styler.apply_cell_color(user_id, day, date_obj, cell_widgets['frame'],
                                                     cell_widgets['label'],
                                                     current_text_no_lock)
                    except ValueError:
                        print(f"[FEHLER] Ungültiges Datum bei Konflikt-Update: {self.year}-{self.month}-{day}")

    def print_shift_plan(self, year, month, month_name):
        """Delegiert die Druckerstellung an den ShiftPlanPrinter."""
        users = self.users_to_render
        if not users:
            messagebox.showinfo("Drucken", "Keine Benutzer zum Drucken vorhanden.", parent=self.master)
            return

        try:
            printer = ShiftPlanPrinter(
                master=self.master,
                app=self.app,
                data_manager=self.dm,
                users_to_render=users,
                year=year,
                month=month,
                month_name=month_name
            )
            printer.generate_and_open_html()
        except Exception as e:
            messagebox.showerror("Fehler", f"Plan konnte nicht zum Drucken geöffnet werden:\n{e}", parent=self.master)