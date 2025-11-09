# gui/action_handlers/action_request_handler.py
# NEU: Ausgelagerte Logik für die Bearbeitung von Wunschanfragen (Regel 4)
#
# --- INNOVATION (Regel 2): Latenz behoben ---
# Alle DB-Aktionen (admin_add, accept, reject, delete, reset)
# wurden auf asynchrone "Optimistic Updates" umgestellt.
# Die UI wird sofort aktualisiert (Cache + Renderer),
# während die DB-Aufrufe im Hintergrund laufen.
# Dies eliminiert das "Einfrieren" der UI bei langsamen Verbindungen.

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
import threading  # NEU: Für asynchrone Operationen

# DB-Importe für Wünsche
from database.db_requests import (admin_submit_request,
                                  get_wunschfrei_request_by_user_and_date,
                                  withdraw_wunschfrei_request,
                                  update_wunschfrei_status,
                                  get_wunschfrei_request_by_id)
from database.db_shifts import save_shift_entry
from database.db_users import get_user_by_id

# Dialog-Import
from ..dialogs.rejection_reason_dialog import RejectionReasonDialog


class ActionRequestHandler:
    """
    Verantwortlich für alle Aktionen im Zusammenhang mit Wunschanfragen
    (Kontextmenü anzeigen, Akzeptieren, Ablehnen, Löschen, Admin-Erstellung).
    """

    def __init__(self, tab, app_instance, renderer, data_manager, update_handler):
        self.tab = tab
        self.app = app_instance
        self.renderer = renderer
        self.dm = data_manager
        self.updater = update_handler  # Referenz auf den ActionUpdateHandler

    def show_wunschfrei_context_menu(self, event, user_id, date_str):
        """
        Zeigt das Admin-Kontextmenü für Wunschanfragen.
        (Diese Funktion bleibt synchron, da sie nur DB-Lesezugriffe
         oder den Aufbau des Menüs selbst durchführt)
        """
        # HINWEIS: get_wunschfrei_request_by_user_and_date ist ein DB-Lesezugriff.
        # Wenn dieser bei langsamer Verbindung spürbar > 100ms dauert,
        # müsste *sogar das Anzeigen des Menüs* asynchronisiert werden.
        # Aktuell gehen wir davon aus, dass Lesezugriffe schnell genug sind.
        request = get_wunschfrei_request_by_user_and_date(user_id, date_str);
        context_menu = tk.Menu(self.tab, tearoff=0)

        if not request:
            print(f"Keine Anfrage für User {user_id} am {date_str}, zeige Admin-Optionen.")
            context_menu.add_command(label="Admin: Wunschfrei (WF)",
                                     command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'WF'))
            context_menu.add_command(label="Admin: Wunschschicht (T/N)",
                                     command=lambda u=user_id, d=date_str: self.admin_add_wunschfrei(u, d, 'T/N'))
        else:
            request_id = request['id'];
            status = request['status'];
            requested_shift = request['requested_shift']
            # HINWEIS: get_user_by_id ist ebenfalls ein DB-Lesezugriff
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
            else:  # (Akzeptiert, Genehmigt, Abgelehnt)
                context_menu.add_command(label=f"Status: {status} ({requested_shift}) von {user_name}",
                                         state="disabled");
                context_menu.add_separator()
                context_menu.add_command(label="Zurücksetzen auf 'Ausstehend'",
                                         command=lambda rid=request_id: self.reset_request_status(rid))
                context_menu.add_command(label="Antrag löschen/zurückziehen", foreground="red",
                                         command=lambda rid=request_id, uid=user_id: self.handle_request_delete(rid,
                                                                                                                uid))

        context_menu.tk_popup(event.x_root, event.y_root)

    # --- 1. AKZEPTIEREN (X) (ASYNCHRON, REGEL 2) ---

    def handle_request_accept_x(self, request_id, user_id, date_str):
        """Setzt Schicht auf 'X' (Optimistic Update) und speichert asynchron."""

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
            new_shift_abbrev = "X"
            new_status = "Akzeptiert"

            # 1. OPTIMISTIC UI UPDATE
            self.updater.update_dm_wunschfrei_cache(user_id, date_str, new_status, "WF", 'user')
            self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, new_shift_abbrev)
            self._update_app_frequency(old_shift_abbrev, new_shift_abbrev)
            self._refresh_requests_tab_if_loaded()

            # 2. ASYNCHRONES SPEICHERN
            threading.Thread(
                target=self._task_accept_x,
                args=(request_id, user_id, date_str, date_obj, old_shift_abbrev, new_shift_abbrev, new_status),
                daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler im Optimistic Update (Accept X): {e}", parent=self.tab)

    def _task_accept_x(self, request_id, user_id, date_str, date_obj, old_shift, new_shift, new_status):
        """ (Worker-Thread) Führt die DB-Aufrufe für 'Accept X' aus. """
        success, msg = update_wunschfrei_status(request_id, new_status)
        if not success:
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, new_shift, old_shift, new_status,
                           "Ausstehend", msg)
            return

        save_success, save_msg = save_shift_entry(user_id, date_str, new_shift, keep_request_record=True)
        if not save_success:
            # Versuche, den Status-Update rückgängig zu machen (Best Effort)
            update_wunschfrei_status(request_id, "Ausstehend")
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, new_shift, old_shift, new_status,
                           "Ausstehend", save_msg)

    # --- 2. AKZEPTIEREN (SCHICHT) (ASYNCHRON, REGEL 2) ---

    def handle_request_accept_shift(self, request_id, user_id, date_str, shift_to_set):
        """Setzt Schicht (Optimistic Update) und speichert asynchron."""

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
            new_shift_abbrev = shift_to_set
            new_status = "Genehmigt"

            # 1. OPTIMISTIC UI UPDATE
            self.updater.update_dm_wunschfrei_cache(user_id, date_str, new_status, new_shift_abbrev, 'admin')
            self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, new_shift_abbrev)
            self._update_app_frequency(old_shift_abbrev, new_shift_abbrev)
            self._refresh_requests_tab_if_loaded()

            # 2. ASYNCHRONES SPEICHERN
            threading.Thread(
                target=self._task_accept_shift,
                args=(request_id, user_id, date_str, date_obj, old_shift_abbrev, new_shift_abbrev, new_status),
                daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler im Optimistic Update (Accept Shift): {e}", parent=self.tab)

    def _task_accept_shift(self, request_id, user_id, date_str, date_obj, old_shift, new_shift, new_status):
        """ (Worker-Thread) Führt die DB-Aufrufe für 'Accept Shift' aus. """
        success, msg = update_wunschfrei_status(request_id, new_status)
        if not success:
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, new_shift, old_shift, new_status,
                           "Ausstehend", msg)
            return

        save_success, save_msg = save_shift_entry(user_id, date_str, new_shift, keep_request_record=True)
        if not save_success:
            update_wunschfrei_status(request_id, "Ausstehend")  # Rollback
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, new_shift, old_shift, new_status,
                           "Ausstehend", save_msg)

    # --- 3. ABLEHNEN (ASYNCHRON, REGEL 2) ---

    def handle_request_reject(self, request_id, user_id, date_str):
        """Aktualisiert Status auf Abgelehnt (Optimistic Update) und speichert asynchron."""

        dialog = RejectionReasonDialog(self.tab);
        reason = dialog.reason
        if reason is None:
            return  # Abbruch durch Benutzer

        req_data = get_wunschfrei_request_by_id(request_id)  # (Bleibt synchron für Rollback-Daten)
        req_type = req_data.get('requested_shift', 'WF') if req_data else 'WF'
        req_by = req_data.get('requested_by', 'user') if req_data else 'user'

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
            new_shift_abbrev = ""  # Setze auf Frei
            new_status = "Abgelehnt"

            # 1. OPTIMISTIC UI UPDATE
            self.updater.update_dm_wunschfrei_cache(user_id, date_str, new_status, req_type, req_by, reason)
            self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, new_shift_abbrev)
            self._update_app_frequency(old_shift_abbrev, new_shift_abbrev)
            self._refresh_requests_tab_if_loaded()

            # 2. ASYNCHRONES SPEICHERN
            threading.Thread(
                target=self._task_reject,
                args=(request_id, user_id, date_str, date_obj, old_shift_abbrev, new_shift_abbrev, new_status, reason,
                      req_type, req_by),
                daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler im Optimistic Update (Reject): {e}", parent=self.tab)

    def _task_reject(self, request_id, user_id, date_str, date_obj, old_shift, new_shift, new_status, reason, req_type,
                     req_by):
        """ (Worker-Thread) Führt die DB-Aufrufe für 'Reject' aus. """
        success, msg = update_wunschfrei_status(request_id, new_status, reason)
        if not success:
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, new_shift, old_shift, new_status,
                           "Ausstehend", msg, req_type, req_by)
            return

        save_success, save_msg = save_shift_entry(user_id, date_str, new_shift, keep_request_record=True)
        if not save_success:
            update_wunschfrei_status(request_id, "Ausstehend")  # Rollback
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, new_shift, old_shift, new_status,
                           "Ausstehend", save_msg, req_type, req_by)

    # --- 4. LÖSCHEN (ASYNCHRON, REGEL 2) ---

    def handle_request_delete(self, request_id, user_id):
        """Löscht/Zieht einen Wunschfrei-Antrag zurück (Optimistic Update) und speichert asynchron."""

        if not messagebox.askyesno("Löschen/Zurückziehen bestätigen",
                                   "Möchten Sie diesen Antrag wirklich löschen oder zurückziehen?", parent=self.tab):
            return

        request_data = get_wunschfrei_request_by_id(request_id)  # (Synchron für Rollback-Daten)
        if not request_data:
            print(f"Antrag {request_id} nicht gefunden.")
            messagebox.showerror("Fehler", f"Antrag {request_id} nicht gefunden.", parent=self.tab)
            return

        date_str = request_data.get('request_date')
        old_status = request_data.get('status', 'Ausstehend')
        old_req_type = request_data.get('requested_shift', 'WF')
        old_req_by = request_data.get('requested_by', 'user')
        old_reason = request_data.get('reason')

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            shift_that_was_removed = ""
            if "Akzeptiert" in old_status or "Genehmigt" in old_status:
                shift_that_was_removed = "X" if old_req_type == "WF" else old_req_type

            # 1. OPTIMISTIC UI UPDATE
            # Entferne Eintrag aus wunschfrei_data Cache im DM
            if self.dm:
                user_id_str = str(user_id)
                if user_id_str in self.dm.wunschfrei_data and \
                        date_str in self.dm.wunschfrei_data[user_id_str]:
                    del self.dm.wunschfrei_data[user_id_str][date_str]
                    print(f"DM Cache für wunschfrei_data am {date_str} entfernt.")

            self.updater.trigger_targeted_update(user_id, date_obj, shift_that_was_removed, "")
            self._update_app_frequency(shift_that_was_removed, "")
            self._refresh_requests_tab_if_loaded()

            # 2. ASYNCHRONES SPEICHERN
            threading.Thread(
                target=self._task_delete,
                args=(request_id, user_id, date_obj, shift_that_was_removed, old_status, old_req_type, old_req_by,
                      old_reason),
                daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler im Optimistic Update (Delete): {e}", parent=self.tab)

    def _task_delete(self, request_id, user_id, date_obj, old_shift, old_status, old_req_type, old_req_by, old_reason):
        """ (Worker-Thread) Führt den DB-Aufruf für 'Delete' aus. """
        success, msg = withdraw_wunschfrei_request(request_id, user_id)

        if not success:
            # Rollback (Datenbank)
            # (Schwer, da admin_submit_request und update_wunschfrei_status benötigt werden,
            #  um den alten Zustand wiederherzustellen. Wir machen ein UI-Rollback)
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, "", old_shift, "Gelöscht", old_status,
                           msg, old_req_type, old_req_by, old_reason)
        else:
            # (Nur Info im Main-Thread anzeigen, wenn erfolgreich)
            self.tab.after(0, lambda: messagebox.showinfo("Erfolg", "Antrag erfolgreich gelöscht/zurückgezogen.",
                                                          parent=self.tab))

    # --- 5. ZURÜCKSETZEN (ASYNCHRON, REGEL 2) ---

    def reset_request_status(self, request_id):
        """Setzt Status zurück (Optimistic Update) und speichert asynchron."""

        request_data = get_wunschfrei_request_by_id(request_id)
        if not request_data:
            messagebox.showerror("Fehler", "Antrag nicht gefunden.", parent=self.tab);
            return

        user_id = request_data['user_id'];
        date_str = request_data['request_date']
        old_status = request_data.get('status', 'Ausstehend')
        req_type = request_data.get('requested_shift', 'WF')
        req_by = request_data.get('requested_by', 'user')
        new_status = "Ausstehend"

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            shift_that_was_removed = ""
            if "Akzeptiert" in old_status or "Genehmigt" in old_status:
                shift_that_was_removed = "X" if req_type == "WF" else req_type

            # 1. OPTIMISTIC UI UPDATE
            self.updater.update_dm_wunschfrei_cache(user_id, date_str, new_status, req_type, req_by)
            self.updater.trigger_targeted_update(user_id, date_obj, shift_that_was_removed, "")
            self._update_app_frequency(shift_that_was_removed, "")
            self._refresh_requests_tab_if_loaded()

            # 2. ASYNCHRONES SPEICHERN
            threading.Thread(
                target=self._task_reset,
                args=(request_id, user_id, date_str, date_obj, shift_that_was_removed, new_status, old_status, req_type,
                      req_by),
                daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler im Optimistic Update (Reset): {e}", parent=self.tab)

    def _task_reset(self, request_id, user_id, date_str, date_obj, old_shift, new_status, old_status, req_type, req_by):
        """ (Worker-Thread) Führt die DB-Aufrufe für 'Reset' aus. """
        success, msg = update_wunschfrei_status(request_id, new_status, None)
        if not success:
            self.tab.after(0, self._handle_request_failure, user_id, date_obj, "", old_shift, new_status, old_status,
                           msg, req_type, req_by)
            return

        if "Akzeptiert" in old_status or "Genehmigt" in old_status:
            save_success, save_msg = save_shift_entry(user_id, date_str, "")  # Setze auf Frei
            if not save_success:
                update_wunschfrei_status(request_id, old_status)  # Rollback
                self.tab.after(0, self._handle_request_failure, user_id, date_obj, "", old_shift, new_status,
                               old_status, save_msg, req_type, req_by)

    # --- 6. ADMIN WUNSCH HINZUFÜGEN (ASYNCHRON, REGEL 2) ---

    def admin_add_wunschfrei(self, user_id, date_str, request_type):
        """ Erstellt Admin-Wunschfrei-Antrag (Optimistic Update) und speichert asynchron. """
        print(f"Admin fügt Wunsch hinzu: User {user_id}, Datum {date_str}, Typ {request_type}")

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

            # 1. OPTIMISTIC UI UPDATE
            if self.renderer:
                self.updater.update_dm_wunschfrei_cache(user_id, date_str, "Ausstehend", request_type, 'admin')
                old_shift = self.updater.get_old_shift_from_ui(user_id, date_str)
                # Nur UI neu zeichnen, Schicht nicht ändern
                self.updater.trigger_targeted_update(user_id, date_obj, old_shift, old_shift)
            else:
                self.tab.refresh_plan()  # Fallback

            self._refresh_requests_tab_if_loaded()

            # 2. ASYNCHRONES SPEICHERN
            threading.Thread(
                target=self._task_admin_add_wunsch,
                args=(user_id, date_str, request_type, date_obj, old_shift),
                daemon=True
            ).start()

        except Exception as e:
            print(f"Fehler bei UI Update nach admin_add_wunschfrei: {e}")
            messagebox.showerror("Fehler", f"UI-Fehler vor dem Speichern: {e}", parent=self.tab)

    def _task_admin_add_wunsch(self, user_id, date_str, request_type, date_obj, old_shift):
        """ (Worker-Thread) Speichert den Admin-Wunsch in der DB. """
        success, msg = admin_submit_request(user_id, date_str, request_type)

        if not success:
            self.tab.after(0, self._handle_admin_add_wunsch_failure, user_id, date_str, date_obj, old_shift, msg)

    def _handle_admin_add_wunsch_failure(self, user_id, date_str, date_obj, old_shift, error_message):
        """ (Main-Thread) Rollback für fehlgeschlagenes Hinzufügen eines Admin-Wunsches. """
        print(f"ROLLBACK: Admin-Wunsch für {user_id}@{date_str} fehlgeschlagen.")
        messagebox.showerror("Speicherfehler (Rollback)",
                             f"Der Admin-Wunsch konnte nicht gespeichert werden.\n"
                             f"Fehler: {error_message}\n\n"
                             "Die Ansicht wird zurückgesetzt.",
                             parent=self.tab)
        try:
            if self.dm:
                user_id_str = str(user_id)
                if user_id_str in self.dm.wunschfrei_data and date_str in self.dm.wunschfrei_data[user_id_str]:
                    del self.dm.wunschfrei_data[user_id_str][date_str]

            self.updater.trigger_targeted_update(user_id, date_obj, old_shift, old_shift)
            self._refresh_requests_tab_if_loaded()
        except Exception as e:
            print(f"Kritischer Fehler im Admin-Wunsch-Rollback: {e}")

    # --- 7. GLOBALE HELFER ---

    def _refresh_requests_tab_if_loaded(self):
        """Aktualisiert den RequestsTab, falls geladen."""
        if hasattr(self.app, 'refresh_specific_tab'):
            self.app.refresh_specific_tab("Wunschanfragen")
        # (Der Fallback-Code war sehr komplex und potenziell fehleranfällig,
        #  die app.refresh_specific_tab-Methode ist der saubere Weg)

    def _update_app_frequency(self, old_shift, new_shift):
        """ Hilfsfunktion zur Aktualisierung des Schicht-Frequenz-Caches in der Haupt-App. """
        try:
            if old_shift and old_shift in self.app.shift_frequency:
                self.app.shift_frequency[old_shift] = max(0, self.app.shift_frequency[old_shift] - 1)

            if new_shift and new_shift in self.app.app.shift_types_data and new_shift not in ['U', 'X', 'EU']:
                if new_shift not in self.app.shift_frequency:
                    self.app.shift_frequency[new_shift] = 0
                self.app.shift_frequency[new_shift] += 1
        except Exception as e:
            print(f"Fehler beim Aktualisieren der App-Frequenz: {e}")

    def _handle_request_failure(self, user_id, date_obj, failed_new_shift, old_shift,
                                failed_new_status, old_status, error_message,
                                old_req_type=None, old_req_by=None, old_reason=None):
        """
        (Main-Thread) Zentrale Rollback-Funktion für alle fehlgeschlagenen
        Akzeptier-, Ablehn- oder Reset-Aktionen.
        """
        print(f"ROLLBACK wird ausgeführt für {user_id}@{date_obj.strftime('%Y-%m-%d')}")
        messagebox.showerror("Speicherfehler (Rollback)",
                             f"Die Aktion ({failed_new_status}) konnte nicht gespeichert werden.\n"
                             f"Fehler: {error_message}\n\n"
                             f"Die Ansicht wird auf '{old_shift}' (Status: {old_status}) zurückgesetzt.",
                             parent=self.tab)

        try:
            # 1. UI-Schicht zurücksetzen
            self.updater.trigger_targeted_update(user_id, date_obj, failed_new_shift, old_shift)

            # 2. App-Frequenz zurücksetzen
            self._update_app_frequency(failed_new_shift, old_shift)

            # 3. DM-Wunsch-Cache zurücksetzen
            self.updater.update_dm_wunschfrei_cache(user_id, date_obj.strftime('%Y-%m-%d'),
                                                    old_status, old_req_type, old_req_by, old_reason)

            # 4. Anderen Tab aktualisieren
            self._refresh_requests_tab_if_loaded()

        except Exception as e:
            print(f"[FEHLER] KRITISCHER FEHLER im Request-Rollback: {e}")
            messagebox.showerror("Kritischer Rollback-Fehler",
                                 f"Das Rollback ist fehlgeschlagen: {e}\n"
                                 "Die Ansicht ist möglicherweise nicht mehr synchron mit der Datenbank.\n"
                                 "Bitte laden Sie den Monat neu (z.B. Monat wechseln).",
                                 parent=self.tab)