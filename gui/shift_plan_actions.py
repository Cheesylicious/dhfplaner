import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

# KORRIGIERTER IMPORT: Nutzt wieder den ursprünglichen Namen
from database.db_shifts import save_shift_entry, delete_all_shifts_for_month
from database.db_requests import (admin_submit_request,
                                  get_wunschfrei_request_by_user_and_date,
                                  withdraw_wunschfrei_request,
                                  update_wunschfrei_status,
                                  get_wunschfrei_request_by_id)
from database.db_users import get_user_by_id
from .dialogs.rejection_reason_dialog import RejectionReasonDialog
from database.db_core import load_config_json
# NEU: Import des ShiftLockManagers
from gui.shift_lock_manager import ShiftLockManager
# --- NEUER IMPORT (INNOVATION) ---
from database.db_locks import delete_all_locks_for_month
# --- ENDE NEUER IMPORT ---

SHIFT_MENU_CONFIG_KEY = "SHIFT_DISPLAY_CONFIG"


class ShiftPlanActionHandler:
    """Verarbeitet Klicks und Aktionen im Dienstplan-Grid."""

    def __init__(self, master_tab, app_instance, shift_plan_tab, renderer_instance):
        self.tab = master_tab
        self.app = app_instance
        self.renderer = renderer_instance
        self._menu_config_cache = self._load_menu_config()
        # NEU: Lock Manager direkt über DataManager instanziieren
        # DataManager wird in ShiftPlanTab initialisiert und der Lock Manager dort instanziiert.
        # Dies setzt voraus, dass self.tab.data_manager bereits den ShiftLockManager enthält (siehe vorherige Korrekturen).
        self.shift_lock_manager = self.tab.data_manager.shift_lock_manager

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

        # NEUE SICHERHEITSREGEL: Darf gesperrte Schichten nicht manuell überschreiben/löschen
        lock_status = self.shift_lock_manager.get_lock_status(user_id, date_str)
        if lock_status and actual_shift_to_save != lock_status:
            messagebox.showwarning("Gesperrte Schicht",
                                   f"Diese Zelle ist als '{lock_status}' gesichert und kann nicht manuell geändert werden, bevor die Sicherung aufgehoben wird.",
                                   parent=self.tab)
            return

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

    # --- NEUE METHODEN ZUM SICHERN VON SCHICHTEN ---

    def _set_shift_lock_status(self, user_id, date_str, shift_abbrev, is_locked):
        """ Allgemeine Hilfsfunktion zum Sichern/Freigeben von Schichten. """
        # KORRIGIERTE ABFRAGE: Nutzt das Attribut, das in MainAdminWindow initialisiert werden sollte
        # Wir fragen user_id, dann current_user_id ab und nutzen None als Fallback
        # Dies behebt den AttributeError durch flexible Abfrage
        # Falls beide fehlen, wird die Fehlerbox angezeigt.
        admin_id = getattr(self.app, 'user_id', None) or getattr(self.app, 'current_user_id', None)

        # KORRIGIERTE FEHLERPRÜFUNG: Prüft auf None oder 0, um den Fehler abzufangen
        if not admin_id:
            # Zeige diese Box weiterhin an, da dies ein kritischer Fehler ist
            messagebox.showerror("Fehler", "Admin-ID nicht verfügbar. Bitte melden Sie sich erneut an.",
                                 parent=self.tab)
            return

        success, message = self.shift_lock_manager.set_lock_status(user_id, date_str, shift_abbrev, is_locked, admin_id)

        if success:
            # --- KORREKTUR: Pop-up entfernt ---
            # messagebox.showinfo("Erfolg", message, parent=self.tab)
            # --- ENDE KORREKTUR ---

            # Führt ein UI-Update durch, um die Lock-Indikatoren anzuzeigen
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                # Aktualisiert die betroffene Zelle, um das Lock-Icon anzuzeigen
                self.renderer.update_cell_display(user_id, date_obj.day, date_obj)
            except Exception as e:
                print(f"[FEHLER] Fehler bei UI-Update nach Lock-Status-Änderung: {e}")
                self.tab.refresh_plan()
        else:
            # --- KORREKTUR: Pop-up durch Konsolen-Log ersetzt ---
            # messagebox.showerror("Fehler", message, parent=self.tab)
            print(f"[FEHLER] Schicht sichern/freigeben fehlgeschlagen: {message}")
            # --- ENDE KORREKTUR ---

    def secure_shift(self, user_id, date_str, shift_abbrev):
        """ Sichert die aktuelle Schicht (T., N., 6). """
        self._set_shift_lock_status(user_id, date_str, shift_abbrev, is_locked=True)

    def unlock_shift(self, user_id, date_str):
        """ Gibt die gesicherte Schicht frei. """
        # Beim Freigeben ist die shift_abbrev leer, da der Lock-Eintrag entfernt wird.
        self._set_shift_lock_status(user_id, date_str, "", is_locked=False)

    # --- ENDE NEUE METHODEN ---

    # --- on_grid_cell_click (jetzt mit Lock-Optionen) ---
    def on_grid_cell_click(self, event, user_id, day, year, month):
        date_obj = date(year, month, day);
        date_str = date_obj.strftime('%Y-%m-%d')
        context_menu = tk.Menu(self.tab, tearoff=0)

        # Holen der aktuell angezeigten Schicht (aus Cache oder UI)
        current_shift = self.tab.data_manager.shift_schedule_data.get(str(user_id), {}).get(date_str)
        # Abrufen des Lock-Status
        lock_status = self.shift_lock_manager.get_lock_status(str(user_id), date_str)

        # 1. Normale Schicht-Auswahl (Nur wenn nicht gesperrt)
        if not lock_status:
            # Code für die normale Schichtauswahl (wie im Original)
            if not hasattr(self.tab, '_menu_item_cache') or not self.tab._menu_item_cache:
                if hasattr(self.tab, '_prepare_shift_menu_items'):
                    try:
                        self.tab._menu_item_cache = self.tab._prepare_shift_menu_items()
                    except Exception as e:
                        print(f"Cache-Fehler: {e}");
                        messagebox.showerror("Fehler", "Menü init failed.", parent=self.tab);
                        return
                else:
                    messagebox.showerror("Fehler", "Menü kann nicht erstellt werden.", parent=self.tab);
                    return

            if hasattr(self.tab, '_menu_item_cache') and self.tab._menu_item_cache:
                for abbrev, label_text in self.tab._menu_item_cache:
                    context_menu.add_command(label=label_text,
                                             command=lambda u=user_id, d=date_str,
                                                            s=abbrev: self.save_shift_entry_and_refresh(u, d, s))
            else:
                context_menu.add_command(label="Fehler Schichtladen", state="disabled")

            context_menu.add_separator();
            context_menu.add_command(label="FREI",
                                     command=lambda u=user_id, d=date_str: self.save_shift_entry_and_refresh(u, d, ""))

        # 2. Lock/Unlock Optionen (für Admin-Zwecke)

        # Prüfen, ob die aktuelle Schicht gesichert werden kann (Arbeitsschichten)
        securable_shifts = ["T.", "N.", "6"]
        # Feste Schichten sind ebenfalls sicherbar/sicher
        is_securable_or_fixed = current_shift in securable_shifts or current_shift in ["X", "QA", "S", "U", "EU", "WF",
                                                                                       "U?"]

        context_menu.add_separator()
        context_menu.add_command(label="Admin: Wunschfrei (WF)",
                                 command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'WF'))
        context_menu.add_command(label="Admin: Wunschschicht (T/N)",
                                 command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'T/N'))
        context_menu.add_separator()

        if lock_status:
            # UNLOCK-Option
            context_menu.add_command(label=f"🔓 Sicherung aufheben (war: {lock_status})", foreground="#007700",
                                     command=lambda u=user_id, d=date_str: self.unlock_shift(u, d))
        elif is_securable_or_fixed:
            # SECURE-Option
            shift_to_secure = current_shift if current_shift else ""
            if shift_to_secure:
                context_menu.add_command(label=f"🔒 Schicht sichern ({shift_to_secure})", foreground="#CC0000",
                                         command=lambda u=user_id, d=date_str, s=shift_to_secure: self.secure_shift(u,
                                                                                                                    d,
                                                                                                                    s))
            else:
                context_menu.add_command(label="🔒 Schicht sichern", state="disabled")

        context_menu.tk_popup(event.x_root, event.y_root)

    # --- (restliche Methoden bleiben unverändert) ---
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

    # --- FUNKTION ZUM LÖSCHEN DES GESAMTEN MONATSPLANS (Innovation) ---
    def delete_shift_plan_by_admin(self, year, month):
        """
        Fragt den Benutzer, ob der Schichtplan gelöscht werden soll und ruft die
        DB-Funktion auf, die bestimmte Schichten (X, S, QA, EU) ausschließt.
        (Wird von ShiftPlanTab._on_delete_month aufgerufen)
        """
        try:
            # KORRIGIERT: Holt EXCLUDED_SHIFTS_ON_DELETE nun vom korrekten Funktionsnamen
            excluded_shifts_str = ", ".join(delete_all_shifts_for_month.EXCLUDED_SHIFTS_ON_DELETE)
        except AttributeError:
            # Fallback
            excluded_shifts_str = "X, S, QA, EU"

            # Verbesserte Bestätigungsmeldung
        if not messagebox.askyesno(
                "Schichtplan löschen",
                f"Wollen Sie alle planbaren Schichten für {month:02d}/{year} wirklich löschen?\n\n"
                f"ACHTUNG: Genehmigte Schichten/Termine wie Urlaube, Wünsche und fixe Einträge "
                f"({excluded_shifts_str}) sowie Urlaubs- und Wunschanfragen werden NICHT gelöscht!"
        ):
            return

        # Annahme: Die Admin-ID ist in self.app.current_user_id gespeichert
        # Absicherung für den Fall, dass current_user_id nicht gesetzt ist
        current_admin_id = getattr(self.app, 'current_user_id', None)

        # KORRIGIERTER AUFRUF: Nutzt den ursprünglichen Funktionsnamen
        success, message = delete_all_shifts_for_month(year, month, current_admin_id)

        if success:
            messagebox.showinfo("Erfolg", message)
            # AKTUALISIERUNG: Ruft die robuste Gitter-Neuerstellung im ShiftPlanTab auf
            if hasattr(self.tab, 'build_shift_plan_grid'):
                self.tab.build_shift_plan_grid(year, month)
            else:
                # Fallback
                if hasattr(self.renderer, 'redraw_grid'):
                    self.renderer.redraw_grid()
                elif hasattr(self.tab, 'load_shifts_and_update_display'):
                    self.tab.load_shifts_and_update_display(year, month)
        else:
            messagebox.showerror("Fehler", f"Fehler beim Löschen des Plans:\n{message}")

    # --- ENDE FUNKTION LÖSCHEN ---


    # --- NEUE FUNKTION (INNOVATION) ---
    def unlock_all_shifts_for_month(self, year, month):
        """
        Hebt alle Schichtsicherungen (Locks) für den angegebenen Monat auf.
        (Wird von ShiftPlanTab._on_unlock_all_shifts aufgerufen)
        """
        # Admin-ID für das Logging holen
        admin_id = getattr(self.app, 'current_user_id', None)
        if not admin_id:
            messagebox.showerror("Fehler", "Admin-ID nicht gefunden. Aktion kann nicht geloggt werden.", parent=self.tab)
            return

        # 1. DB-Aufruf
        success, message = delete_all_locks_for_month(year, month, admin_id)

        if success:
            # 2. Lokalen Cache leeren (wichtig!)
            # Wir leeren den gesamten Cache, da er monatsbasiert ist
            if self.shift_lock_manager and hasattr(self.shift_lock_manager, 'locked_shifts'):
                self.shift_lock_manager.locked_shifts.clear()
                print(f"[Action] Lokaler ShiftLockManager-Cache für {month}/{year} geleert.")
            else:
                print(f"[WARNUNG] ShiftLockManager-Cache konnte nicht geleert werden.")

            messagebox.showinfo("Erfolg", message, parent=self.tab)

            # 3. UI komplett neu laden, um alle Lock-Icons zu entfernen
            if hasattr(self.tab, 'build_shift_plan_grid'):
                self.tab.build_shift_plan_grid(year, month)
            else:
                self.tab.refresh_plan() # Fallback
        else:
            messagebox.showerror("Fehler", f"Fehler beim Aufheben der Sicherungen:\n{message}", parent=self.tab)
    # --- ENDE NEUE FUNKTION ---


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