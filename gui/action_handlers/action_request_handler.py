# gui/action_handlers/action_request_handler.py
# NEU: Ausgelagerte Logik für die Bearbeitung von Wunschanfragen (Regel 4)

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

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
        """Zeigt das Admin-Kontextmenü für Wunschanfragen."""
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

    def handle_request_accept_x(self, request_id, user_id, date_str):
        """Setzt Schicht auf 'X', aktualisiert Status und UI gezielt."""
        success, msg = update_wunschfrei_status(request_id, "Akzeptiert")
        if success:
            # Aktualisiere wunschfrei_data Cache im DM (via updater)
            self.updater.update_dm_wunschfrei_cache(user_id, date_str, "Akzeptiert", "WF", 'user')

            old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
            save_success, save_msg = save_shift_entry(user_id, date_str, "X", keep_request_record=True)

            if save_success:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, "X")
                except ValueError:
                    messagebox.showerror("Fehler", "Datumsfehler.", parent=self.tab)

                # App-Frequenz-Update
                if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency:
                    self.app.shift_frequency[old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)
                if "X" not in self.app.shift_frequency: self.app.shift_frequency["X"] = 0
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
            self.updater.update_dm_wunschfrei_cache(user_id, date_str, "Genehmigt", shift_to_set, 'admin')

            old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
            save_success, save_msg = save_shift_entry(user_id, date_str, shift_to_set, keep_request_record=True)

            if save_success:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, shift_to_set)
                except ValueError:
                    messagebox.showerror("Fehler", "Datumsfehler.", parent=self.tab)

                if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency:
                    self.app.shift_frequency[old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)
                if shift_to_set not in self.app.shift_frequency: self.app.shift_frequency[shift_to_set] = 0
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
            req_data = get_wunschfrei_request_by_id(request_id)
            req_type = req_data.get('requested_shift', 'WF') if req_data else 'WF'
            req_by = req_data.get('requested_by', 'user') if req_data else 'user'

            success, msg = update_wunschfrei_status(request_id, "Abgelehnt", reason)
            if success:
                self.updater.update_dm_wunschfrei_cache(user_id, date_str, "Abgelehnt", req_type, req_by, reason)

                old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
                save_success, save_msg = save_shift_entry(user_id, date_str, "",
                                                          keep_request_record=True)  # Setze auf Frei
                if save_success:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, "")  # Neuer Wert ""
                    except ValueError:
                        messagebox.showerror("Fehler", "Datumsfehler.", parent=self.tab)

                    if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency:
                        self.app.shift_frequency[old_shift_abbrev] = max(0,
                                                                         self.app.shift_frequency[old_shift_abbrev] - 1)

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
                if date_str and self.dm:
                    user_id_str = str(user_id)
                    if user_id_str in self.dm.wunschfrei_data and \
                            date_str in self.dm.wunschfrei_data[user_id_str]:
                        del self.dm.wunschfrei_data[user_id_str][date_str]
                        print(f"DM Cache für wunschfrei_data am {date_str} entfernt.")

                if request_data and (
                        "Akzeptiert" in request_data.get('status', '') or "Genehmigt" in request_data.get('status',
                                                                                                          '')):
                    accepted_shift = request_data['requested_shift']
                    shift_that_was_removed = "X" if accepted_shift == "WF" else accepted_shift

                if date_str:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        self.updater.trigger_targeted_update(user_id, date_obj, shift_that_was_removed, "")
                    except ValueError:
                        print(f"[FEHLER] Ungültiges Datum (delete): {date_str}")
                    except Exception as e:
                        print(f"Fehler bei UI Update nach Delete: {e}")
                else:
                    self.tab.refresh_plan()

                self._refresh_requests_tab_if_loaded()
                messagebox.showinfo("Erfolg", msg, parent=self.tab)
            else:
                messagebox.showerror("Fehler", f"Antrag löschen/zurückziehen fehlgeschlagen: {msg}", parent=self.tab)

    def reset_request_status(self, request_id):
        """Setzt Status zurück, entfernt ggf. Schicht und aktualisiert UI gezielt."""
        request_data = get_wunschfrei_request_by_id(request_id)
        if not request_data:
            messagebox.showerror("Fehler", "Antrag nicht gefunden.", parent=self.tab);
            return

        success, msg = update_wunschfrei_status(request_id, "Ausstehend", None)
        if success:
            shift_that_was_removed = ""
            user_id = request_data['user_id'];
            date_str = request_data['request_date']
            req_type = request_data.get('requested_shift', 'WF')
            req_by = request_data.get('requested_by', 'user')

            self.updater.update_dm_wunschfrei_cache(user_id, date_str, "Ausstehend", req_type, req_by)

            if "Akzeptiert" in request_data.get('status', '') or "Genehmigt" in request_data.get('status', ''):
                accepted_shift = request_data['requested_shift']
                shift_that_was_removed = "X" if accepted_shift == "WF" else accepted_shift
                save_success, save_msg = save_shift_entry(user_id, date_str, "")  # Setze auf Frei
                if not save_success:
                    messagebox.showwarning("Fehler",
                                           f"Status zurückgesetzt, Schicht entfernen fehlgeschlagen: {save_msg}",
                                           parent=self.tab)

            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                self.updater.trigger_targeted_update(user_id, date_obj, shift_that_was_removed, "")
            except ValueError:
                print(f"[FEHLER] Ungültiges Datum (reset): {date_str}")
            except Exception as e:
                print(f"Fehler bei UI Update nach Reset: {e}")

            self._refresh_requests_tab_if_loaded()
        else:
            messagebox.showerror("Fehler", f"Status zurücksetzen fehlgeschlagen: {msg}", parent=self.tab)

    def admin_add_wunschfrei(self, user_id, date_str, request_type):
        """ Erstellt Admin-Wunschfrei-Antrag und aktualisiert UI gezielt. """
        print(f"Admin fügt Wunsch hinzu: User {user_id}, Datum {date_str}, Typ {request_type}")
        success, msg = admin_submit_request(user_id, date_str, request_type)
        if success:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                if self.renderer:
                    self.updater.update_dm_wunschfrei_cache(user_id, date_str, "Ausstehend", request_type, 'admin')
                    old_shift = self.updater.get_old_shift_from_ui(user_id, date_str)

                    # Trigger Update (setzt Text auf "(A)?"), aber ohne Schichtänderung
                    self.updater.trigger_targeted_update(user_id, date_obj, old_shift, "")

                else:
                    self.tab.refresh_plan()
            except Exception as e:
                print(f"Fehler bei UI Update nach admin_add_wunschfrei: {e}")
                self.tab.refresh_plan()

            self._refresh_requests_tab_if_loaded()
        else:
            messagebox.showerror("Fehler", f"Wunschfrei-Anfrage speichern fehlgeschlagen: {msg}", parent=self.tab)

    def _refresh_requests_tab_if_loaded(self):
        """Aktualisiert den RequestsTab, falls geladen."""
        if hasattr(self.app, 'refresh_specific_tab'):
            self.app.refresh_specific_tab("Wunschanfragen")
        else:
            if hasattr(self.tab, 'master') and hasattr(self.tab.master, 'master') and hasattr(self.tab.master.master,
                                                                                              'loaded_tabs'):
                notebook = self.tab.master.master
                if "Wunschanfragen" in notebook.loaded_tabs:
                    requests_tab = notebook.tab_frames.get("Wunschanfragen")
                    if requests_tab and hasattr(requests_tab, 'refresh_data'):
                        requests_tab.refresh_data()