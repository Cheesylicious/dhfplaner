# gui/shift_plan_actions.py
import tkinter as tk
from tkinter import messagebox
from datetime import date
import threading

# DB Imports
from database.db_shifts import save_shift_entry
from database.db_requests import get_wunschfrei_request_by_user_and_date, admin_submit_request, update_wunschfrei_status
from gui.dialogs.rejection_reason_dialog import RejectionReasonDialog
from gui.admin_menu_config_manager import AdminMenuConfigManager


class ShiftPlanActionHandler:
    """
    Verantwortlich für alle Aktionen, die auf Benutzerinteraktion folgen (Klicks, Menüs)
    und Schreibzugriffe auf die Datenbank beinhalten.
    """

    def __init__(self, master, app, shift_plan_tab_instance, renderer):
        super().__init__()
        self.master = master  # Die ShiftPlanTab-Instanz
        self.app = app
        self.tab = shift_plan_tab_instance  # Für einen Full-Refresh
        self.renderer = renderer
        self._pending_update_lock = threading.Lock()

        # Cache für die Admin-Menü-Konfiguration
        self._menu_config_cache = self._load_initial_menu_config()

        # HINWEIS: Das vorberechnete Menü (_menu_item_cache) wird über self.tab._menu_item_cache abgerufen.

    def _load_initial_menu_config(self):
        """Lädt die Menü-Konfiguration einmalig beim Start."""
        all_abbrevs = list(self.app.shift_types_data.keys())
        return AdminMenuConfigManager.load_config(all_abbrevs)

    def _update_user_total_hours(self, user_id_str):
        """Aktualisiert nur die Stunden-Spalte in der UI."""
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        total_hours = self.renderer.dm.calculate_total_hours_for_user(user_id_str, year, month)
        total_hours_label = self.renderer.grid_widgets['user_totals'].get(user_id_str)
        if total_hours_label:
            total_hours_label.config(text=str(total_hours))

    def _update_daily_counts_for_day(self, day):
        """Aktualisiert nur die Besetzungszeilen in der UI."""
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        current_date = date(year, month, day)
        date_str = current_date.strftime('%Y-%m-%d')

        # Daten-Cache des DM aktualisieren und nutzen
        _, _, _, daily_counts_for_day = self.renderer.dm.load_and_process_data(year, month)

        for abbrev, day_map in self.renderer.grid_widgets['daily_counts'].items():
            if day in day_map:
                count_label = day_map[day]
                min_required = self.renderer.dm.get_min_staffing_for_date(current_date).get(abbrev)
                count = daily_counts_for_day.get(abbrev, 0)

                display_text = str(count)
                if abbrev != "6":
                    display_text = f"{count}/{min_required}" if min_required is not None else str(count)
                else:
                    is_friday = current_date.weekday() == 4
                    is_holiday = self.app.is_holiday(current_date)
                    if not is_friday or is_holiday:
                        display_text = ""

                count_label.config(text=display_text)

    def on_grid_cell_click(self, event, user_id, day, year, month):
        """
        Öffnet das Menü sofort (optimistisch). Die DB-Prüfung erfolgt jetzt erst beim Klick auf einen Menüpunkt.
        """
        shift_date_str = date(year, month, day).strftime('%Y-%m-%d')

        # 1. Hole den aktuellen Wert und die Koordinaten (schnelle UI-Operation)
        try:
            cell_widgets = self.renderer.grid_widgets['cells'][str(user_id)][day]
            current_shift = cell_widgets['label'].cget("text")
        except KeyError:
            current_shift = ""

            # 2. **SOFORTIGER MENÜAUFBAU** im Haupt-Thread. Die Latenz ist minimal, da keine DB-Checks mehr im Weg sind.
        self._open_menu_instantly(event.x_root, event.y_root, user_id, shift_date_str, current_shift)

    def _open_menu_instantly(self, x_root, y_root, user_id, shift_date_str, current_shift):
        """
        Zeichnet das Menü im Haupt-Thread aus dem vorberechneten Cache und zeigt es an.
        """
        context_menu = tk.Menu(self.master, tearoff=0)
        anfragen_menu = tk.Menu(context_menu, tearoff=0)

        # 1. Standard-Einträge hinzufügen
        context_menu.add_command(label="FREI (Dienst entfernen)",
                                 command=lambda: self._trigger_save_and_update(user_id, shift_date_str, current_shift,
                                                                               ""))
        context_menu.add_separator()

        # 2. Anfragen-Submenü erstellen
        context_menu.add_cascade(label="Anfragen", menu=anfragen_menu)
        anfragen_menu.add_command(label="Anfrage für 'T. oder N.'",
                                  command=lambda s="T/N": self._admin_request_shift(user_id, shift_date_str, s))
        anfragen_menu.add_separator()

        # 3. Menüeinträge aus dem CACHE hinzufügen (Extrem schnell!)
        # Wir greifen auf den vorberechneten Cache des ShiftPlanTab-Objekts zu.
        for abbrev, label_text in self.tab._menu_item_cache:
            # Command für Hauptmenü (Schicht eintragen)
            context_menu.add_command(label=label_text,
                                     command=lambda s=abbrev: self._trigger_save_and_update(user_id,
                                                                                            shift_date_str,
                                                                                            current_shift, s))
            # Command für Anfragen-Submenü
            anfragen_menu.add_command(label=label_text,
                                      command=lambda s=abbrev: self._admin_request_shift(user_id, shift_date_str, s))

        context_menu.post(x_root, y_root)

    def _trigger_save_and_update(self, user_id, date_str, old_shift, new_shift):
        """
        WIRD BEI KLICK AUF MENÜPUNKT AUSGELÖST.
        FÜHRT JETZT DIE BLOCKIERENDE WUNSCHFREI-PRÜFUNG DURCH!
        """
        # --- BLOCKIERENDER CHECK WIRD HIER DURCHGEFÜHRT (ca. 0,8s) ---
        request = get_wunschfrei_request_by_user_and_date(user_id, date_str)
        if request and request['status'] == 'Ausstehend' and request['requested_by'] == 'user':
            messagebox.showwarning("Aktion blockiert",
                                   "Sie können keine Schicht eintragen, da für diesen Tag bereits ein offener Wunschfrei-Antrag vorliegt.",
                                   parent=self.master)
            return
        # --- ENDE CHECK ---

        user_id_str = str(user_id)

        # 1. OPTIMISTISCHES UI-UPDATE: Zelle sofort ändern
        year, month, day = map(int, date_str.split('-'))
        cell_widgets = self.renderer.grid_widgets['cells'][user_id_str][day]
        cell_widgets['label'].config(text=new_shift)

        # 2. STARTEN DES ASYNCHRONEN SCHREIBVORGANGS
        threading.Thread(target=self._save_shift_in_thread,
                         args=(user_id, date_str, old_shift, new_shift, user_id_str, day)).start()

    def _save_shift_in_thread(self, user_id, date_str, old_shift, new_shift, user_id_str, day):
        """
        Führt den blockierenden DB-Schreibvorgang im Worker-Thread aus.
        """
        success, message = save_shift_entry(user_id, date_str, new_shift)

        # 1. Lokalen Daten-Cache aktualisieren (muss im Thread erfolgen, da dies die Daten betrifft)
        with self._pending_update_lock:
            if success:
                # App-Frequenz und Cache aktualisieren
                if new_shift and new_shift != "FREI":
                    self.app.shift_frequency[new_shift] = self.app.shift_frequency.get(new_shift, 0) + 1
                    self.app.save_shift_frequency()

                if user_id_str not in self.renderer.dm.shift_schedule_data:
                    self.renderer.dm.shift_schedule_data[user_id_str] = {}
                if new_shift:
                    self.renderer.dm.shift_schedule_data[user_id_str][date_str] = new_shift
                elif date_str in self.renderer.dm.shift_schedule_data[user_id_str]:
                    del self.renderer.dm.shift_schedule_data[user_id_str][date_str]

                # 2. Asynchronen UI-Update im Haupt-Thread triggern
                self.master.after(0, lambda: self._finalize_ui_update(user_id_str, date_str, day))

                # Update der Teilnahmen-Tabelle (falls vorhanden)
                if "Teilnahmen" in self.app.tab_frames and hasattr(self.app.tab_frames["Teilnahmen"], 'refresh_data'):
                    self.app.tab.after(0, self.app.tab_frames["Teilnahmen"].refresh_data)

            else:
                # 3. Fehlerbehandlung: UI auf alten Zustand zurücksetzen und Fehlermeldung zeigen
                self.master.after(0, lambda: self._handle_save_error(user_id_str, date_str, old_shift, message))

    def _finalize_ui_update(self, user_id_str, date_str, day):
        """Führt alle notwendigen UI-Updates im Haupt-Thread nach erfolgreichem Speichern durch."""
        year, month = self.app.current_display_date.year, self.app.current_display_date.month

        # 1. Berechnung und Anwendung der Stunden- und Zähler-Updates
        self._update_user_total_hours(user_id_str)
        self._update_daily_counts_for_day(day)

        # 2. Neuberechnung der Konfliktfarben
        self.renderer.dm.update_violation_set(year, month)
        self.renderer.apply_grid_colors(year, month)

    def _handle_save_error(self, user_id_str, date_str, old_shift, message):
        """Behandelt Fehler beim Speichern im Haupt-Thread."""
        year, month, day = map(int, date_str.split('-'))
        cell_widgets = self.renderer.grid_widgets['cells'][user_id_str][day]

        # UI-Zelle auf den alten Zustand zurücksetzen
        cell_widgets['label'].config(text=old_shift)

        messagebox.showerror("Fehler beim Speichern", message, parent=self.master)

        # Komplette UI zur Sicherheit neu laden (optional, falls Fehler schwerwiegend)
        self.tab.refresh_plan()

    def _admin_request_shift(self, user_id, shift_date_str, shift_abbrev):
        """Sendet eine Admin-Anfrage und aktualisiert das Grid."""
        success, message = admin_submit_request(user_id, shift_date_str, shift_abbrev)
        if success:
            messagebox.showinfo("Anfrage gesendet", message, parent=self.app)
            self.tab.refresh_plan()
        else:
            messagebox.showerror("Fehler", message, parent=self.app)

    def show_wunschfrei_context_menu(self, event, user_id, date_str):
        """Erstellt das Kontextmenü für die Bearbeitung von Wunschfrei-Anträgen (RECHTSKLICK)."""
        # Diese Funktion bleibt synchron, da sie für den Rechtsklick-Admin-Workflow verwendet wird.
        request = get_wunschfrei_request_by_user_and_date(user_id, date_str)
        if not request or request['status'] != 'Ausstehend': return

        context_menu = tk.Menu(self.master, tearoff=0)
        requested_shift = request.get('requested_shift')

        if requested_shift == 'T/N':
            context_menu.add_command(label="Als Tagdienst genehmigen",
                                     command=lambda: self._process_wish_request(request, "T."))
            context_menu.add_command(label="Als Nachtdienst genehmigen",
                                     command=lambda: self._process_wish_request(request, "N."))
            context_menu.add_separator()
            context_menu.add_command(label="Ablehnen",
                                     command=lambda: self._process_wish_request(request, "Abgelehnt"))
        else:
            shift_to_approve = 'X' if requested_shift == 'WF' else requested_shift
            context_menu.add_command(label=f"'{requested_shift}' genehmigen",
                                     command=lambda: self._process_wish_request(request, shift_to_approve))
            context_menu.add_command(label="Ablehnen",
                                     command=lambda: self._process_wish_request(request, "Abgelehnt"))

        context_menu.post(event.x_root, event.y_root)

    def _process_wish_request(self, request_info, action):
        """Genehmigt oder lehnt einen Wunschfrei-Antrag ab (DB-Schreibvorgang)."""
        user_id = request_info['user_id']
        date_str = request_info['request_date']
        request_id = request_info['id']

        if action == "Abgelehnt":
            dialog = RejectionReasonDialog(self.master)
            if dialog.result:
                reason = dialog.result
                update_wunschfrei_status(request_id, "Abgelehnt", reason)
                self.tab.refresh_plan()
        else:
            save_shift_entry(user_id, date_str, action, keep_request_record=True)
            update_wunschfrei_status(request_id, "Genehmigt")
            self.tab.refresh_plan()