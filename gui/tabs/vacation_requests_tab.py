# gui/tabs/vacation_requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_requests import (
    get_all_vacation_requests_for_admin,
    approve_vacation_request,
    update_vacation_request_status,
    cancel_vacation_request,
    archive_vacation_request,
    delete_vacation_requests
)


class VacationRequestsTab(ttk.Frame):
    def __init__(self, master, app, initial_data_count=None):
        """
        Konstruktor für den VacationRequestsTab.
        Akzeptiert optional die ANZAHL vorgeladener Anträge (Regel 2),
        um den TypeError zu beheben.
        HINWEIS: Der Tab lädt seine Details (die volle Liste) weiterhin selbst,
        da der Bootloader nur den Zähler liefert.
        """
        super().__init__(master)
        self.app = app
        self.admin_id = self.app.user_data['id']

        # initial_data_count (aus dem Cache) wird hier nicht aktiv
        # genutzt, aber die Annahme behebt den TypeError beim Laden.
        print(f"[VacationTab] Initialisiert (Cache-Zähler: {initial_data_count})")

        self.setup_ui()
        self.refresh_data()  # Lädt die vollen Daten aus der DB

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(button_frame, text="Genehmigen", command=self.approve_selected).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Ablehnen", command=self.reject_selected).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Stornieren", command=self.cancel_selected).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Archivieren", command=self.archive_selected).pack(side="left", padx=5)

        # --- KORREKTUR: Ruft refresh_data() auf ---
        ttk.Button(button_frame, text="Aktualisieren", command=self.refresh_data).pack(side="right",
                                                                                       padx=5)
        # --- ENDE KORREKTUR ---

        delete_button = ttk.Button(button_frame, text="Archivierte Anträge endgültig löschen",
                                   command=self.delete_selected_archived_requests)
        delete_button.pack(side="left", padx=20)

        self.tree = ttk.Treeview(main_frame, columns=('Name', 'Von', 'Bis', 'Status'), show='headings')
        self.tree.heading('Name', text='Name')
        self.tree.heading('Von', text='Von')
        self.tree.heading('Bis', text='Bis')
        self.tree.heading('Status', text='Status')
        self.tree.pack(fill="both", expand=True)

        self.tree.tag_configure('Ausstehend', background='#FFF3CD')
        self.tree.tag_configure('Genehmigt', background='#D4EDDA')
        self.tree.tag_configure('Abgelehnt', background='#F8D7DA')
        self.tree.tag_configure('Storniert', background='#E2E3E5')
        self.tree.tag_configure('Archiviert', foreground='grey')

    def refresh_data(self, data_cache=None):
        """
        (Ehemals refresh_vacation_requests) Aktualisiert die Daten.
        Nimmt optional einen Cache entgegen (Regel 2), der hier aber (da es nur
        ein Zähler ist) nicht verwendet wird. Lädt immer aus der DB.
        """
        if data_cache is not None:
            # data_cache ist nur der ZÄHLER, wir brauchen die vollen Daten.
            print("[VacationTab] Refresh (Cache ignoriert, da nur Zähler). Lade aus DB.")
        else:
            print("[VacationTab] Refresh aus DB.")

        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            requests = get_all_vacation_requests_for_admin()
            for req in requests:
                start_date = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
                end_date = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')

                tags = (req['status'],)
                if req['archived']:
                    tags = ('Archiviert',)

                self.tree.insert('', 'end', iid=req['id'],
                                 values=(f"{req['vorname']} {req['name']}", start_date, end_date, req['status']),
                                 tags=tags)
        except Exception as e:
            messagebox.showerror("Fehler Laden", f"Urlaubsanträge laden fehlgeschlagen:\n{e}", parent=self)

    def get_selected_request_ids(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie mindestens einen Antrag aus.", parent=self)
            return None
        return selected_items

    def approve_selected(self):
        selected_ids = self.get_selected_request_ids()
        if not selected_ids: return

        if messagebox.askyesno("Bestätigen", f"{len(selected_ids)} Antrag/Anträge genehmigen und im Plan eintragen?"):
            for req_id in selected_ids:
                approve_vacation_request(req_id, self.admin_id)
            self.refresh_data()

            # --- INNOVATION (Regel 1 & 4): Tab-Manager für Refresh nutzen ---
            if hasattr(self.app, 'tab_manager'):
                self.app.tab_manager.refresh_specific_tab("Schichtplan")
            # --- ENDE INNOVATION ---

    def reject_selected(self):
        selected_ids = self.get_selected_request_ids()
        if not selected_ids: return

        for req_id in selected_ids:
            update_vacation_request_status(req_id, 'Abgelehnt')
        self.refresh_data()

        # --- INNOVATION (Regel 1 & 4): Tab-Manager für Refresh nutzen ---
        if hasattr(self.app, 'tab_manager'):
            self.app.tab_manager.refresh_specific_tab("Schichtplan")
        # --- ENDE INNOVATION ---

    def cancel_selected(self):
        selected_ids = self.get_selected_request_ids()
        if not selected_ids: return

        if messagebox.askyesno("Bestätigen",
                               f"{len(selected_ids)} genehmigte(n) Antrag/Anträge stornieren und aus dem Plan entfernen?"):
            for req_id in selected_ids:
                cancel_vacation_request(req_id, self.admin_id)
            self.refresh_data()

            # --- INNOVATION (Regel 1 & 4): Tab-Manager für Refresh nutzen ---
            if hasattr(self.app, 'tab_manager'):
                self.app.tab_manager.refresh_specific_tab("Schichtplan")
            # --- ENDE INNOVATION ---

    def archive_selected(self):
        selected_ids = self.get_selected_request_ids()
        if not selected_ids: return

        for req_id in selected_ids:
            archive_vacation_request(req_id, self.admin_id)
        self.refresh_data()

    def delete_selected_archived_requests(self):
        selected_ids = self.get_selected_request_ids()
        if not selected_ids: return

        archived_to_delete = []
        for req_id in selected_ids:
            item = self.tree.item(req_id)
            if 'Archiviert' in item['tags']:
                archived_to_delete.append(req_id)

        if not archived_to_delete:
            messagebox.showwarning("Keine archivierten Anträge",
                                   "Nur archivierte Anträge können endgültig gelöscht werden.", parent=self)
            return

        if messagebox.askyesno("Endgültig löschen",
                               f"Möchten Sie {len(archived_to_delete)} archivierte(n) Antrag/Anträge wirklich endgültig löschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden und entfernt die Anträge auch aus dem Verlauf der Benutzer.",
                               parent=self, icon='warning'):
            success, msg = delete_vacation_requests(archived_to_delete)
            if success:
                messagebox.showinfo("Erfolg", msg, parent=self)
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", msg, parent=self)