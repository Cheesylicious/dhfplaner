# gui/tabs/vacation_requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_manager import (
    get_all_vacation_requests_for_admin, update_vacation_request_status, archive_vacation_request
)


class VacationRequestsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.current_filter = tk.StringVar(value="Offen")
        self.setup_ui()
        self.load_requests()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill='both')

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill='x', pady=5)

        ttk.Button(action_frame, text="Genehmigen", command=self.approve_request).pack(side='left')
        ttk.Button(action_frame, text="Ablehnen", command=self.reject_request).pack(side='left', padx=5)
        ttk.Button(action_frame, text="Archivieren", command=self.archive_request).pack(side='left')

        filter_frame = ttk.Frame(action_frame)
        filter_frame.pack(side='right')
        ttk.Label(filter_frame, text="Filter:").pack(side='left', padx=(0, 5))
        ttk.Radiobutton(filter_frame, text="Offen", variable=self.current_filter, value="Offen",
                        command=self.load_requests).pack(side='left')
        ttk.Radiobutton(filter_frame, text="Alle", variable=self.current_filter, value="Alle",
                        command=self.load_requests).pack(side='left', padx=5)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(expand=True, fill='both', pady=(10, 0))

        self.tree = ttk.Treeview(tree_frame, columns=('name', 'start_date', 'end_date', 'status'), show='headings')
        self.tree.heading('name', text='Mitarbeiter')
        self.tree.heading('start_date', text='Von')
        self.tree.heading('end_date', text='Bis')
        self.tree.heading('status', text='Status')

        self.tree.column('name', width=200)
        self.tree.column('start_date', width=120)
        self.tree.column('end_date', width=120)
        self.tree.column('status', width=100)

        # Farben definieren
        self.tree.tag_configure('Ausstehend', background='#FFF3CD')  # Hellgelb
        self.tree.tag_configure('Genehmigt', background='#D4EDDA')  # Hellgrün
        self.tree.tag_configure('Abgelehnt', background='#F8D7DA')  # Hellrot
        self.tree.tag_configure('Archiviert-Genehmigt', background='#E2F0E5', foreground='gray')  # Blassgrün
        self.tree.tag_configure('Archiviert-Abgelehnt', background='#F5E3E4', foreground='gray')  # Blassrot

        self.tree.pack(side='left', expand=True, fill='both')

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

    def load_requests(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        all_requests = get_all_vacation_requests_for_admin()

        for req in all_requests:
            filter_val = self.current_filter.get()
            status = req['status']
            archived = req['archived']

            if filter_val == "Offen" and status != 'Ausstehend':
                continue

            if filter_val == "Alle" and archived:
                continue

            tag = status
            display_status = status
            if archived:
                display_status = f"Archiviert ({status})"
                tag = f"Archiviert-{status}"

            start_date_formatted = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            end_date_formatted = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')

            self.tree.insert('', 'end', iid=req['id'], values=(
                f"{req['vorname']} {req['name']}",
                start_date_formatted,
                end_date_formatted,
                display_status
            ), tags=(tag,))

    def get_selected_request(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie zuerst einen Antrag aus.", parent=self)
            return None, None

        request_id = selected_items[0]
        item = self.tree.item(request_id)
        return request_id, item

    def approve_request(self):
        request_id, item = self.get_selected_request()
        if not request_id:
            return

        if 'Ausstehend' not in item['values'][3]:
            messagebox.showinfo("Information", "Nur ausstehende Anträge können genehmigt werden.", parent=self)
            return

        success, msg = update_vacation_request_status(request_id, "Genehmigt")
        if success:
            messagebox.showinfo("Erfolg", msg, parent=self)
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", msg, parent=self)

    def reject_request(self):
        request_id, item = self.get_selected_request()
        if not request_id:
            return

        if 'Ausstehend' not in item['values'][3]:
            messagebox.showinfo("Information", "Nur ausstehende Anträge können abgelehnt werden.", parent=self)
            return

        success, msg = update_vacation_request_status(request_id, "Abgelehnt")
        if success:
            messagebox.showinfo("Erfolg", msg, parent=self)
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", msg, parent=self)

    def archive_request(self):
        request_id, item = self.get_selected_request()
        if not request_id:
            return

        status = item['values'][3]
        if 'Genehmigt' not in status and 'Abgelehnt' not in status:
            messagebox.showinfo("Information",
                                "Nur bereits bearbeitete Anträge (genehmigt/abgelehnt) können archiviert werden.",
                                parent=self)
            return

        if messagebox.askyesno("Bestätigen",
                               f"Möchten Sie diesen '{status}'-Antrag wirklich archivieren?\nEventuell eingetragene Schichten ('EU'/'X') werden entfernt.",
                               parent=self):
            success, msg = archive_vacation_request(request_id, self.app.user_data['id'])
            if success:
                messagebox.showinfo("Erfolg", msg, parent=self)
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", msg, parent=self)

    def refresh_data(self):
        self.load_requests()
        self.app.refresh_all_tabs()