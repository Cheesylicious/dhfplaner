# gui/tabs/vacation_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
from datetime import date, datetime
from database.db_manager import add_vacation_request, get_requests_by_user


class VacationTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app
        self.user_data = app.user_data

        self.remaining_vacation_days = self.user_data.get('urlaub_rest', 0)

        info_frame = ttk.LabelFrame(self, text="Meine Übersicht", padding="10")
        info_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(info_frame, text=f"Verfügbare Urlaubstage: {self.remaining_vacation_days}",
                  font=("Arial", 12, "bold")).pack()

        request_frame = ttk.LabelFrame(self, text="Neuen Urlaub beantragen", padding="10")
        request_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(request_frame, text="Erster Urlaubstag:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.start_date_entry = DateEntry(request_frame, date_pattern='dd.mm.yyyy', mindate=date.today())
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(request_frame, text="Letzter Urlaubstag:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.end_date_entry = DateEntry(request_frame, date_pattern='dd.mm.yyyy', mindate=date.today())
        self.end_date_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(request_frame, text="Antrag stellen", command=self.submit_request).grid(row=2, column=0,
                                                                                           columnspan=2, pady=10)

        status_frame = ttk.LabelFrame(self, text="Meine Anträge", padding="10")
        status_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(status_frame, columns=("start_date", "end_date", "status"), show="headings")
        self.tree.heading("start_date", text="Von")
        self.tree.heading("end_date", text="Bis")
        self.tree.heading("status", text="Status")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("genehmigt", background="lightgreen")
        self.tree.tag_configure("ausstehend", background="khaki")
        self.tree.tag_configure("abgelehnt", background="lightcoral")

        self.load_requests()

    def load_requests(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        requests = get_requests_by_user(self.user_data['id'])
        for req in requests:
            start_date_obj = datetime.strptime(req['start_date'], '%Y-%m-%d')
            end_date_obj = datetime.strptime(req['end_date'], '%Y-%m-%d')
            display_values = (start_date_obj.strftime('%d.%m.%Y'), end_date_obj.strftime('%d.%m.%Y'), req['status'])
            self.tree.insert("", tk.END, values=display_values, tags=(req['status'].lower(),))

    def submit_request(self):
        start_date = self.start_date_entry.get_date()
        end_date = self.end_date_entry.get_date()
        if start_date > end_date:
            messagebox.showwarning("Fehler", "Das Startdatum muss vor dem Enddatum liegen.", parent=self)
            return
        if add_vacation_request(self.user_data['id'], start_date, end_date):
            messagebox.showinfo("Erfolg", "Ihr Antrag wurde erfolgreich eingereicht.", parent=self)
            self.load_requests()
        else:
            messagebox.showerror("Fehler", "Ihr Antrag konnte nicht gespeichert werden.", parent=self)