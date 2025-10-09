# gui/tabs/vacation_requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_manager import get_pending_vacation_requests, update_vacation_request_status


class VacationRequestsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        pending_frame = ttk.LabelFrame(main_frame, text="Offene Urlaubsanträge", padding="10")
        pending_frame.pack(fill="both", expand=True)

        tree_container = ttk.Frame(pending_frame)
        tree_container.pack(fill="both", expand=True, side="left")

        self.tree = ttk.Treeview(tree_container, columns=("user", "start_date", "end_date"), show="headings")
        self.tree.heading("user", text="Mitarbeiter")
        self.tree.heading("start_date", text="Von")
        self.tree.heading("end_date", text="Bis")
        self.tree.pack(fill="both", expand=True)

        button_frame = ttk.Frame(pending_frame)
        button_frame.pack(side="left", fill="y", padx=10, pady=5)
        ttk.Button(button_frame, text="Genehmigen", command=lambda: self.process_selection(True)).pack(pady=5, fill="x")
        ttk.Button(button_frame, text="Ablehnen", command=lambda: self.process_selection(False)).pack(pady=5, fill="x")
        ttk.Button(button_frame, text="Aktualisieren", command=self.refresh_data).pack(side="bottom", pady=10)

    def refresh_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        requests = get_pending_vacation_requests()
        for req in requests:
            user_name = f"{req['vorname']} {req['name']}"
            start_date = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            end_date = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            self.tree.insert("", tk.END, iid=req['id'], values=(user_name, start_date, end_date))

    def process_selection(self, approve):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Urlaubsantrag aus.", parent=self)
            return

        request_id = int(selection[0])
        status = "Genehmigt" if approve else "Abgelehnt"

        success, message = update_vacation_request_status(request_id, status)
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_data()
            self.app.check_for_updates()  # Löst die Aktualisierung der Benachrichtigungen aus
        else:
            messagebox.showerror("Fehler", message, parent=self)