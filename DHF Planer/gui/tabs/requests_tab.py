# gui/tabs/requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_manager import get_pending_requests


class RequestsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app

        columns = ("user", "start_date", "end_date", "status")
        self.request_tree = ttk.Treeview(self, columns=columns, show="headings")
        self.request_tree.heading("user", text="Mitarbeiter")
        self.request_tree.heading("start_date", text="Von")
        self.request_tree.heading("end_date", text="Bis")
        self.request_tree.heading("status", text="Status")
        self.request_tree.pack(fill="both", expand=True)
        self.request_tree.tag_configure("ausstehend", background="khaki")

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Antrag genehmigen", command=self.approve_request).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Antrag ablehnen", command=self.deny_request).pack(side="left", padx=5)

        self.refresh_requests_tree()

    def refresh_requests_tree(self):
        for item in self.request_tree.get_children():
            self.request_tree.delete(item)
        pending_requests = get_pending_requests()
        for req in pending_requests:
            full_name = f"{req['vorname']} {req['name']}".strip()
            start_date_obj = datetime.strptime(req['start_date'], '%Y-%m-%d')
            end_date_obj = datetime.strptime(req['end_date'], '%Y-%m-%d')
            display_values = (
                full_name, start_date_obj.strftime('%d.%m.%Y'), end_date_obj.strftime('%d.%m.%Y'), req['status'])
            self.request_tree.insert("", tk.END, iid=req['id'], values=display_values, tags=("ausstehend",))

        self.app.update_notification_indicators()

    def approve_request(self):
        messagebox.showinfo("Info", "Funktion 'Genehmigen' noch nicht implementiert.", parent=self.app)
        # Hier würde die Logik zum Genehmigen stehen, danach:
        # self.refresh_requests_tree()

    def deny_request(self):
        messagebox.showinfo("Info", "Funktion 'Ablehnen' noch nicht implementiert.", parent=self.app)
        # Hier würde die Logik zum Ablehnen stehen, danach:
        # self.refresh_requests_tree()