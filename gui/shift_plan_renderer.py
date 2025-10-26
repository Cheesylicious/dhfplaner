# gui/shift_plan_renderer.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
import calendar
import webbrowser
import os
import tempfile

from database.db_shifts import get_ordered_shift_abbrevs
# get_ordered_users_for_schedule wird hier nicht mehr direkt benötigt

class ShiftPlanRenderer:
    """
    Verantwortlich für die Erstellung der visuellen Darstellung des Dienstplangrids
    und die Anwendung aller Farben/Stile, sowie gezielte Updates.
    """

    def __init__(self, master, app, data_manager, action_handler):
        self.master = master
        self.app = app
        self.dm = data_manager
        self.ah = action_handler
        self.plan_grid_frame = None
        # Initialisiere grid_widgets immer als leeres Dictionary mit den erwarteten Schlüsseln
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        self.current_user_row = 0
        self.ROW_CHUNK_SIZE = 5 # Chunk-Größe beibehalten

        # Referenzen für Jahr/Monat der aktuellen Anzeige
        self.year = 0
        self.month = 0
        # Referenz auf die aktuell gerenderte Benutzerliste
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

        # Zerstöre alte Widgets und setze Widget-Referenzen zurück
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        self.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        # Benutzerliste vom DM holen (nur die sichtbaren für die Anzeige)
        all_users_from_dm = self.dm.cached_users_for_month
        self.users_to_render = [user for user in all_users_from_dm if user.get('is_visible', 1) == 1]
        print(f"[Renderer] {len(self.users_to_render)} Benutzer werden gerendert.")

        # Daten holen (sollten durch data_ready=True aus DM-Cache kommen)
        if data_ready:
            # Stelle sicher, dass Attribute existieren, bevor darauf zugegriffen wird
            self.shifts_data = getattr(self.dm, 'shift_schedule_data', {})
            self.processed_vacations = getattr(self.dm, 'processed_vacations', {})
            self.wunschfrei_data = getattr(self.dm, 'wunschfrei_data', {})
            self.daily_counts = getattr(self.dm, 'daily_counts', {})
        else:
            # Synchroner Ladevorgang (Fallback)
            print("[WARNUNG] Renderer führt synchronen Daten-Reload durch!")
            try:
                # Stelle sicher, dass load_and_process_data alle benötigten Attribute setzt
                self.shifts_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts = self.dm.load_and_process_data(year, month)
            except Exception as e:
                 messagebox.showerror("Fehler", f"Fehler beim synchronen Laden der Daten im Renderer:\n{e}", parent=self.master)
                 self.shifts_data, self.processed_vacations, self.wunschfrei_data, self.daily_counts = {}, {}, {}, {}


        # Grid konfigurieren
        days_in_month = calendar.monthrange(year, month)[1]
        MIN_NAME_WIDTH, MIN_DOG_WIDTH = 150, 100
        # Konfiguriere Spalten neu
        # Alte Konfigurationen entfernen (optional, aber sauberer)
        for i in range(self.plan_grid_frame.grid_size()[0]): self.plan_grid_frame.grid_columnconfigure(i, weight=0, minsize=0)
        # Neue Konfigurationen setzen
        self.plan_grid_frame.grid_columnconfigure(0, minsize=MIN_NAME_WIDTH, weight=0) # Name nicht skalieren
        self.plan_grid_frame.grid_columnconfigure(1, minsize=MIN_DOG_WIDTH, weight=0) # Hund nicht skalieren
        for day_col in range(2, days_in_month + 2): # Tage (Index 2 bis days+1)
             self.plan_grid_frame.grid_columnconfigure(day_col, weight=1, minsize=35) # Mindestbreite, skalierbar
        self.plan_grid_frame.grid_columnconfigure(days_in_month + 2, weight=0, minsize=40) # Stunden nicht skalieren


        # Zeichnen starten
        self._draw_header_rows(year, month)
        self.current_user_row = 0
        # Starte den asynchronen Zeichenprozess, wenn Benutzer vorhanden sind
        if self.users_to_render:
            self._draw_rows_in_chunks()
        else:
             # Wenn keine Benutzer da sind, zeichne direkt die Zusammenfassung
             self._draw_summary_rows()


    def _draw_header_rows(self, year, month):
        # (Diese Methode bleibt unverändert)
        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        rules = self.app.staffing_rules.get('Colors', {})
        header_bg = "#E0E0E0"; weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700"); ausbildung_bg = rules.get('quartals_ausbildung_bg', "#ADD8E6")
        schiessen_bg = rules.get('schiessen_bg', "#FFB6C1")

        tk.Label(self.plan_grid_frame, text="Mitarbeiter", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=0, column=0, columnspan=2, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Name", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=1, column=0, sticky="nsew")
        tk.Label(self.plan_grid_frame, text="Diensthund", font=("Segoe UI", 9, "bold"), bg=header_bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=1, column=1, sticky="nsew")

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day); day_abbr = day_map[current_date.weekday()]
            is_weekend = current_date.weekday() >= 5; event_type = self.app.get_event_type(current_date)
            bg = header_bg
            if self.app.is_holiday(current_date): bg = holiday_bg
            elif event_type == "Quartals Ausbildung": bg = ausbildung_bg
            elif event_type == "Schießen": bg = schiessen_bg
            elif is_weekend: bg = weekend_bg
            tk.Label(self.plan_grid_frame, text=day_abbr, font=("Segoe UI", 9, "bold"), bg=bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=0, column=day + 1, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=str(day), font=("Segoe UI", 9), bg=bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=1, column=day + 1, sticky="nsew")

        tk.Label(self.plan_grid_frame, text="Std.", font=("Segoe UI", 10, "bold"), bg=header_bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=0, column=days_in_month + 2, rowspan=2, sticky="nsew")


    def _draw_rows_in_chunks(self):
        """ Zeichnet Benutzerzeilen in Paketen. """
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        users = self.users_to_render
        if not users: return # Nichts zu zeichnen
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        start_index = self.current_user_row
        end_index = min(start_index + self.ROW_CHUNK_SIZE, len(users))

        for i in range(start_index, end_index):
            user_data_row = users[i]; current_row = i + 2
            user_id, user_id_str = user_data_row['id'], str(user_data_row['id'])

            if user_id_str not in self.grid_widgets['cells']: self.grid_widgets['cells'][user_id_str] = {}

            # Name & Hund
            tk.Label(self.plan_grid_frame, text=f"{user_data_row['vorname']} {user_data_row['name']}", font=("Segoe UI", 10, "bold"), bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="w").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=user_data_row.get('diensthund', '---'), font=("Segoe UI", 10), bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=current_row, column=1, sticky="nsew")

            # Stunden
            total_hours = self.dm.calculate_total_hours_for_user(user_id_str, self.year, self.month)
            total_hours_label = tk.Label(self.plan_grid_frame, text=str(total_hours), font=("Segoe UI", 10, "bold"), bg="white", fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e")
            total_hours_label.grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            self.grid_widgets['user_totals'][user_id_str] = total_hours_label

            # Tageszellen
            for day in range(1, days_in_month + 1):
                current_date_obj = date(self.year, self.month, day)
                date_str = current_date_obj.strftime('%Y-%m-%d')

                # --- Textbestimmung ---
                # Daten aus den aktuellen Caches holen (sollten aktuell sein)
                display_text_from_schedule = self.shifts_data.get(user_id_str, {}).get(date_str, "")
                vacation_status = self.processed_vacations.get(user_id_str, {}).get(current_date_obj)
                request_info = self.wunschfrei_data.get(user_id_str, {}).get(date_str) # Holt Tupel oder None

                # Logik zur Bestimmung des finalen Anzeigetextes
                final_display_text = "" # Standard: Leer
                if display_text_from_schedule: # Wenn eine Schicht eingetragen ist
                    final_display_text = display_text_from_schedule

                # Überschreibe mit Urlaub/Anfrage, falls vorhanden und relevant
                if vacation_status == 'Genehmigt': final_display_text = 'U'
                elif vacation_status == 'Ausstehend': final_display_text = "U?"
                elif request_info:
                    status, requested_shift, requested_by, _ = request_info
                    # Nur ausstehende Anfragen im Plan anzeigen
                    if status == 'Ausstehend':
                        if requested_by == 'admin': final_display_text = f"{requested_shift} (A)?"
                        else: # User-Anfrage
                            if requested_shift == 'WF': final_display_text = 'WF'
                            elif requested_shift == 'T/N': final_display_text = 'T./N.?' # Mit Punkten für Anzeige
                            else: final_display_text = f"{requested_shift}?"
                    # Akzeptiertes Wunschfrei 'X' nur anzeigen, wenn *keine* andere Schicht eingetragen ist
                    elif ("Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and not display_text_from_schedule:
                         final_display_text = 'X'
                    # Wenn eine Schicht eingetragen ist, hat diese Vorrang vor alten Anfragen (außer Urlaub)

                # --- Widget Erstellung ---
                frame = tk.Frame(self.plan_grid_frame, bd=1, relief="solid", bg="black") # Standard-Rahmen
                frame.grid(row=current_row, column=day + 1, sticky="nsew")
                label = tk.Label(frame, text=final_display_text, font=("Segoe UI", 10), anchor="center")
                label.pack(expand=True, fill="both", padx=1, pady=1)

                # Farbe direkt anwenden
                self.apply_cell_color(user_id, day, current_date_obj, frame, label, final_display_text)

                # Bindings
                is_admin_request_pending = request_info and request_info[2] == 'admin' and request_info[0] == 'Ausstehend'
                needs_context_menu = '?' in final_display_text or final_display_text == 'WF' or is_admin_request_pending
                # Immer Linksklick binden
                label.bind("<Button-1>", lambda e, uid=user_id, d=day, y=self.year, m=self.month: self.ah.on_grid_cell_click(e, uid, d, y, m))
                # Rechtsklick nur wenn nötig
                if needs_context_menu:
                    label.bind("<Button-3>", lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))
                else:
                     label.unbind("<Button-3>") # Sicherstellen, dass kein altes Binding bleibt

                self.grid_widgets['cells'][user_id_str][day] = {'frame': frame, 'label': label}

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
        # Starte nach der letzten Benutzerzeile + Spacer
        current_row = len(self.users_to_render) + 2

        tk.Label(self.plan_grid_frame, text="", bg=header_bg, bd=0).grid(row=current_row, column=0, columnspan=days_in_month + 3, sticky="nsew", pady=1)
        current_row += 1

        if 'daily_counts' not in self.grid_widgets: self.grid_widgets['daily_counts'] = {}

        for item in ordered_abbrevs_to_show:
            abbrev = item['abbreviation']
            self.grid_widgets['daily_counts'][abbrev] = {} # Leeres Dict für den Tag

            tk.Label(self.plan_grid_frame, text=abbrev, font=("Segoe UI", 9, "bold"), bg=summary_bg, fg="black", padx=5, pady=5, bd=1, relief="solid").grid(row=current_row, column=0, sticky="nsew")
            tk.Label(self.plan_grid_frame, text=item.get('name', 'N/A'), font=("Segoe UI", 9), bg=summary_bg, fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="w").grid(row=current_row, column=1, sticky="nsew")

            for day in range(1, days_in_month + 1):
                current_date = date(self.year, self.month, day)
                date_str = current_date.strftime('%Y-%m-%d')
                is_friday = current_date.weekday() == 4
                is_holiday = self.app.is_holiday(current_date)
                # Hole aktuelle Zählung aus dem (hoffentlich aktuellen) DM-Cache
                count = self.daily_counts.get(date_str, {}).get(abbrev, 0)
                min_req = self.dm.get_min_staffing_for_date(current_date).get(abbrev)

                display_text = str(count)
                if min_req is not None: display_text = f"{count}/{min_req}"
                if abbrev == "6" and (not is_friday or is_holiday): display_text = ""

                count_label = tk.Label(self.plan_grid_frame, text=display_text, font=("Segoe UI", 9), bd=1, relief="solid", anchor="center")
                count_label.grid(row=current_row, column=day + 1, sticky="nsew")
                self.grid_widgets['daily_counts'][abbrev][day] = count_label
                # Farbe direkt anwenden
                self.apply_daily_count_color(abbrev, day, current_date, count_label, count, min_req)

            tk.Label(self.plan_grid_frame, text="---", font=("Segoe UI", 9), bg=summary_bg, fg="black", padx=5, pady=5, bd=1, relief="solid", anchor="e").grid(row=current_row, column=days_in_month + 2, sticky="nsew")
            current_row += 1

        # Abschluss: UI im Tab finalisieren
        if self.master and self.master.winfo_exists():
             self.master._finalize_ui_after_render()


    # --- Gezielte Update-Methoden ---

    def update_cell_display(self, user_id, day, date_obj):
        """Aktualisiert Text und Farbe einer einzelnen Zelle."""
        user_id_str = str(user_id)
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        if not any(u['id'] == user_id for u in self.users_to_render): return

        cell_widgets = self.grid_widgets.get('cells', {}).get(user_id_str, {}).get(day)
        if not cell_widgets or not cell_widgets['label'].winfo_exists(): return

        frame = cell_widgets['frame']; label = cell_widgets['label']
        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"[Renderer Update Cell] User: {user_id}, Day: {day}")

        # 1. Neuen Text bestimmen (aus den *aktuellen* DM-Caches)
        display_text_from_schedule = self.dm.shift_schedule_data.get(user_id_str, {}).get(date_str, "")
        vacation_status = self.dm.processed_vacations.get(user_id_str, {}).get(date_obj)
        request_info = self.dm.wunschfrei_data.get(user_id_str, {}).get(date_str) # Holt Tupel oder None

        # Logik zur Bestimmung des finalen Anzeigetextes
        final_display_text = ""
        if display_text_from_schedule: final_display_text = display_text_from_schedule

        if vacation_status == 'Genehmigt': final_display_text = 'U'
        elif vacation_status == 'Ausstehend': final_display_text = "U?"
        elif request_info:
            status, requested_shift, requested_by, _ = request_info
            if status == 'Ausstehend':
                if requested_by == 'admin': final_display_text = f"{requested_shift} (A)?"
                else:
                    if requested_shift == 'WF': final_display_text = 'WF'
                    elif requested_shift == 'T/N': final_display_text = 'T./N.?'
                    else: final_display_text = f"{requested_shift}?"
            elif ("Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and not display_text_from_schedule:
                 final_display_text = 'X'

        print(f"  -> Final Display Text: '{final_display_text}'")
        label.config(text=final_display_text) # Setze den finalen Text (auch wenn leer!)

        # 2. Bindings anpassen
        is_admin_request_pending = request_info and request_info[2] == 'admin' and request_info[0] == 'Ausstehend'
        needs_context_menu = '?' in final_display_text or final_display_text == 'WF' or is_admin_request_pending
        current_binding = label.bind("<Button-3>")

        if needs_context_menu and not current_binding:
             print(f"  -> Binding Button-3 HINZUGEFÜGT für '{final_display_text}'")
             label.bind("<Button-3>", lambda e, uid=user_id, dt=date_str: self.ah.show_wunschfrei_context_menu(e, uid, dt))
        elif not needs_context_menu and current_binding:
             print(f"  -> Binding Button-3 ENTFERNT für '{final_display_text}'")
             label.unbind("<Button-3>")

        # 3. Farbe anwenden (nutzt final_display_text)
        self.apply_cell_color(user_id, day, date_obj, frame, label, final_display_text)


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
         # Hole die *aktuellsten* Zählungen vom DM (sollten durch recalculate... aktuell sein)
         current_counts_for_day = self.dm.daily_counts.get(date_str, {})
         min_staffing_for_day = self.dm.get_min_staffing_for_date(date_obj)

         # Iteriere durch alle Schichten im Grid-Widget
         for abbrev, day_map in self.grid_widgets.get('daily_counts', {}).items():
             count_label = day_map.get(day)
             if count_label and count_label.winfo_exists():
                 count = current_counts_for_day.get(abbrev, 0) # Default 0
                 min_req = min_staffing_for_day.get(abbrev)
                 display_text = str(count)
                 if min_req is not None: display_text = f"{count}/{min_req}"
                 is_friday = date_obj.weekday() == 4; is_holiday = self.app.is_holiday(date_obj)
                 if abbrev == "6" and (not is_friday or is_holiday): display_text = ""
                 count_label.config(text=display_text)
                 self.apply_daily_count_color(abbrev, day, date_obj, count_label, count, min_req)


    def update_conflict_markers(self, updated_cells):
        """Aktualisiert die Farbe von Zellen basierend auf Konfliktänderungen."""
        if not self.plan_grid_frame or not self.plan_grid_frame.winfo_exists(): return
        print(f"[Renderer Update Conflicts] Zellen: {updated_cells}")
        if not updated_cells: return

        for user_id, day in updated_cells:
            if any(u['id'] == user_id for u in self.users_to_render): # Nur sichtbare User
                cell_widgets = self.grid_widgets.get('cells', {}).get(str(user_id), {}).get(day)
                if cell_widgets and cell_widgets['frame'].winfo_exists():
                    try:
                        date_obj = date(self.year, self.month, day)
                        # Hole den aktuellen Text aus dem Label für die Farbgebung
                        current_text = cell_widgets['label'].cget("text")
                        self.apply_cell_color(user_id, day, date_obj, cell_widgets['frame'], cell_widgets['label'], current_text)
                    except ValueError: print(f"[FEHLER] Ungültiges Datum bei Konflikt-Update: {self.year}-{self.month}-{day}")


    # --- Hilfsfunktionen zum Einfärben ---
    def apply_cell_color(self, user_id, day, date_obj, frame, label, final_display_text):
        """Wendet Farbe auf eine einzelne Zelle an, basierend auf dem finalen Text."""
        user_id_str = str(user_id)
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF"); holiday_bg = rules.get('holiday_bg', "#FFD700")
        pending_color = rules.get('Ausstehend', 'orange'); admin_pending_color = rules.get('Admin_Ausstehend', '#E0B0FF')

        is_weekend = date_obj.weekday() >= 5; is_holiday = self.app.is_holiday(date_obj)
        date_str = date_obj.strftime('%Y-%m-%d')

        # Normalisiere den *finalen* Text für Schicht-Lookup und Farbfindung
        # --- KORREKTUR 3 (von 4) ---
        # .replace("T.", "T").replace("N.", "N") entfernt.
        shift_abbrev = final_display_text.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF", "X")
        # --- KORREKTUR ENDE ---


        shift_data = self.app.shift_types_data.get(shift_abbrev)
        # Statusinformationen aus DM holen (für Rahmen etc.)
        vacation_status = self.dm.processed_vacations.get(user_id_str, {}).get(date_obj)
        request_info = self.dm.wunschfrei_data.get(user_id_str, {}).get(date_str)

        # --- Farb-Logik ---
        bg_color = "white" # Standard-Hintergrund
        if is_holiday: bg_color = holiday_bg
        elif is_weekend: bg_color = weekend_bg

        # Schichtfarbe nur anwenden, wenn vorhanden und passend
        if shift_data and shift_data.get('color'):
            if shift_abbrev in ["U", "X", "EU"]: bg_color = shift_data['color'] # Immer Schichtfarbe
            elif not is_holiday and not is_weekend: bg_color = shift_data['color'] # Nur an normalen Tagen

        # Statusfarben überschreiben (falls relevant für den finalen Text)
        if final_display_text == "U?": bg_color = pending_color # Urlaub ausstehend
        elif request_info and request_info[0] == 'Ausstehend': # Wunsch ausstehend
            # Prüfe, ob der finale Text die Anfrage anzeigt
            if "?" in final_display_text or final_display_text == "WF":
                bg_color = admin_pending_color if request_info[2] == 'admin' else pending_color

        # Konfliktprüfung
        is_violation = (user_id, day) in self.dm.violation_cells
        fg_color = self.app.get_contrast_color(bg_color)
        frame_border_color = "black"; frame_border_width = 1

        if is_violation:
            bg_color = rules.get('violation_bg', "#FF5555")
            fg_color = "white"
            frame_border_color = "darkred"; frame_border_width = 2
        # Rahmen nur für *sichtbare* ausstehende Anträge
        elif final_display_text == "U?":
             frame_border_color = "orange"; frame_border_width = 2
        elif request_info and request_info[0] == 'Ausstehend' and ("?" in final_display_text or final_display_text == "WF"):
             frame_border_color = "purple" if request_info[2] == 'admin' else "orange"; frame_border_width = 2

        # Stelle sicher, dass Widgets noch existieren
        if label.winfo_exists(): label.config(bg=bg_color, fg=fg_color)
        if frame.winfo_exists(): frame.config(bg=frame_border_color, bd=frame_border_width)


    def apply_daily_count_color(self, abbrev, day, date_obj, label, count, min_req):
        """Wendet Farbe auf ein einzelnes Tageszählungs-Label an."""
        # (Diese Funktion bleibt unverändert)
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF"); holiday_bg = rules.get('holiday_bg', "#FFD700")
        summary_bg = "#D0D0FF"
        is_friday = date_obj.weekday() == 4; is_holiday = self.app.is_holiday(date_obj); is_weekend = date_obj.weekday() >= 5
        bg = summary_bg; border_width = 1
        if not (abbrev == "6" and (not is_friday or is_holiday)):
             if is_holiday: bg = holiday_bg
             elif is_weekend: bg = weekend_bg
        if abbrev == "6" and (not is_friday or is_holiday): border_width = 0
        elif min_req is not None and min_req > 0:
             if count < min_req: bg = rules.get('alert_bg', "#FF5555")
             elif count > min_req and rules.get('overstaffed_bg'): bg = rules.get('overstaffed_bg', "#FFFF99")
             elif count == min_req and rules.get('success_bg'): bg = rules.get('success_bg', "#90EE90")
        if label.winfo_exists(): label.config(bg=bg, fg=self.app.get_contrast_color(bg), bd=border_width)

    # apply_grid_colors kann als Fallback bleiben
    def apply_grid_colors(self, year, month):
         print("[Renderer] Wende Farben auf gesamtes Grid an (Fallback)...")
         # (Implementierung wie im vorherigen Schritt)


    def print_shift_plan(self, year, month, month_name):
        """Erzeugt das HTML für den Druck und öffnet es im Browser."""
        # (Implementierung bleibt unverändert, verwendet users_to_render)
        users = self.users_to_render
        if not users:
             messagebox.showinfo("Drucken", "Keine Benutzer zum Drucken vorhanden.", parent=self.master)
             return

        # Hole aktuelle Daten aus dem DM
        shifts_data = self.dm.shift_schedule_data
        wunschfrei_data = self.dm.wunschfrei_data
        processed_vacations = self.dm.processed_vacations
        rules = self.app.staffing_rules.get('Colors', {})
        weekend_bg = rules.get('weekend_bg', "#EAF4FF")
        holiday_bg = rules.get('holiday_bg', "#FFD700")
        violation_bg = rules.get('violation_bg', "#FF5555") # Für Druck

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
        """
        days_in_month = calendar.monthrange(year, month)[1]
        day_map = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            day_class = "day-col"
            if self.app.is_holiday(current_date): day_class += " holiday"
            elif current_date.weekday() >= 5: day_class += " weekend"
            html += f'<th class="{day_class}">{day}<br>{day_map[current_date.weekday()]}</th>'
        html += '<th class="hours-col">Std.</th></tr></thead><tbody>'

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
                display_text_from_schedule = shifts_data.get(user_id_str, {}).get(date_str, "&nbsp;") # &nbsp; für leere Zellen
                vacation_status = processed_vacations.get(user_id_str, {}).get(current_date)
                request_info = wunschfrei_data.get(user_id_str, {}).get(date_str)

                # Logik zur Bestimmung des finalen Textes (wie im Grid)
                final_display_text = display_text_from_schedule
                if vacation_status == 'Genehmigt': final_display_text = 'U'
                elif vacation_status == 'Ausstehend': final_display_text = "U?"
                elif request_info:
                     status, requested_shift, requested_by, _ = request_info
                     if status == 'Ausstehend':
                          if requested_by == 'admin': final_display_text = f"{requested_shift}(A)?"
                          else:
                               if requested_shift == 'WF': final_display_text = 'WF'
                               elif requested_shift == 'T/N': final_display_text = 'T/N?'
                               else: final_display_text = f"{requested_shift}?"
                     elif ("Akzeptiert" in status or "Genehmigt" in status) and requested_shift == 'WF' and display_text_from_schedule == "&nbsp;":
                          final_display_text = 'X'

                # --- KORREKTUR 4 (von 4) ---
                # .replace("T.", "T").replace("N.", "N") entfernt.
                shift_abbrev_for_style = final_display_text.replace("&nbsp;", "").replace("?", "").replace("(A)", "").replace("T./N.", "T/N").replace("WF","X")
                # --- KORREKTUR ENDE ---
                td_class = "day-col"; is_weekend = current_date.weekday() >= 5; is_holiday = self.app.is_holiday(current_date)
                is_violation = (user['id'], day) in self.dm.violation_cells

                bg_color_style = ""
                if is_violation: td_class += " violation"
                else:
                    bg_color = ""
                    if is_holiday: bg_color = holiday_bg
                    elif is_weekend: bg_color = weekend_bg
                    shift_data = self.app.shift_types_data.get(shift_abbrev_for_style)
                    if shift_data and shift_data.get('color'):
                         if shift_abbrev_for_style in ["U", "X", "EU"]: bg_color = shift_data['color']
                         elif not is_holiday and not is_weekend: bg_color = shift_data['color']
                    if final_display_text == "U?": bg_color = rules.get('Ausstehend', 'orange')
                    elif request_info and request_info[0] == 'Ausstehend' and ("?" in final_display_text or final_display_text == "WF"):
                         bg_color = rules.get('Admin_Ausstehend', '#E0B0FF') if request_info[2] == 'admin' else rules.get('Ausstehend', 'orange')
                    if bg_color:
                         fg_color = self.app.get_contrast_color(bg_color)
                         bg_color_style = f' style="background-color: {bg_color}; color: {fg_color};"'
                    if not bg_color_style and shift_abbrev_for_style in self.app.shift_types_data:
                         td_class += f" shift-{shift_abbrev_for_style}"
                html += f'<td class="{td_class}"{bg_color_style}>{final_display_text}</td>'
            html += f'<td class="hours-col">{total_hours}</td></tr>'
        html += """</tbody></table></body></html>"""

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
                f.write(html); filepath = f.name
            webbrowser.open(f"file://{os.path.realpath(filepath)}")
            messagebox.showinfo("Drucken",
                                "Der Dienstplan wurde in deinem Webbrowser geöffnet.\n\n"
                                "Nutze dort die Druckfunktion (Strg+P).\n\n"
                                "Datei: " + filepath, parent=self.master)
        except Exception as e:
            messagebox.showerror("Fehler", f"Plan konnte nicht zum Drucken geöffnet werden:\n{e}", parent=self.master)