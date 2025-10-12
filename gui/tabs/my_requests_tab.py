# gui/tabs/my_requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
from tkcalendar import DateEntry
from database.db_requests import get_all_requests_by_user, withdraw_wunschfrei_request, submit_user_request
from database.db_shifts import get_all_shift_types
from ..request_lock_manager import RequestLockManager


class MyRequestsTab(ttk.Frame):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.user_data = user_data
        self.shift_types = [st['abbreviation'] for st in get_all_shift_types()]
        self.selected_request_id = None

        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        new_request_frame = ttk.LabelFrame(main_frame, text="Neuer Antrag", padding="10")
        new_request_frame.pack(fill="x", pady=(0, 10))
        new_request_frame.columnconfigure(1, weight=1)

        ttk.Label(new_request_frame, text="Datum:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.date_entry = DateEntry(new_request_frame, date_pattern='dd.mm.yyyy', width=12)
        self.date_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(new_request_frame, text="Schichtwunsch (optional):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.shift_combo = ttk.Combobox(new_request_frame, values=self.shift_types, state="readonly")
        self.shift_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        button_frame = ttk.Frame(new_request_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Wunschfrei beantragen", command=self.submit_frei_request).pack(side="left",
                                                                                                      padx=5)
        ttk.Button(button_frame, text="Schichtwunsch senden", command=self.submit_shift_request).pack(side="left",
                                                                                                      padx=5)

        requests_frame = ttk.LabelFrame(main_frame, text="Meine Anträge", padding="10")
        requests_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(requests_frame, columns=('Datum', 'Anfrage', 'Angefragt von', 'Status', 'Grund'),
                                 show='headings')
        self.tree.heading('Datum', text='Datum')
        self.tree.heading('Anfrage', text='Anfrage')
        self.tree.heading('Angefragt von', text='Angefragt von')
        self.tree.heading('Status', text='Status')
        self.tree.heading('Grund', text='Grund (bei Ablehnung)')
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.tag_configure('Ausstehend', background='#FFF3CD')
        self.tree.tag_configure('Akzeptiert von Admin', background='#D4EDDA')
        self.tree.tag_configure('Akzeptiert von Benutzer', background='#D4EDDA')
        self.tree.tag_configure('Abgelehnt von Admin', background='#F8D7DA')
        self.tree.tag_configure('Abgelehnt von Benutzer', background='#F8D7DA')

        scrollbar = ttk.Scrollbar(requests_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        ttk.Button(main_frame, text="Ausgewählten Antrag zurückziehen", command=self.withdraw_request).pack(pady=10)

    def refresh_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        requests = get_all_requests_by_user(self.user_data['id'])

        for req in requests:
            req_date = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            requested_by = "Admin" if req.get('requested_by') == 'admin' else "Benutzer"

            if requested_by == "Admin":
                anfrage = f"Anfrage vom Admin: {req['requested_shift']}"
            else:
                anfrage = "Wunschfrei" if req[
                                              'requested_shift'] == 'WF' else f"Eigener Wunsch: {req['requested_shift']}"

            reason = req.get('rejection_reason', '')
            status = req['status']

            self.tree.insert('', 'end', iid=req['id'], values=(req_date, anfrage, requested_by, status, reason),
                             tags=(status,))

    def submit_frei_request(self):
        req_date = self.date_entry.get_date()
        if RequestLockManager.is_month_locked(req_date.year, req_date.month):
            messagebox.showwarning("Anträge gesperrt", "Für diesen Monat können keine Anträge gestellt oder bestehende bearbeitet werden.", parent=self)
            return
        date_str = req_date.strftime('%Y-%m-%d')
        success, msg = submit_user_request(self.user_data['id'], date_str, requested_shift=None)
        if success:
            messagebox.showinfo("Erfolg", "Wunschfrei-Antrag wurde gestellt.", parent=self)
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", msg, parent=self)

    def submit_shift_request(self):
        shift = self.shift_combo.get()
        if not shift:
            messagebox.showwarning("Eingabe fehlt", "Bitte wählen Sie eine Schicht aus.", parent=self)
            return
        req_date = self.date_entry.get_date()
        if RequestLockManager.is_month_locked(req_date.year, req_date.month):
            messagebox.showwarning("Anträge gesperrt", "Für diesen Monat können keine Anträge gestellt oder bestehende bearbeitet werden.", parent=self)
            return
        date_str = req_date.strftime('%Y-%m-%d')
        success, msg = submit_user_request(self.user_data['id'], date_str, requested_shift=shift)
        if success:
            messagebox.showinfo("Erfolg",
                                f"Schichtwunsch '{shift}' wurde für den {req_date.strftime('%d.%m.%Y')} gestellt.",
                                parent=self)
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", msg, parent=self)

    def withdraw_request(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Antrag zum Zurückziehen aus.", parent=self)
            return

        item = self.tree.item(selected[0])
        date_str = item['values'][0]
        req_date = datetime.strptime(date_str, '%d.%m.%Y').date()

        if RequestLockManager.is_month_locked(req_date.year, req_date.month):
            messagebox.showwarning("Anträge gesperrt", "Für diesen Monat können keine Anträge gestellt oder bestehende bearbeitet werden.", parent=self)
            return

        request_id = selected[0]
        if messagebox.askyesno("Bestätigen", "Möchten Sie den ausgewählten Antrag wirklich zurückziehen?", parent=self):
            success, msg = withdraw_wunschfrei_request(request_id, self.user_data['id'])
            if success:
                messagebox.showinfo("Erfolg", msg, parent=self)
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", msg, parent=self)