# gui/shift_plan_actions.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

from database.db_shifts import save_shift_entry
from database.db_requests import (admin_submit_request,
                                  get_wunschfrei_request_by_user_and_date,
                                  withdraw_wunschfrei_request,
                                  update_wunschfrei_status,
                                  get_wunschfrei_request_by_id)
from database.db_users import get_user_by_id
from .dialogs.rejection_reason_dialog import RejectionReasonDialog
from database.db_core import load_config_json

SHIFT_MENU_CONFIG_KEY = "SHIFT_DISPLAY_CONFIG"


class ShiftPlanActionHandler:
    """Verarbeitet Klicks und Aktionen im Dienstplan-Grid."""

    def __init__(self, master_tab, app_instance, shift_plan_tab, renderer_instance):
        self.tab = master_tab
        self.app = app_instance
        self.renderer = renderer_instance
        self._menu_config_cache = self._load_menu_config()

    def _load_menu_config(self):
        config = load_config_json(SHIFT_MENU_CONFIG_KEY)
        return config if config is not None else {}

    # --- ZENTRALE UPDATE FUNKTION ---
    def _trigger_targeted_update(self, user_id, date_obj, old_shift, new_shift):
        """Führt alle notwendigen Daten- und UI-Updates nach einer Änderung durch."""
        affected_conflict_cells = set()
        day = date_obj.day
        user_id_str = str(user_id)
        date_str = date_obj.strftime('%Y-%m-%d')  # Datum-String für Cache-Zugriff

        # Stelle sicher, dass old_shift und new_shift normalisiert sind (kein None)
        old_shift = old_shift if old_shift else ""
        new_shift = new_shift if new_shift else ""

        print(f"[_trigger_targeted_update] User: {user_id}, Date: {date_str}, Old: '{old_shift}', New: '{new_shift}'")

        try:
            # --- Daten im DM anpassen ---
            dm = self.tab.data_manager
            if not dm:
                print("[FEHLER] DataManager nicht verfügbar in _trigger_targeted_update.")
                raise Exception("DataManager nicht verfügbar.")

            # 1. Schichtplan-Cache aktualisieren
            if user_id_str not in dm.shift_schedule_data: dm.shift_schedule_data[user_id_str] = {}
            if not new_shift:  # FREI
                if date_str in dm.shift_schedule_data[user_id_str]:
                    print(f"  -> Entferne '{old_shift}' aus shift_schedule_data Cache für {user_id_str} am {date_str}")
                    del dm.shift_schedule_data[user_id_str][date_str]
            else:  # Neue Schicht eintragen/überschreiben
                print(f"  -> Setze '{new_shift}' in shift_schedule_data Cache für {user_id_str} am {date_str}")
                dm.shift_schedule_data[user_id_str][date_str] = new_shift

            # 2. Wunschfrei-Cache aktualisieren (falls nötig, z.B. wenn Status sich ändert)
            #    Diese Logik gehört eigentlich in die Methoden, die den Status ändern (accept/reject etc.)
            #    Hier gehen wir davon aus, dass der wunschfrei_data Cache *vor* dem Aufruf
            #    von _trigger_targeted_update bereits korrekt ist.
            #    Beim einfachen Setzen auf FREI muss der Wunschfrei-Status nicht geändert werden,
            #    aber wir müssen sicherstellen, dass die Anzeige in update_cell_display korrekt ist.

            # 3. Inkrementelles Konflikt-Update im DM
            print(f"  -> Rufe update_violations_incrementally auf...")
            updates = dm.update_violations_incrementally(user_id, date_obj, old_shift, new_shift)
            if updates: affected_conflict_cells.update(updates)

            # 4. Tageszählungen im DM aktualisieren
            print(f"  -> Rufe recalculate_daily_counts_for_day auf...")
            dm.recalculate_daily_counts_for_day(date_obj, old_shift, new_shift)


        except Exception as e:
            print(f"[FEHLER] Fehler bei Datenaktualisierung nach Speichern: {e}")
            messagebox.showwarning("Update-Fehler",
                                   f"Interne Daten konnten nicht vollständig aktualisiert werden:\n{e}\n\nUI wird möglicherweise inkonsistent.",
                                   parent=self.tab)

        # --- Gezielte UI-Updates über den Renderer ---
        if self.renderer:
            try:
                print("[Action] Starte gezielte UI-Updates...")
                if day > 0:
                    # Stelle sicher, dass die Daten für die Anzeige aktuell sind
                    # (Normalerweise durch die Schritte oben, aber zur Sicherheit)
                    self.renderer.shifts_data = dm.shift_schedule_data
                    self.renderer.wunschfrei_data = dm.wunschfrei_data
                    self.renderer.processed_vacations = dm.processed_vacations
                    self.renderer.daily_counts = dm.daily_counts

                    # Jetzt die UI-Updates
                    self.renderer.update_cell_display(user_id, day, date_obj)
                    self.renderer.update_user_total_hours(user_id)
                    self.renderer.update_daily_counts_for_day(day, date_obj)
                    self.renderer.update_conflict_markers(affected_conflict_cells)
                    print("[Action] Gezielte UI-Updates abgeschlossen.")
                    # Scrollregion neu berechnen
                    if self.tab.inner_frame.winfo_exists() and self.tab.canvas.winfo_exists():
                        self.tab.inner_frame.update_idletasks()
                        self.tab.canvas.configure(scrollregion=self.tab.canvas.bbox("all"))
                else:
                    print("[FEHLER] Ungültiger Tag (0) in _trigger_targeted_update.")

            except Exception as e:
                print(f"[FEHLER] Fehler bei gezieltem UI-Update: {e}")
                messagebox.showerror("UI Update Fehler",
                                     f"UI konnte nicht gezielt aktualisiert werden:\n{e}\n\nBitte manuell neu laden (Monat wechseln).",
                                     parent=self.tab)
        else:
            print("[FEHLER] Renderer nicht verfügbar für UI-Updates.")
            messagebox.showerror("Interner Fehler",
                                 "Renderer-Komponente nicht gefunden. UI kann nicht aktualisiert werden.",
                                 parent=self.tab)

    def save_shift_entry_and_refresh(self, user_id, date_str, shift_abbrev):
        """Speichert die Schicht und löst gezielte UI-Updates aus."""
        print(f"[Action] Speichere: User {user_id}, Datum {date_str}, Schicht '{shift_abbrev}'")
        old_shift_abbrev = ""
        day = 0
        try:
            day = int(date_str.split('-')[2])
            if self.renderer and hasattr(self.renderer, 'grid_widgets') and 'cells' in self.renderer.grid_widgets:
                cell_widgets = self.renderer.grid_widgets['cells'].get(str(user_id), {}).get(day)
                if cell_widgets and cell_widgets.get('label'):
                    current_text = cell_widgets['label'].cget("text")
                    # Normalisiere den alten Wert FÜR DIE BERECHNUNGEN (Konflikte, Zählung)
                    # --- KORREKTUR 1 (von 4) ---
                    # .replace("T.", "T").replace("N.", "N") entfernt.
                    old_shift_normalized = current_text.replace("?", "").replace(" (A)", "").replace("T./N.",
                                                                                                     "T/N").replace(
                        "WF", "X")
                    # --- KORREKTUR ENDE ---
                    if old_shift_normalized in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?', '&nbsp;']:
                        old_shift_abbrev = ""  # Zählt nicht als Schicht
                    else:
                        old_shift_abbrev = old_shift_normalized  # Ist eine echte Schicht
            else:
                print("[WARNUNG] Renderer/Widgets nicht bereit für alten Wert.")
        except Exception as e:
            print(f"[WARNUNG] Konnte alten Schichtwert nicht ermitteln: {e}")
            return

        # 1. Speichern in DB
        # Wichtig: shift_abbrev="" bedeutet "FREI" / Löschen in der DB
        actual_shift_to_save = shift_abbrev if shift_abbrev else ""
        success, message = save_shift_entry(user_id, date_str, actual_shift_to_save)

        if success:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

                # --- KORREKTUR (Wunschfrei-Cache leeren) START ---
                # Wenn auf "FREI" gesetzt wird, müssen wir den DM-Cache für wunschfrei
                # ebenfalls leeren, da save_shift_entry() (in db_shifts.py)
                # wahrscheinlich den DB-Eintrag für wunschfrei entfernt (wenn 'Ausstehend').
                if actual_shift_to_save == "":
                    if hasattr(self.tab, 'data_manager') and self.tab.data_manager:
                        dm = self.tab.data_manager
                        user_id_str = str(user_id)
                        if user_id_str in dm.wunschfrei_data and date_str in dm.wunschfrei_data[user_id_str]:
                            # Entferne den (vermutlich) 'Ausstehend' Eintrag aus dem Cache
                            del dm.wunschfrei_data[user_id_str][date_str]
                            print(f"[Action] 'FREI' gesetzt: Wunschfrei-Cache für {user_id_str} am {date_str} geleert.")
                # --- KORREKTUR ENDE ---

                # 2. Trigger die zentrale Update-Logik
                # new_shift ist hier der Wert, der im UI angezeigt werden soll (leer bei FREI)
                self._trigger_targeted_update(user_id, date_obj, old_shift_abbrev, actual_shift_to_save)
            except ValueError:
                print(f"[FEHLER] Ungültiges Datum für Update-Trigger: {date_str}")
                messagebox.showerror("Fehler", "Interner Datumsfehler. UI wird nicht aktualisiert.", parent=self.tab)

            # 3. Schichthäufigkeit aktualisieren
            if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency: self.app.shift_frequency[
                old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)
            # Zähle neue Schicht nur, wenn sie gültig ist (nicht leer, U, X etc.)
            if actual_shift_to_save and actual_shift_to_save in self.app.shift_types_data and actual_shift_to_save not in [
                'U', 'X', 'EU']:
                self.app.shift_frequency[actual_shift_to_save] += 1
        else:
            messagebox.showerror("Speicherfehler", message, parent=self.tab)

    # --- on_grid_cell_click (bleibt unverändert) ---
    def on_grid_cell_click(self, event, user_id, day, year, month):
        date_obj = date(year, month, day);
        date_str = date_obj.strftime('%Y-%m-%d')
        context_menu = tk.Menu(self.tab, tearoff=0)
        if not hasattr(self.tab, '_menu_item_cache') or not self.tab._menu_item_cache:
            print("[WARNUNG] Menü-Cache leer.");  # Gekürzt
            if hasattr(self.tab, '_prepare_shift_menu_items'):
                try:
                    self.tab._menu_item_cache = self.tab._prepare_shift_menu_items()
                except Exception as e:
                    print(f"Cache-Fehler: {e}"); messagebox.showerror("Fehler", "Menü init failed.",
                                                                      parent=self.tab); return
            else:
                messagebox.showerror("Fehler", "Menü kann nicht erstellt werden.", parent=self.tab); return
        if hasattr(self.tab, '_menu_item_cache') and self.tab._menu_item_cache:
            for abbrev, label_text in self.tab._menu_item_cache: context_menu.add_command(label=label_text,
                                                                                          command=lambda u=user_id,
                                                                                                         d=date_str,
                                                                                                         s=abbrev: self.save_shift_entry_and_refresh(
                                                                                              u, d, s))
        else:
            context_menu.add_command(label="Fehler Schichtladen", state="disabled")
        context_menu.add_separator();
        context_menu.add_command(label="FREI",
                                 command=lambda u=user_id, d=date_str: self.save_shift_entry_and_refresh(u, d, ""))
        context_menu.add_separator();
        context_menu.add_command(label="Admin: Wunschfrei (WF)",
                                 command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'WF'))

        # --- KORREKTUR TEXT ---
        context_menu.add_command(label="Admin: Wunschschicht (T/N)",
                                 command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'T/N'))
        # --- ENDE KORREKTUR ---

        context_menu.tk_popup(event.x_root, event.y_root)

    # --- show_wunschfrei_context_menu (bleibt unverändert) ---
    def show_wunschfrei_context_menu(self, event, user_id, date_str):
        request = get_wunschfrei_request_by_user_and_date(user_id, date_str);
        context_menu = tk.Menu(self.tab, tearoff=0)
        if not request:
            print(f"Keine Anfrage für User {user_id} am {date_str}, zeige Admin-Optionen.")
            context_menu.add_command(label="Admin: Wunschfrei (WF)",
                                     command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'WF'))

            # --- KORREKTUR TEXT ---
            context_menu.add_command(label="Admin: Wunschschicht (T/N)",
                                     command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'T/N'))
            # --- ENDE KORREKTUR ---

        else:
            request_id = request['id'];
            status = request['status'];
            requested_shift = request['requested_shift']
            user_info = get_user_by_id(user_id);
            user_name = f"{user_info['vorname']} {user_info['name']}" if user_info else f"User ID {user_id}"
            if status == 'Ausstehend':
                context_menu.add_command(label=f"Anfrage von {user_name} ({requested_shift})", state="disabled");
                context_menu.add_separator()
                if requested_shift == 'WF':
                    context_menu.add_command(label="Akzeptieren (X setzen)", command=lambda rid=request_id, u=user_id,
                                                                                            d=date_str: self.handle_request_accept_x(
                        rid, u, d))
                elif requested_shift == 'T/N':
                    context_menu.add_command(label="Akzeptieren (T. setzen)", command=lambda rid=request_id, u=user_id,
                                                                                             d=date_str: self.handle_request_accept_shift(
                        rid, u, d, "T."))
                    context_menu.add_command(label="Akzeptieren (N. setzen)", command=lambda rid=request_id, u=user_id,
                                                                                             d=date_str: self.handle_request_accept_shift(
                        rid, u, d, "N."))
                else:
                    context_menu.add_command(label=f"Akzeptieren ({requested_shift} setzen)",
                                             command=lambda rid=request_id, u=user_id, d=date_str,
                                                            s=requested_shift: self.handle_request_accept_shift(rid, u,
                                                                                                                d, s))
                context_menu.add_command(label="Ablehnen", command=lambda rid=request_id, u=user_id,
                                                                          d=date_str: self.handle_request_reject(rid, u,
                                                                                                                 d));
                context_menu.add_separator()
                context_menu.add_command(label="Antrag löschen/zurückziehen", foreground="red",
                                         command=lambda rid=request_id, uid=user_id: self.handle_request_delete(rid,
                                                                                                                uid))
            else:
                context_menu.add_command(label=f"Status: {status} ({requested_shift}) von {user_name}",
                                         state="disabled");
                context_menu.add_separator()
                context_menu.add_command(label="Zurücksetzen auf 'Ausstehend'",
                                         command=lambda rid=request_id: self.reset_request_status(rid))
                context_menu.add_command(label="Antrag löschen/zurückziehen", foreground="red",
                                         command=lambda rid=request_id, uid=user_id: self.handle_request_delete(rid,
                                                                                                                uid))
        context_menu.tk_popup(event.x_root, event.y_root)

    def handle_request_accept_x(self, request_id, user_id, date_str):
        """Setzt Schicht auf 'X', aktualisiert Status und UI gezielt."""
        success, msg = update_wunschfrei_status(request_id, "Akzeptiert")
        if success:
            # Aktualisiere wunschfrei_data Cache im DM
            self._update_dm_wunschfrei_cache(user_id, date_str, "Akzeptiert", "WF",
                                             'user')  # Annahme: User hat angefragt
            old_shift_abbrev = self._get_old_shift_from_ui(user_id, date_str)
            save_success, save_msg = save_shift_entry(user_id, date_str, "X", keep_request_record=True)
            if save_success:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    self._trigger_targeted_update(user_id, date_obj, old_shift_abbrev, "X")
                except ValueError:
                    messagebox.showerror("Fehler", "Datumsfehler.", parent=self.tab)
                if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency: self.app.shift_frequency[
                    old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)
                if "X" in self.app.shift_types_data: self.app.shift_frequency["X"] += 1
                self._refresh_requests_tab_if_loaded()
            else:
                messagebox.showerror("Fehler", f"Setzen auf 'X' fehlgeschlagen: {save_msg}", parent=self.tab)
        else:
            messagebox.showerror("Fehler", f"Status Update fehlgeschlagen: {msg}", parent=self.tab)

    def handle_request_accept_shift(self, request_id, user_id, date_str, shift_to_set):
        """Setzt Schicht, aktualisiert Status und UI gezielt."""
        success, msg = update_wunschfrei_status(request_id, "Genehmigt")
        if success:
            # Aktualisiere wunschfrei_data Cache im DM
            # Wer hat angefragt? Müssen wir aus DB holen oder annehmen. Annahme: Admin
            self._update_dm_wunschfrei_cache(user_id, date_str, "Genehmigt", shift_to_set, 'admin')
            old_shift_abbrev = self._get_old_shift_from_ui(user_id, date_str)
            save_success, save_msg = save_shift_entry(user_id, date_str, shift_to_set, keep_request_record=True)
            if save_success:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    self._trigger_targeted_update(user_id, date_obj, old_shift_abbrev, shift_to_set)
                except ValueError:
                    messagebox.showerror("Fehler", "Datumsfehler.", parent=self.tab)
                if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency: self.app.shift_frequency[
                    old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)
                if shift_to_set in self.app.shift_types_data: self.app.shift_frequency[shift_to_set] += 1
                self._refresh_requests_tab_if_loaded()
            else:
                messagebox.showerror("Fehler", f"Setzen auf '{shift_to_set}' fehlgeschlagen: {save_msg}",
                                     parent=self.tab)
        else:
            messagebox.showerror("Fehler", f"Status Update fehlgeschlagen: {msg}", parent=self.tab)

    def handle_request_reject(self, request_id, user_id, date_str):
        """Aktualisiert Status auf Abgelehnt, setzt Zelle auf Frei und aktualisiert UI gezielt."""
        dialog = RejectionReasonDialog(self.tab);
        reason = dialog.reason
        if reason is not None:
            # Hole Request-Typ bevor Status geändert wird
            req_data = get_wunschfrei_request_by_id(request_id)
            req_type = req_data.get('requested_shift', 'WF') if req_data else 'WF'
            req_by = req_data.get('requested_by', 'user') if req_data else 'user'

            success, msg = update_wunschfrei_status(request_id, "Abgelehnt", reason)
            if success:
                # Aktualisiere wunschfrei_data Cache im DM
                self._update_dm_wunschfrei_cache(user_id, date_str, "Abgelehnt", req_type, req_by, reason)
                old_shift_abbrev = self._get_old_shift_from_ui(user_id, date_str)
                save_success, save_msg = save_shift_entry(user_id, date_str, "",
                                                          keep_request_record=True)  # Setze auf Frei
                if save_success:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        self._trigger_targeted_update(user_id, date_obj, old_shift_abbrev, "")  # Neuer Wert ""
                    except ValueError:
                        messagebox.showerror("Fehler", "Datumsfehler.", parent=self.tab)
                    if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency: self.app.shift_frequency[
                        old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)
                    self._refresh_requests_tab_if_loaded()
                else:
                    messagebox.showerror("Fehler", f"Status aktualisiert, Zelle leeren fehlgeschlagen: {save_msg}",
                                         parent=self.tab)
            else:
                messagebox.showerror("Fehler", f"Status Update fehlgeschlagen: {msg}", parent=self.tab)

    def handle_request_delete(self, request_id, user_id):
        """Löscht/Zieht einen Wunschfrei-Antrag zurück und aktualisiert UI gezielt."""
        if messagebox.askyesno("Löschen/Zurückziehen bestätigen",
                               "Möchten Sie diesen Antrag wirklich löschen oder zurückziehen?", parent=self.tab):
            request_data = get_wunschfrei_request_by_id(request_id)
            if not request_data: print(f"Antrag {request_id} nicht gefunden.")

            success, msg = withdraw_wunschfrei_request(request_id, user_id)
            if success:
                shift_that_was_removed = ""
                date_str = request_data.get('request_date') if request_data else None

                # Entferne Eintrag aus wunschfrei_data Cache im DM
                if date_str and hasattr(self.tab, 'data_manager') and self.tab.data_manager:
                    user_id_str = str(user_id)
                    if user_id_str in self.tab.data_manager.wunschfrei_data and \
                            date_str in self.tab.data_manager.wunschfrei_data[user_id_str]:
                        del self.tab.data_manager.wunschfrei_data[user_id_str][date_str]
                        print(f"DM Cache für wunschfrei_data am {date_str} entfernt.")

                # Prüfe, ob Schicht entfernt wurde (passiert in DB-Funktion)
                if request_data and (
                        "Akzeptiert" in request_data.get('status', '') or "Genehmigt" in request_data.get('status',
                                                                                                          '')):
                    accepted_shift = request_data['requested_shift']
                    shift_that_was_removed = "X" if accepted_shift == "WF" else accepted_shift

                # Trigger UI Update (neuer Wert ist immer "")
                if date_str:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        self._trigger_targeted_update(user_id, date_obj, shift_that_was_removed, "")
                    except ValueError:
                        print(f"[FEHLER] Ungültiges Datum (delete): {date_str}")
                    except Exception as e:
                        print(f"Fehler bei UI Update nach Delete: {e}")
                else:  # Fallback, wenn Datum unbekannt
                    self.tab.refresh_plan()

                self._refresh_requests_tab_if_loaded()
                messagebox.showinfo("Erfolg", msg, parent=self.tab)
            else:
                messagebox.showerror("Fehler", f"Antrag löschen/zurückziehen fehlgeschlagen: {msg}", parent=self.tab)

    def reset_request_status(self, request_id):
        """Setzt Status zurück, entfernt ggf. Schicht und aktualisiert UI gezielt."""
        request_data = get_wunschfrei_request_by_id(request_id)
        if not request_data: messagebox.showerror("Fehler", "Antrag nicht gefunden.", parent=self.tab); return

        success, msg = update_wunschfrei_status(request_id, "Ausstehend", None)
        if success:
            shift_that_was_removed = ""
            user_id = request_data['user_id'];
            date_str = request_data['request_date']
            req_type = request_data.get('requested_shift', 'WF')
            req_by = request_data.get('requested_by', 'user')

            # Aktualisiere wunschfrei_data Cache im DM
            self._update_dm_wunschfrei_cache(user_id, date_str, "Ausstehend", req_type, req_by)

            if "Akzeptiert" in request_data.get('status', '') or "Genehmigt" in request_data.get('status', ''):
                accepted_shift = request_data['requested_shift']
                shift_that_was_removed = "X" if accepted_shift == "WF" else accepted_shift
                save_success, save_msg = save_shift_entry(user_id, date_str, "")  # Setze auf Frei
                if not save_success: messagebox.showwarning("Fehler",
                                                            f"Status zurückgesetzt, Schicht entfernen fehlgeschlagen: {save_msg}",
                                                            parent=self.tab)

            # Trigger UI Update
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                self._trigger_targeted_update(user_id, date_obj, shift_that_was_removed, "")  # Neuer Wert ""
            except ValueError:
                print(f"[FEHLER] Ungültiges Datum (reset): {date_str}")
            except Exception as e:
                print(f"Fehler bei UI Update nach Reset: {e}")

            self._refresh_requests_tab_if_loaded()
        else:
            messagebox.showerror("Fehler", f"Status zurücksetzen fehlgeschlagen: {msg}", parent=self.tab)

    def _refresh_requests_tab_if_loaded(self):
        """Aktualisiert den RequestsTab, falls geladen."""
        # Prüft, ob das Hauptfenster (AdminWindow) die Methode hat
        if hasattr(self.app, 'refresh_specific_tab'):
            # Ruft die Methode im AdminWindow auf
            self.app.refresh_specific_tab("Wunschanfragen")
        else:  # Fallback, falls die App-Referenz nicht das AdminWindow ist
            if hasattr(self.tab, 'master') and hasattr(self.tab.master, 'master') and hasattr(self.tab.master.master,
                                                                                              'loaded_tabs'):
                # Geht davon aus, dass master.master das Notebook ist
                notebook = self.tab.master.master
                if "Wunschanfragen" in notebook.loaded_tabs:
                    requests_tab = notebook.tab_frames.get("Wunschanfragen")
                    if requests_tab and hasattr(requests_tab, 'refresh_data'):
                        requests_tab.refresh_data()

    def admin_add_wunschfrei(self, user_id, date_str, request_type):
        """ Erstellt Admin-Wunschfrei-Antrag und aktualisiert UI gezielt. """
        print(f"Admin fügt Wunsch hinzu: User {user_id}, Datum {date_str}, Typ {request_type}")
        success, msg = admin_submit_request(user_id, date_str, request_type)
        if success:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                day = date_obj.day
                if self.renderer:
                    # Aktualisiere wunschfrei_data Cache im DM
                    self._update_dm_wunschfrei_cache(user_id, date_str, "Ausstehend", request_type, 'admin')

                    # Hole alten Wert (könnte eine Schicht sein) für _trigger_targeted_update
                    old_shift = self._get_old_shift_from_ui(user_id, date_str)

                    # Trigger Update für die Zelle (setzt Text auf "(A)?"),
                    # aber ohne Schichtänderung (new_shift="")
                    self._trigger_targeted_update(user_id, date_obj, old_shift, "")

                else:
                    self.tab.refresh_plan()  # Fallback
            except Exception as e:
                print(f"Fehler bei UI Update nach admin_add_wunschfrei: {e}")
                self.tab.refresh_plan()  # Fallback

            self._refresh_requests_tab_if_loaded()
        else:
            messagebox.showerror("Fehler", f"Wunschfrei-Anfrage speichern fehlgeschlagen: {msg}", parent=self.tab)

    # --- NEUE HILFSFUNKTIONEN ---
    def _get_old_shift_from_ui(self, user_id, date_str):
        """ Holt den normalisierten alten Schichtwert aus dem UI Label. """
        old_shift_abbrev = ""
        try:
            day = int(date_str.split('-')[2])
            if self.renderer and hasattr(self.renderer, 'grid_widgets') and 'cells' in self.renderer.grid_widgets:
                cell_widgets = self.renderer.grid_widgets['cells'].get(str(user_id), {}).get(day)
                if cell_widgets and cell_widgets.get('label'):
                    current_text = cell_widgets['label'].cget("text")
                    # Normalisiere für Berechnungen
                    # --- KORREKTUR 2 (von 4) ---
                    # .replace("T.", "T").replace("N.", "N") entfernt.
                    normalized = current_text.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF",
                                                                                                                   "X")
                    # --- KORREKTUR ENDE ---
                    if normalized not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?', '&nbsp;', '']:
                        old_shift_abbrev = normalized
        except Exception as e:
            print(f"[WARNUNG] _get_old_shift_from_ui: {e}")
        return old_shift_abbrev

    def _update_dm_wunschfrei_cache(self, user_id, date_str, status, req_shift, req_by, reason=None):
        """ Aktualisiert den wunschfrei_data Cache im DataManager. """
        try:
            if hasattr(self.tab, 'data_manager') and self.tab.data_manager:
                dm = self.tab.data_manager
                user_id_str = str(user_id)
                if user_id_str not in dm.wunschfrei_data: dm.wunschfrei_data[user_id_str] = {}
                # Update Cache mit Status, Typ, requested_by, None für Timestamp
                # WICHTIG: Grund (reason) wird in db_requests.py gespeichert, nicht im Cache hier?
                # Der Cache hier spiegelt wider, was für die Anzeige relevant ist.
                dm.wunschfrei_data[user_id_str][date_str] = (status, req_shift, req_by, None)
                print(f"DM Cache für wunschfrei_data aktualisiert: {dm.wunschfrei_data[user_id_str][date_str]}")
            else:
                print("[FEHLER] DataManager nicht gefunden für wunschfrei_data Cache Update.")
        except Exception as e:
            print(f"[FEHLER] Fehler beim Aktualisieren des wunschfrei_data Cache: {e}")