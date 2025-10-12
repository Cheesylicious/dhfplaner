# gui/tabs/vacation_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
from datetime import datetime, date

# --- Hier ist die Korrektur: aufgeteilt auf db_requests und db_users ---
from database.db_requests import add_vacation_request, get_requests_by_user
from database.db_users import get_user_by_id
# --- Ende der Korrektur ---

from ..request_lock_manager import RequestLockManager

class VacationTab(ttk.Frame):
    def __init__(self, master, user_data):
        super().__init__(master)
        self.user_data = user_data

        self.setup_ui()
        self.load_user_vacation_data()
        self.load_requests()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill='both')

        info_frame = ttk.LabelFrame(main_frame, text="Meine Urlaubstage", padding="10")
        info_frame.pack(fill='x', pady=5)
        self.vacation_days_label = ttk.Label(info_frame, text="", font=('Segoe UI', 10))
        self.vacation_days_label.pack()

        request_frame = ttk.LabelFrame(main_frame, text="Neuer Urlaubsantrag", padding="10")
        request_frame.pack(fill='x', pady=10)

        ttk.Label(request_frame, text="Von:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.start_date_entry = DateEntry(request_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd.mm.yyyy')
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(request_frame, text="Bis:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.end_date_entry = DateEntry(request_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd.mm.yyyy')
        self.end_date_entry.grid(row=0, column=3, padx=5, pady=5)

        submit_button = ttk.Button(request_frame, text="Antrag stellen", command=self.submit_request)
        submit_button.grid(row=0, column=4, padx=10, pady=5)

        history_frame = ttk.LabelFrame(main_frame, text="Meine Anträge", padding="10")
        history_frame.pack(expand=True, fill='both')

        self.tree = ttk.Treeview(history_frame, columns=('start_date', 'end_date', 'status'), show='headings')
        self.tree.heading('start_date', text='Von')
        self.tree.heading('end_date', text='Bis')
        self.tree.heading('status', text='Status')

        self.tree.tag_configure('Ausstehend', background='#FFF3CD')
        self.tree.tag_configure('Genehmigt', background='#D4EDDA')
        self.tree.tag_configure('Abgelehnt', background='#F8D7DA')
        self.tree.tag_configure('Storniert', background='#E0B0FF')

        self.tree.pack(expand=True, fill='both')

    def load_user_vacation_data(self):
        user = get_user_by_id(self.user_data['id'])
        if user:
            self.user_data['urlaub_gesamt'] = user['urlaub_gesamt']
            self.user_data['urlaub_rest'] = user['urlaub_rest']
            self.vacation_days_label.config(text=f"Gesamtanspruch: {user['urlaub_gesamt']} Tage | Resturlaub: {user['urlaub_rest']} Tage")

    def load_requests(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        requests = get_requests_by_user(self.user_data['id'])
        for req in requests:
            start_date = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            end_date = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            status = req['status']
            self.tree.insert('', 'end', values=(start_date, end_date, status), tags=(status,))

    def submit_request(self):
        start_date = self.start_date_entry.get_date()
        end_date = self.end_date_entry.get_date()

        if start_date > end_date:
            messagebox.showwarning("Ungültiges Datum", "Das Startdatum darf nicht nach dem Enddatum liegen.", parent=self)
            return

        months_to_check = set()
        temp_date = start_date
        while temp_date <= end_date:
            months_to_check.add((temp_date.year, temp_date.month))
            next_month = temp_date.month % 12 + 1
            next_year = temp_date.year + (temp_date.month // 12)
            temp_date = date(next_year, next_month, 1)

        for year, month in months_to_check:
            if RequestLockManager.is_month_locked(year, month):
                month_name = date(year, month, 1).strftime("%B")
                messagebox.showwarning("Anträge gesperrt", f"Der Monat {month_name} {year} ist für Anträge gesperrt.", parent=self)
                return

        if add_vacation_request(self.user_data['id'], start_date, end_date):
            messagebox.showinfo("Erfolg", "Urlaubsantrag wurde erfolgreich gestellt.", parent=self)
            self.load_requests()
        else:
            messagebox.showerror("Fehler", "Der Urlaubsantrag konnte nicht gestellt werden.", parent=self)

    def refresh_data(self):
        self.load_user_vacation_data()
        self.load_requests()