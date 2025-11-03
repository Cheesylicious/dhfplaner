# python
# gui/shift_plan_renderer.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta
import calendar
# Entfernt: webbrowser, os, tempfile (sind jetzt im Printer)

# --- NEUE IMPORTE (Regel 4) ---
from .renderer.renderer_styling import RendererStyling
from .renderer.renderer_printer import RendererPrinter
from .renderer.renderer_draw import RendererDraw


# --- ENDE NEUE IMPORTE ---

# get_ordered_shift_abbrevs wird jetzt vom Draw-Helfer importiert
# from database.db_shifts import get_ordered_shift_abbrevs


class ShiftPlanRenderer:
    """
    Verantwortlich für die Erstellung der visuellen Darstellung des Dienstplangrids
    und die Anwendung aller Farben/Stile, sowie gezielte Updates.

    (Refactored, Regel 4: Styling, Drucken und Zeichnen ausgelagert)
    """

    def __init__(self, master, app, data_manager, action_handler):
        self.master = master
        self.app = app
        self.dm = data_manager
        self.ah = action_handler
        self.plan_grid_frame = None
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        self.current_user_row = 0
        self.ROW_CHUNK_SIZE = 5

        self.year = 0
        self.month = 0
        self.users_to_render = []

        # --- NEU (Für Tastatur-Shortcuts) ---
        # Speichert (user_id, day_of_month) der Zelle unter dem Mauszeiger
        self.hovered_cell_coords = None
        # --- ENDE NEU ---

        # --- NEU (Refactoring): Helfer-Klassen instanziieren ---
        self.styling_helper = RendererStyling(self)
        self.printer = RendererPrinter(self)
        self.draw_helper = RendererDraw(self)  # Neuer Draw-Helfer
        # --- ENDE NEU ---

        # Cache für Tagesdaten (wird vom Styling-Helfer verwaltet)
        self.day_data_cache = {}

        # Referenzen auf Vormonatsdaten (wird von build_shift_plan_grid gefüllt)
        self.prev_month_shifts = {}
        self.processed_vacations_prev = {}
        self.wunschfrei_data_prev = {}

        # Daten-Referenzen (werden von build_shift_plan_grid gefüllt)
        self.shifts_data = {}
        self.processed_vacations = {}
        self.wunschfrei_data = {}
        self.daily_counts = {}

    def set_plan_grid_frame(self, frame):
        self.plan_grid_frame = frame

        # --- NEU (Für Tastatur-Shortcuts) ---
        # Wenn die Maus das gesamte Grid-Frame verlässt,
        # setzen wir die Hover-Koordinaten zurück.
        if self.plan_grid_frame:
            self.plan_grid_frame.bind("<Leave>", self._on_mouse_leave_grid)
        # --- ENDE NEU ---

    # --- Methoden für Caching und Styling (delegiert) ---

    def _pre_calculate_day_data(self, year, month):
        self.styling_helper._pre_calculate_day_data(year, month)

    def get_day_data(self, day):
        return self.styling_helper.get_day_data(day)

    def _get_display_text_for_prev_month(self, user_id_str, prev_date_obj):
        return self.styling_helper._get_display_text_for_prev_month(user_id_str, prev_date_obj)

    def _apply_prev_month_cell_color(self, user_id, date_obj, frame, label, display_text_no_lock):
        self.styling_helper._apply_prev_month_cell_color(user_id, date_obj, frame, label, display_text_no_lock)

    def apply_cell_color(self, user_id, day, date_obj, frame, label, final_display_text_no_lock):
        self.styling_helper.apply_cell_color(user_id, day, date_obj, frame, label, final_display_text_no_lock)

    def apply_daily_count_color(self, abbrev, day, date_obj, label, count, min_req):
        self.styling_helper.apply_daily_count_color(abbrev, day, date_obj, label, count, min_req)

    # --- Haupt-Render-Logik (delegiert) ---

    def build_shift_plan_grid(self, year, month, data_ready=False):
        """ Startet den (Neu-)Zeichenprozess des gesamten Grids. """
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists():
            print("[FEHLER] plan_grid_frame nicht gesetzt oder zerstört in build_shift_plan_grid.")
            return

        print(f"[Renderer] Baue Grid für {year}-{month:02d}...")
        self.year, self.month = year, month

        # --- NEU (Für Tastatur-Shortcuts) ---
        # Setze Hover-Koordinaten zurück, da das Gitter neu gezeichnet wird
        self.hovered_cell_coords = None
        # --- ENDE NEU ---

        # 1. Styling-Cache vorbereiten
        self._pre_calculate_day_data(year, month)

        # 2. Alte Widgets zerstören
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        # 3. Benutzerliste holen
        all_users_from_dm = self.dm.cached_users_for_month
        self.users_to_render = [user for user in all_users_from_dm if user.get('is_visible', 1) == 1]
        print(f"[Renderer] {len(self.users_to_render)} Benutzer werden gerendert.")

        # 4. Daten-Referenzen füllen
        if data_ready:
            self.shifts_data = getattr(self.dm, 'shift_schedule_data', {})
            self.processed_vacations = getattr(self.dm, 'processed_vacations', {})
            self.wunschfrei_data = getattr(self.dm, 'wunschfrei_data', {})
            self.daily_counts = getattr(self.dm, 'daily_counts', {})
            self.prev_month_shifts = self.dm.get_previous_month_shifts()
            self.processed_vacations_prev = getattr(self.dm, 'processed_vacations_prev', {})
            self.wunschfrei_data_prev = getattr(self.dm, 'wunschfrei_data_prev', {})
        else:
            # Fallback (sollte dank Preloading selten sein)
            print("[WARNUNG] Renderer führt synchronen Daten-Reload durch!")
            try:
                # --- KORREKTUR: load_and_process_data gibt keinen Wert zurück ---
                # (Es füllt die DM-Caches, wir müssen sie danach lesen)
                self.dm.load_and_process_data(year, month)
                self.shifts_data = self.dm.shift_schedule_data
                self.processed_vacations = self.dm.processed_vacations
                self.wunschfrei_data = self.dm.wunschfrei_data
                self.daily_counts = self.dm.daily_counts
                # --- ENDE KORREKTUR ---

                self.prev_month_shifts = self.dm.get_previous_month_shifts()
                self.processed_vacations_prev = getattr(self.dm, 'processed_vacations_prev', {})
                self.wunschfrei_data_prev = getattr(self.dm, 'wunschfrei_data_prev', {})
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim synchronen Laden der Daten im Renderer:\n{e}",
                                     parent=self.master)
                # Setze leere Daten, um Absturz zu verhindern
                self.shifts_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts = {}, {}, {}, {}
                self.prev_month_shifts, self.processed_vacations_prev, self.wunschfrei_data_prev = {}, {}, {}

        # 5. Grid-Spalten konfigurieren
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

        # 6. Zeichnen starten (delegiert)
        self.draw_helper._draw_header_rows(year, month)
        self.current_user_row = 0
        if self.users_to_render:
            self.draw_helper._draw_rows_in_chunks()
        else:
            self.draw_helper._draw_summary_rows()

    # --- Delegierte Draw-Methoden ---

    def _draw_header_rows(self, year, month):
        self.draw_helper._draw_header_rows(year, month)

    def _draw_rows_in_chunks(self):
        self.draw_helper._draw_rows_in_chunks()

    def _draw_summary_rows(self):
        self.draw_helper._draw_summary_rows()

    # --- Gezielte Update-Methoden (Bleiben im Renderer, da sie Widgets *modifizieren*) ---

    def update_cell_display(self, user_id, day, date_obj):
        """Aktualisiert eine einzelne Zelle (inkl. 'Ü' für day==0)."""
        user_id_str = str(user_id)
        date_str = date_obj.strftime('%Y-%m-%d')

        # Vormonat-Zelle (Ü)
        if day == 0:
            cell = self.grid_widgets.get('cells', {}).get(user_id_str, {}).get(0)
            if not cell: return
            frame, label = cell['frame'], cell['label']
            display = self._get_display_text_for_prev_month(user_id_str, date_obj)  # Delegiert
            if label.winfo_exists():
                label.config(text=display)
            self._apply_prev_month_cell_color(user_id, date_obj, frame, label, display)  # Delegiert
            return

        # Aktueller Monat: Bestimme finalen Text (ohne Lock)
        display_text_from_schedule = self.shifts_data.get(user_id_str, {}).get(date_str, "")
        vacation_status = self.processed_vacations.get(user_id_str, {}).get(date_obj)
        request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)

        final_display_text = ""
        if display_text_from_schedule:
            final_display_text = display_text_from_schedule
        if vacation_status == 'Genehmigt':
            final_display_text = 'U'
        elif vacation_status == 'Ausstehend':
            final_display_text = "U?"
        elif request_info:
            # --- KORREKTUR: request_info Entpacken (basiert auf db_plan_loader) ---
            # request_info ist (status, requested_shift, requested_by, request_id)
            try:
                status, requested_shift, requested_by, _ = request_info
            except (TypeError, ValueError):
                print(f"[FEHLER] Unerwartetes request_info Format: {request_info}")
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

        # Lock-Symbol ermitteln
        lock_char = ""
        if hasattr(self.dm, 'shift_lock_manager'):
            lock_status = self.dm.shift_lock_manager.get_lock_status(user_id_str, date_str)
            if lock_status is not None:
                lock_char = "🔒"
        text_with_lock = f"{lock_char}{final_display_text}".strip()

        cell = self.grid_widgets.get('cells', {}).get(user_id_str, {}).get(day)
        if not cell: return
        frame, label = cell['frame'], cell['label']

        # Text aktualisieren und Farbe anwenden
        if label.winfo_exists():
            label.config(text=text_with_lock)
        self.apply_cell_color(user_id, day, date_obj, frame, label, final_display_text)  # Delegiert

        # Bindings aktualisieren
        is_admin_request_pending = request_info and request_info[2] == 'admin' and request_info[0] == 'Ausstehend'
        needs_context_menu = '?' in final_display_text or final_display_text == 'WF' or is_admin_request_pending

        label.bind("<Button-1>",
                   lambda e, uid=user_id, d=day, y=self.year, m=self.month: self.ah.on_grid_cell_click(e, uid, d, y, m))
        if needs_context_menu:
            label.bind("<Button-3>",
                       lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))
        else:
            if label.winfo_exists():  # Sicherstellen, dass das Widget noch existiert
                label.unbind("<Button-3>")

    def update_user_total_hours(self, user_id):
        """Aktualisiert das Stunden-Label für einen Benutzer."""
        user_id_str = str(user_id)
        label = self.grid_widgets.get('user_totals', {}).get(user_id_str)
        if not label: return
        total_hours = self.dm.calculate_total_hours_for_user(user_id_str, self.year, self.month)
        if label.winfo_exists():
            label.config(text=f"{total_hours:.1f}")  # Formatierung als Float

    def update_daily_counts_for_day(self, day, date_obj):
        """Aktualisiert alle Zähl-Labels für einen bestimmten Tag."""
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        date_str = date_obj.strftime('%Y-%m-%d')
        current_counts_for_day = self.dm.daily_counts.get(date_str, {})
        min_staffing_for_day = self.dm.get_min_staffing_for_date(date_obj)

        for abbrev, day_map in self.grid_widgets.get('daily_counts', {}).items():
            count_label = day_map.get(day)
            if count_label and count_label.winfo_exists():
                count = current_counts_for_day.get(abbrev, 0)
                min_req = min_staffing_for_day.get(abbrev)
                display_text = str(count)
                if min_req is not None and min_req > 0:  # Zeige 0/0 nicht an
                    display_text = f"{count}/{min_req}"
                elif min_req is None and count == 0:  # Zeige 0 nicht an, wenn nicht geplant
                    display_text = ""

                is_friday = date_obj.weekday() == 4;

                day_data = self.get_day_data(day)  # Nutze Cache
                is_holiday = day_data['is_holiday']

                if abbrev == "6" and not (is_friday or is_holiday):
                    display_text = ""

                count_label.config(text=display_text)
                self.apply_daily_count_color(abbrev, day, date_obj, count_label, count, min_req)  # Delegiert

    def update_conflict_markers(self, affected_cells=None):
        """
        Aktualisiert Konflikt-/Violation-Markierungen im Grid.
        (Logik bleibt hier, nutzt aber delegierte Farb-Helfer)
        """
        try:
            if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists():
                return

            def _date_for(user_day):
                if user_day == 0:
                    return date(self.year, self.month, 1) - timedelta(days=1)
                try:
                    return date(self.year, self.month, user_day)
                except ValueError:  # Tag existiert nicht (z.B. 31. Feb)
                    return None

            if affected_cells:
                iterator = affected_cells
            else:
                iterator = []
                for user_id_str, days_map in self.grid_widgets.get('cells', {}).items():
                    for day_key in days_map.keys():
                        iterator.append((int(user_id_str), day_key))

            for user_id, day in iterator:
                user_id_str = str(user_id)
                cell = self.grid_widgets.get('cells', {}).get(user_id_str, {}).get(day)
                if not cell: continue
                frame, label = cell.get('frame'), cell.get('label')
                if not label or not frame: continue
                if not label.winfo_exists() or not frame.winfo_exists(): continue

                date_obj = _date_for(day)
                if date_obj is None: continue  # Ungültiges Datum überspringen

                # Vormonat ("Ü") -> delegierte Farb-/Rahmenlogik
                if day == 0:
                    display = self._get_display_text_for_prev_month(user_id_str, date_obj)  # Delegiert
                    if label.winfo_exists():
                        label.config(text=display)
                    self._apply_prev_month_cell_color(user_id, date_obj, frame, label, display)  # Delegiert
                    continue

                # Aktueller Monat
                date_str = date_obj.strftime('%Y-%m-%d')
                display_text_from_schedule = self.shifts_data.get(user_id_str, {}).get(date_str, "")
                vacation_status = self.processed_vacations.get(user_id_str, {}).get(date_obj)
                request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str)

                final_display_text = ""
                if display_text_from_schedule:
                    final_display_text = display_text_from_schedule
                if vacation_status == 'Genehmigt':
                    final_display_text = 'U'
                elif vacation_status == 'Ausstehend':
                    final_display_text = 'U?'
                elif request_info:
                    # --- KORREKTUR: request_info Entpacken (basiert auf db_plan_loader) ---
                    try:
                        status, requested_shift, requested_by, _ = request_info
                    except (TypeError, ValueError):
                        status, requested_shift, requested_by = None, None, None
                    # --- ENDE KORREKTUR ---

                    if status == 'Ausstehend':
                        if requested_shift == 'WF':
                            final_display_text = 'WF'
                        elif requested_by == 'admin':
                            final_display_text = f"{requested_shift} (A)?"
                        elif requested_shift == 'T/N':
                            final_display_text = 'T./N.?'
                        else:
                            final_display_text = f"{requested_shift}?"
                    elif (
                            "Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and not display_text_from_schedule:
                        final_display_text = 'X'

                # Wende Farb- / Rahmen-Logik an (delegiert)
                self.apply_cell_color(user_id, day, date_obj, frame, label, final_display_text)

        except Exception as e:
            print(f"[Renderer] update_conflict_markers failed: {e}")
            import traceback
            traceback.print_exc()

    # --- Druckfunktion (delegiert) ---

    def print_shift_plan(self, year, month, month_name):
        """Delegiert die Erstellung der HTML-Druckansicht an den Helfer."""
        self.printer.print_shift_plan(year, month, month_name)

    # --- NEUE METHODEN (Für Tastatur-Shortcuts) ---

    def set_hovered_cell(self, user_id, day):
        """ Speichert die Zelle, über der die Maus schwebt. """
        self.hovered_cell_coords = (user_id, day)

    def clear_hovered_cell(self):
        """ Löscht die Hover-Information. """
        self.hovered_cell_coords = None

    def get_hovered_cell_coords(self):
        """
        Gibt die Zelle zurück, über der die Maus schwebt.
        Returns:
            tuple (user_id, day) or None
        """
        return self.hovered_cell_coords

    def _on_mouse_leave_grid(self, event):
        """ Setzt die Hover-Koordinaten zurück, wenn die Maus das Gitter verlässt. """
        self.clear_hovered_cell()

    # --- ENDE NEUE METHODEN ---