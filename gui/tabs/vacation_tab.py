# gui/tabs/vacation_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
from datetime import datetime, date
from database.db_manager import (
    add_vacation_request,
    get_requests_by_user,
    get_user_by_id
)

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

        # Frame for vacation days info
        info_frame = ttk.LabelFrame(main_frame, text="Meine Urlaubstage", padding="10")
        info_frame.pack(fill='x', pady=5)
        self.vacation_days_label = ttk.Label(info_frame, text="", font=('Segoe UI', 10))
        self.vacation_days_label.pack()

        # Frame for new request
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

        # Frame for existing requests
        history_frame = ttk.LabelFrame(main_frame, text="Meine Anträge", padding="10")
        history_frame.pack(expand=True, fill='both')

        self.tree = ttk.Treeview(history_frame, columns=('start_date', 'end_date', 'status'), show='headings')
        self.tree.heading('start_date', text='Von')
        self.tree.heading('end_date', text='Bis')
        self.tree.heading('status', text='Status')

        # Farben für die Status
        self.tree.tag_configure('Ausstehend', background='#FFF3CD')
        self.tree.tag_configure('Genehmigt', background='#D4EDDA')
        self.tree.tag_configure('Abgelehnt', background='#F8D7DA')
        self.tree.tag_configure('Storniert', background='#E0B0FF') # Lila

        self.tree.pack(expand=True, fill='both')

    def load_user_vacation_data(self):
        # Lade die Benutzerdaten bei Bedarf neu, um aktuelle Urlaubstage zu haben
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
            # Der Tag für die Farbe ist direkt der Status
            self.tree.insert('', 'end', values=(start_date, end_date, status), tags=(status,))

    def submit_request(self):
        start_date = self.start_date_entry.get_date()
        end_date = self.end_date_entry.get_date()

        if start_date > end_date:
            messagebox.showwarning("Ungültiges Datum", "Das Startdatum darf nicht nach dem Enddatum liegen.", parent=self)
            return

        if add_vacation_request(self.user_data['id'], start_date, end_date):
            messagebox.showinfo("Erfolg", "Urlaubsantrag wurde erfolgreich gestellt.", parent=self)
            self.load_requests()
        else:
            messagebox.showerror("Fehler", "Der Urlaubsantrag konnte nicht gestellt werden.", parent=self)

    def refresh_data(self):
        self.load_user_vacation_data()
        self.load_requests()