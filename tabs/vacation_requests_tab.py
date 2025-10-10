# gui/tabs/vacation_requests_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_manager import (
    get_all_vacation_requests_for_admin,
    update_vacation_request_status,
    archive_vacation_request,
    approve_vacation_request,
    cancel_vacation_request
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

        ttk.Button(action_frame, text="Genehmigen", command=self.approve_selected_request).pack(side='left')
        ttk.Button(action_frame, text="Ablehnen", command=self.reject_selected_request).pack(side='left', padx=5)
        ttk.Button(action_frame, text="Stornieren", command=self.cancel_selected_request, style="Storno.TButton").pack(side='left')
        ttk.Button(action_frame, text="Archivieren", command=self.archive_selected_request).pack(side='left', padx=5)

        # Style für den Stornieren-Button
        style = ttk.Style()
        style.configure("Storno.TButton", foreground="red")


        filter_frame = ttk.Frame(action_frame)
        filter_frame.pack(side='right')
        ttk.Label(filter_frame, text="Filter:").pack(side='left', padx=(0, 5))
        ttk.Radiobutton(filter_frame, text="Offen", variable=self.current_filter, value="Offen", command=self.load_requests).pack(side='left')
        ttk.Radiobutton(filter_frame, text="Alle", variable=self.current_filter, value="Alle", command=self.load_requests).pack(side='left', padx=5)
        ttk.Radiobutton(filter_frame, text="Archiv", variable=self.current_filter, value="Archiv", command=self.load_requests).pack(side='left', padx=5)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(expand=True, fill='both', pady=(10, 0))

        self.tree = ttk.Treeview(tree_frame, columns=('id', 'name', 'start_date', 'end_date', 'status'), show='headings')
        self.tree.heading('id', text='ID')
        self.tree.heading('name', text='Mitarbeiter')
        self.tree.heading('start_date', text='Von')
        self.tree.heading('end_date', text='Bis')
        self.tree.heading('status', text='Status')

        self.tree.column('id', width=40, anchor='center')
        self.tree.column('name', width=200)
        self.tree.column('start_date', width=120, anchor='center')
        self.tree.column('end_date', width=120, anchor='center')
        self.tree.column('status', width=120, anchor='center')

        # Farben definieren
        self.tree.tag_configure('Ausstehend', background='#FFF3CD')
        self.tree.tag_configure('Genehmigt', background='#D4EDDA')
        self.tree.tag_configure('Abgelehnt', background='#F8D7DA')
        self.tree.tag_configure('Storniert', background='#E0B0FF') # Lila
        self.tree.tag_configure('Archiviert', background='#E9ECEF', foreground='gray')

        self.tree.pack(side='left', expand=True, fill='both')
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

    def load_requests(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        all_requests = get_all_vacation_requests_for_admin()
        filter_val = self.current_filter.get()

        for req in all_requests:
            status = req['status']
            archived = req['archived']
            if (filter_val == "Offen" and (status != 'Ausstehend' or archived)) or \
               (filter_val == "Alle" and archived) or \
               (filter_val == "Archiv" and not archived):
                continue

            tag = "Archiviert" if archived else status
            display_status = f"Archiviert ({status})" if archived else status
            start_date = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            end_date = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            self.tree.insert('', 'end', values=(req['id'], f"{req['vorname']} {req['name']}", start_date, end_date, display_status), tags=(tag,))

    def get_selected_request_details(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie zuerst einen Antrag aus.", parent=self)
            return None, None
        item = self.tree.item(selected_items[0])
        request_id = item['values'][0]
        # Der Status ist der Text im Treeview, der auch "Archiviert (...)" enthalten kann
        # Wir nehmen daher das Tag als echten Status
        status = item['tags'][0] if item['tags'] else None
        return request_id, status

    def approve_selected_request(self):
        request_id, status = self.get_selected_request_details()
        if not request_id: return
        if status != 'Ausstehend':
            messagebox.showwarning("Aktion nicht möglich", "Nur ausstehende Anträge können genehmigt werden.", parent=self)
            return
        success, msg = approve_vacation_request(request_id, self.app.user_data['id'])
        if success:
            messagebox.showinfo("Erfolg", msg, parent=self)
            self.refresh_ui_after_action()
        else:
            messagebox.showerror("Fehler", msg, parent=self)

    def reject_selected_request(self):
        request_id, status = self.get_selected_request_details()
        if not request_id: return
        if status != 'Ausstehend':
            messagebox.showwarning("Aktion nicht möglich", "Nur ausstehende Anträge können abgelehnt werden.", parent=self)
            return
        success, msg = update_vacation_request_status(request_id, "Abgelehnt")
        if success:
            messagebox.showinfo("Erfolg", "Antrag wurde abgelehnt.", parent=self)
            self.refresh_ui_after_action()
        else:
            messagebox.showerror("Fehler", msg, parent=self)

    def cancel_selected_request(self):
        request_id, status = self.get_selected_request_details()
        if not request_id: return
        if status != 'Genehmigt':
            messagebox.showwarning("Aktion nicht möglich", "Nur genehmigte Urlaube können storniert werden.", parent=self)
            return
        if messagebox.askyesno("Bestätigen", "Möchten Sie diesen genehmigten Urlaub wirklich stornieren?\nDer Mitarbeiter wird benachrichtigt und die 'U'-Tage werden aus dem Plan entfernt.", parent=self):
            success, msg = cancel_vacation_request(request_id, self.app.user_data['id'])
            if success:
                messagebox.showinfo("Erfolg", msg, parent=self)
                self.refresh_ui_after_action()
            else:
                messagebox.showerror("Fehler", msg, parent=self)

    def archive_selected_request(self):
        request_id, _ = self.get_selected_request_details()
        if not request_id: return
        if messagebox.askyesno("Bestätigen", "Möchten Sie diesen Antrag wirklich archivieren?\nEr wird aus der Hauptansicht ausgeblendet, aber der Status und der Schichtplan bleiben unverändert.", parent=self):
            success, msg = archive_vacation_request(request_id, self.app.user_data['id'])
            if success:
                messagebox.showinfo("Erfolg", msg, parent=self)
                self.refresh_ui_after_action()
            else:
                messagebox.showerror("Fehler", msg, parent=self)

    def refresh_ui_after_action(self):
        self.load_requests()
        self.app.check_for_updates()
        if "Schichtplan" in self.app.tab_frames:
            self.app.tab_frames["Schichtplan"].refresh_plan()

    def refresh_data(self):
        self.load_requests()