# gui/tabs/my_requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_manager import get_all_requests_by_user, withdraw_wunschfrei_request


class MyRequestsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app
        self.wunschfrei_data_store = {}

        pending_frame = ttk.LabelFrame(self, text="Offene Anträge", padding=10)
        pending_frame.pack(fill="x", expand=False)
        pending_tree_frame = ttk.Frame(pending_frame)
        pending_tree_frame.pack(fill="x", expand=True)
        self.pending_requests_tree = ttk.Treeview(pending_tree_frame, columns=("date", "request_type", "status"),
                                                  show="headings", height=5)
        self.pending_requests_tree.heading("date", text="Datum")
        self.pending_requests_tree.heading("request_type", text="Anfrage")
        self.pending_requests_tree.heading("status", text="Status")
        self.pending_requests_tree.pack(fill="x", expand=True, side="left")
        self.pending_requests_tree.tag_configure("Ausstehend", background="orange")

        pending_button_frame = ttk.Frame(pending_tree_frame)
        pending_button_frame.pack(side="left", fill="y", padx=10)
        self.withdraw_button = ttk.Button(pending_button_frame, text="Zurückziehen",
                                          command=self.withdraw_selected_request)
        self.withdraw_button.pack(pady=5)

        self.archive_visible = tk.BooleanVar(value=True)
        self.toggle_archive_button = ttk.Button(self, text="Archiv ausblenden", command=self.toggle_archive_visibility)
        self.toggle_archive_button.pack(fill="x", pady=10)

        self.archive_frame = ttk.Frame(self)
        self.archive_frame.pack(fill="both", expand=True)
        processed_frame = ttk.LabelFrame(self.archive_frame, text="Bearbeitete Anträge (Archiv)", padding=10)
        processed_frame.pack(fill="both", expand=True)
        self.processed_requests_tree = ttk.Treeview(processed_frame, columns=("date", "request_type", "status"),
                                                    show="headings")
        self.processed_requests_tree.heading("date", text="Datum")
        self.processed_requests_tree.heading("request_type", text="Anfrage")
        self.processed_requests_tree.heading("status", text="Status")
        self.processed_requests_tree.pack(fill="both", expand=True)
        self.processed_requests_tree.tag_configure("Genehmigt", background="lightgreen")
        self.processed_requests_tree.tag_configure("Abgelehnt", background="lightcoral")

        self.pending_requests_tree.bind("<<TreeviewSelect>>", self.on_wunschfrei_selected)
        self.processed_requests_tree.bind("<<TreeviewSelect>>", self.on_wunschfrei_selected)

        self.refresh_wunschfrei_tab()

    def refresh_wunschfrei_tab(self):
        for tree in [self.pending_requests_tree, self.processed_requests_tree]:
            for item in tree.get_children():
                tree.delete(item)
        self.wunschfrei_data_store.clear()

        requests = get_all_requests_by_user(self.app.user_data['id'])
        for req in requests:
            self.wunschfrei_data_store[req['id']] = req
            date_obj = datetime.strptime(req['request_date'], '%Y-%m-%d')
            req_type = "Frei" if req.get('requested_shift') == 'WF' else req.get('requested_shift', 'Unbekannt')
            values = (date_obj.strftime('%d.%m.%Y'), req_type, req['status'])

            if req['status'] == 'Ausstehend':
                self.pending_requests_tree.insert("", tk.END, iid=req['id'], values=values, tags=(req['status'],))
            else:
                self.processed_requests_tree.insert("", tk.END, iid=req['id'], values=values, tags=(req['status'],))

    def withdraw_selected_request(self):
        selection = self.pending_requests_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen offenen Antrag zum Zurückziehen aus.",
                                   parent=self)
            return

        success, message = withdraw_wunschfrei_request(int(selection[0]), self.app.user_data['id'])
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_wunschfrei_tab()
            # Reload shift plan if it exists
            if "Schichtplan" in self.app.tab_frames:
                self.app.tab_frames["Schichtplan"].build_shift_plan_grid(self.app.current_display_date.year,
                                                                         self.app.current_display_date.month)
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def on_wunschfrei_selected(self, event):
        # You can add logic here to show details if needed
        pass

    def toggle_archive_visibility(self):
        if self.archive_visible.get():
            self.archive_frame.pack_forget()
            self.toggle_archive_button.config(text="Archiv einblenden")
            self.archive_visible.set(False)
        else:
            self.archive_frame.pack(fill="both", expand=True)
            self.toggle_archive_button.config(text="Archiv ausblenden")
            self.archive_visible.set(True)