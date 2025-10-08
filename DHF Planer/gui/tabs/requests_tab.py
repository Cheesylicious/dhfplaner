# gui/tabs/requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from database import db_manager


class RequestsTab(ttk.Frame):
    def __init__(self, master, app_logic):
        super().__init__(master)
        self.app = app_logic
        self.all_requests = {}
        self.selected_request_id = None
        self.setup_ui()
        self.refresh_requests_tree()

    def setup_ui(self):
        # UI-Setup bleibt unverändert...
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        list_frame = ttk.Frame(main_pane, padding=5)
        self.setup_list_frame(list_frame)
        main_pane.add(list_frame, weight=1)
        details_frame = ttk.Frame(main_pane, padding=10)
        self.setup_details_frame(details_frame)
        main_pane.add(details_frame, weight=2)

    def setup_list_frame(self, parent):
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(top_frame, text="Offene Anträge", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, anchor="w")
        ttk.Button(top_frame, text="Aktualisieren", command=self.refresh_requests_tree).pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        cols = ("datum", "mitarbeiter", "wunsch")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.tree.heading("datum", text="Datum")
        self.tree.column("datum", width=100)
        self.tree.heading("mitarbeiter", text="Mitarbeiter")
        self.tree.column("mitarbeiter", width=150)
        self.tree.heading("wunsch", text="Wunsch")
        self.tree.column("wunsch", width=80, anchor="center")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_request_select)

    def setup_details_frame(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="Details zum Antrag", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2,
                                                                                         sticky="w", pady=(0, 10))
        self.detail_date_var = tk.StringVar()
        self.detail_user_var = tk.StringVar()
        self.detail_request_var = tk.StringVar()
        ttk.Label(parent, text="Datum:").grid(row=1, column=0, sticky="w")
        ttk.Label(parent, textvariable=self.detail_date_var).grid(row=1, column=1, sticky="w")
        ttk.Label(parent, text="Mitarbeiter:").grid(row=2, column=0, sticky="w")
        ttk.Label(parent, textvariable=self.detail_user_var).grid(row=2, column=1, sticky="w")
        ttk.Label(parent, text="Wunsch:").grid(row=3, column=0, sticky="w")
        ttk.Label(parent, textvariable=self.detail_request_var).grid(row=3, column=1, sticky="w")

        action_frame = ttk.Frame(parent, padding=(0, 20, 0, 0))
        action_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.approve_button = ttk.Button(action_frame, text="Genehmigen", command=lambda: self.process_request(True))
        self.approve_button.pack(side="left", padx=5)
        self.reject_button = ttk.Button(action_frame, text="Ablehnen", command=lambda: self.process_request(False))
        self.reject_button.pack(side="left", padx=5)

    def refresh_requests_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        requests = db_manager.get_pending_wunschfrei_requests()
        self.all_requests.clear()

        for req in requests:
            self.all_requests[req['id']] = req
            date_str = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            user_name = f"{req['vorname']} {req['name']}"
            request_type = req['requested_shift']
            self.tree.insert("", "end", iid=req['id'], values=(date_str, user_name, request_type))

        self.clear_details()
        # Ruft die neue Methode im Hauptfenster auf, um alle Zähler zu aktualisieren
        self.app.update_notification_indicators()

    def on_request_select(self, event):
        selection = self.tree.selection()
        if not selection:
            self.clear_details()
            return

        self.selected_request_id = int(selection[0])
        self.display_request_details(self.selected_request_id)

    def display_request_details(self, request_id):
        request = self.all_requests.get(request_id)
        if not request: return

        date_str = datetime.strptime(request['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
        self.detail_date_var.set(date_str)
        self.detail_user_var.set(f"{request['vorname']} {request['name']}")
        self.detail_request_var.set(request['requested_shift'])

    def clear_details(self):
        self.selected_request_id = None
        self.detail_date_var.set("")
        self.detail_user_var.set("")
        self.detail_request_var.set("")

    def process_request(self, approve):
        if self.selected_request_id is None:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie zuerst einen Antrag aus.", parent=self)
            return

        request_data = self.all_requests.get(self.selected_request_id)
        if not request_data: return

        if approve:
            new_status = 'Genehmigt'
            reason = None
            if request_data['requested_shift'] == 'WF':
                # Bei Genehmigung von "Wunschfrei" wird 'X' in den Plan eingetragen
                db_manager.save_shift_entry(request_data['user_id'], request_data['request_date'], 'X')
            else:
                # Bei Schichtwunsch wird die gewünschte Schicht eingetragen
                db_manager.save_shift_entry(request_data['user_id'], request_data['request_date'],
                                            request_data['requested_shift'])
        else:
            new_status = 'Abgelehnt'
            # Simpler Dialog zur Eingabe eines Ablehnungsgrundes
            from tkinter.simpledialog import askstring
            reason = askstring("Ablehnungsgrund", "Bitte geben Sie einen Grund für die Ablehnung an:", parent=self)

        success, msg = db_manager.update_wunschfrei_status(self.selected_request_id, new_status, reason)

        if success:
            messagebox.showinfo("Erfolg", f"Antrag wurde erfolgreich {new_status.lower()}.", parent=self)
            self.refresh_requests_tree()
            # Lade den Schichtplan neu, da sich Einträge geändert haben könnten
            self.app.reload_shift_plan()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Bearbeiten des Antrags:\n{msg}", parent=self)