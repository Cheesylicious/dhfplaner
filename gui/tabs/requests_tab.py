# gui/tabs/requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from database.db_requests import get_pending_wunschfrei_requests, update_wunschfrei_status
from database.db_shifts import save_shift_entry
from ..dialogs.rejection_reason_dialog import RejectionReasonDialog


class RequestsTab(ttk.Frame):
    def __init__(self, master, app, initial_data_cache=None):
        """
        Konstruktor für den RequestsTab.
        Akzeptiert optional vorgeladene Daten (pending_wishes), um DB-Wartezeiten zu vermeiden (Regel 2).
        """
        super().__init__(master)
        self.app = app
        self.all_requests_data = {}  # Wird jetzt als Cache (Dict) verwendet
        self.setup_ui()

        # --- INNOVATION (Regel 1 & 2) ---
        if initial_data_cache is not None:
            print("[RequestsTab] Lade Daten aus initialem Cache.")
            self._load_requests_from_cache(initial_data_cache)
        else:
            print("[RequestsTab] Initialer Cache leer. Lade aus DB (Fallback).")
            self.refresh_data()  # Daten aus DB holen und anzeigen
        # --- ENDE INNOVATION ---

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        pending_frame = ttk.LabelFrame(main_frame, text="Offene Anträge", padding="10")
        pending_frame.pack(fill="both", expand=True)

        tree_container = ttk.Frame(pending_frame)
        tree_container.pack(fill="both", expand=True, side="left")

        self.pending_requests_tree = ttk.Treeview(
            tree_container,
            columns=("user", "date", "request_type", "status"),
            show="headings"
        )
        self.pending_requests_tree.heading("user", text="Mitarbeiter")
        self.pending_requests_tree.heading("date", text="Datum")
        self.pending_requests_tree.heading("request_type", text="Anfrage")
        self.pending_requests_tree.heading("status", text="Status")
        self.pending_requests_tree.pack(fill="both", expand=True)

        button_frame = ttk.Frame(pending_frame)
        button_frame.pack(side="left", fill="y", padx=10, pady=5)
        ttk.Button(button_frame, text="Genehmigen", command=lambda: self.process_selection(True)).pack(pady=5, fill="x")
        ttk.Button(button_frame, text="Ablehnen", command=lambda: self.process_selection(False)).pack(pady=5, fill="x")

        # --- KORREKTUR: Ruft refresh_data() auf ---
        ttk.Button(button_frame, text="Aktualisieren", command=self.refresh_data).pack(side="bottom", pady=10)
        # --- ENDE KORREKTUR ---

    def _load_requests_from_cache(self, requests_list):
        """
        (NEUE METHODE) Füllt die Treeview mit der übergebenen Request-Liste.
        Diese Methode greift nicht auf die Datenbank zu. (Regel 2 & 4)
        """
        # Baum leeren
        for item in self.pending_requests_tree.get_children():
            self.pending_requests_tree.delete(item)

        # Internen Cache (Dict) leeren und neu aufbauen
        self.all_requests_data.clear()

        # Sortieren (z.B. nach Datum)
        try:
            sorted_requests = sorted(requests_list, key=lambda r: r.get('request_date', ''))
        except Exception:
            sorted_requests = requests_list  # Fallback

        for req in sorted_requests:
            req_id = req['id']
            # Internen Cache füllen, damit Bearbeitung funktioniert
            self.all_requests_data[req_id] = req

            user_name = f"{req['vorname']} {req['name']}"
            date_obj = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            req_type = "Frei" if req.get('requested_shift') == 'WF' else req.get('requested_shift')
            status = 'Ausstehend'
            values = (user_name, date_obj, req_type, status)
            self.pending_requests_tree.insert("", tk.END, iid=req_id, values=values)

    def refresh_data(self, data_cache=None):
        """
        (Ehemals refresh_requests) Aktualisiert die Daten.
        Nimmt optional einen Cache entgegen (Regel 2).
        Wenn kein Cache übergeben wird, lädt sie aus der DB (Fallback).
        """
        try:
            requests = []
            if data_cache is not None:
                print("[RequestsTab] Refresh aus Cache.")
                requests = data_cache
            else:
                print("[RequestsTab] Refresh aus DB.")
                # Fallback: Direkter DB-Aufruf
                requests = get_pending_wunschfrei_requests()

            # Daten in Treeview laden (ohne DB-Zugriff)
            self._load_requests_from_cache(requests)

        except Exception as e:
            messagebox.showerror("Fehler Laden", f"Wunschanfragen laden fehlgeschlagen:\n{e}", parent=self)

    def _get_selected_request_id(self):
        selection = self.pending_requests_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Antrag aus.", parent=self)
            return None
        return int(selection[0])

    def process_selection(self, approve):
        request_id = self._get_selected_request_id()
        if request_id is None:
            return

        reason = self._ask_for_rejection_reason_if_needed(approve)
        if reason is None:  # Benutzer hat bei Ablehnung auf "Abbrechen" geklickt
            return

        self._update_request_status(request_id, approve, reason)

    def _ask_for_rejection_reason_if_needed(self, approve):
        if not approve:
            dialog = RejectionReasonDialog(self)
            if dialog.result:
                return dialog.reason
            else:
                return None  # Signalisiert Abbruch
        return ""

    def _update_request_status(self, request_id, approve, reason=""):
        status = 'Genehmigt' if approve else 'Abgelehnt'
        success, message = update_wunschfrei_status(request_id, status, reason)
        if not success:
            messagebox.showerror("Datenbankfehler", message, parent=self)
            return

        if approve:
            request_details = self.all_requests_data.get(request_id)
            if request_details:
                user_id = request_details['user_id']
                date_str = request_details['request_date']
                shift = 'WF' if request_details['requested_shift'] == 'WF' else request_details['requested_shift']

                save_shift = 'X' if shift == 'WF' else shift

                save_success, save_message = save_shift_entry(user_id, date_str, save_shift)
                if not save_success:
                    messagebox.showerror("Fehler beim Eintragen", save_message, parent=self)

        messagebox.showinfo("Erfolg", message, parent=self)

        # --- KORREKTUR: Ruft refresh_data() auf (lädt aus DB neu) ---
        self.refresh_data()
        # --- ENDE KORREKTUR ---

        # --- INNOVATION (Regel 1 & 4): Tab-Manager für Refresh nutzen ---
        # Statt direkt auf den Schichtplan-Tab zuzugreifen,
        # wird der Tab-Manager gebeten, den Schichtplan zu aktualisieren.
        if hasattr(self.app, 'tab_manager'):
            print("[RequestsTab] Benachrichtige Tab-Manager, Schichtplan zu aktualisieren.")
            self.app.tab_manager.refresh_specific_tab("Schichtplan")
        else:
            print("[RequestsTab] Warnung: 'self.app.tab_manager' nicht gefunden.")
        # --- ENDE INNOVATION ---

    def process_wunschfrei_by_id(self, request_id, approve):
        if request_id not in self.all_requests_data:
            self.refresh_data()  # Lädt neu, wenn ID nicht im lokalen Cache ist
            if request_id not in self.all_requests_data:
                messagebox.showerror("Fehler", "Antrag nicht gefunden. Bitte aktualisieren Sie die Ansicht.",
                                     parent=self)
                return

        reason = self._ask_for_rejection_reason_if_needed(approve)
        if reason is None:
            return

        self._update_request_status(request_id, approve, reason)