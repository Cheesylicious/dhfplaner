# gui/tabs/wunschfrei_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime

from database.db_manager import (
    get_pending_wunschfrei_requests, update_wunschfrei_status, save_shift_entry
)


class WunschfreiTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app

        columns = ("user", "date", "request_type")
        self.wunschfrei_tree = ttk.Treeview(self, columns=columns, show="headings")
        self.wunschfrei_tree.heading("user", text="Mitarbeiter")
        self.wunschfrei_tree.heading("date", text="Datum")
        self.wunschfrei_tree.heading("request_type", text="Anfrage")
        self.wunschfrei_tree.column("request_type", anchor="center", width=120)
        self.wunschfrei_tree.pack(fill="both", expand=True)
        self.wunschfrei_tree.tag_configure("Ausstehend", background="orange")

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Anfrage genehmigen", command=self.approve_wunschfrei).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Anfrage ablehnen", command=self.deny_wunschfrei).pack(side="left", padx=5)

        self.refresh_wunschfrei_tree()

    def refresh_wunschfrei_tree(self):
        for item in self.wunschfrei_tree.get_children():
            self.wunschfrei_tree.delete(item)
        pending_requests = get_pending_wunschfrei_requests()
        for req in pending_requests:
            full_name = f"{req['vorname']} {req['name']}".strip()
            date_obj = datetime.strptime(req['request_date'], '%Y-%m-%d')
            request_type = "Frei" if req.get('requested_shift') == 'WF' else req.get('requested_shift', 'Unbekannt')
            display_values = (full_name, date_obj.strftime('%d.%m.%Y'), request_type)
            self.wunschfrei_tree.insert("", tk.END, iid=req['id'], values=display_values, tags=("Ausstehend",))

        self.app.update_notification_indicators()

    def process_wunschfrei_request(self, approve):
        selection = self.wunschfrei_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Anfrage aus.", parent=self.app)
            return
        request_id = int(selection[0])
        self.process_wunschfrei_by_id(request_id, approve)

    def process_wunschfrei_by_id(self, request_id, approve):
        req_data = next((r for r in get_pending_wunschfrei_requests() if r['id'] == request_id), None)
        if not req_data:
            messagebox.showerror("Fehler", "Anfrage nicht mehr gefunden oder bereits bearbeitet.", parent=self.app)
            self.refresh_wunschfrei_tree()
            return

        user_id, request_date_str, requested_shift = req_data['user_id'], req_data['request_date'], req_data.get(
            'requested_shift')
        new_status = "Genehmigt" if approve else "Abgelehnt"
        rejection_reason = None

        if not approve:
            reason = simpledialog.askstring("Ablehnungsgrund", "Bitte geben Sie einen Grund für die Ablehnung an:",
                                            parent=self.app)
            if reason is None: return
            rejection_reason = reason.strip()

        success_status, msg_status = update_wunschfrei_status(request_id, new_status, reason=rejection_reason)
        if not success_status:
            messagebox.showerror("Fehler", f"Status konnte nicht aktualisiert werden: {msg_status}", parent=self.app)
            return

        shift_plan_tab = self.app.tab_frames.get("Schichtplan")
        if approve and shift_plan_tab:
            shift_to_save = 'X' if requested_shift == 'WF' else requested_shift
            if shift_to_save == 'X' and 'X' not in self.app.shift_types_data:
                messagebox.showwarning("Hinweis",
                                       "Die Schichtart 'X' für genehmigtes Wunschfrei existiert nicht. Es wird empfohlen, 'X' anzulegen.",
                                       parent=self.app)

            success_shift, msg_shift = save_shift_entry(user_id, request_date_str, shift_to_save)
            if not success_shift:
                messagebox.showerror("Fehler beim Eintragen", msg_shift, parent=self.app)
                update_wunschfrei_status(request_id, "Ausstehend")  # Rollback
                return

        # UI aktualisieren
        if shift_plan_tab:
            shift_plan_tab.build_shift_plan_grid(self.app.current_display_date.year,
                                                 self.app.current_display_date.month)

        action = "genehmigt" if approve else "abgelehnt"
        messagebox.showinfo("Erfolg",
                            f"Anfrage wurde {action}. Der Mitarbeiter wird beim nächsten Login benachrichtigt.",
                            parent=self.app)
        self.refresh_wunschfrei_tree()

    def approve_wunschfrei(self):
        self.process_wunschfrei_request(approve=True)

    def deny_wunschfrei(self):
        self.process_wunschfrei_request(approve=False)