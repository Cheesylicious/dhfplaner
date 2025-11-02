# gui/tabs/request_lock_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from ..request_lock_manager import RequestLockManager


class RequestLockTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.year_var = tk.StringVar(value=str(datetime.now().year))

        self.setup_ui()
        self.load_locks_for_year()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        year_frame = ttk.Frame(main_frame)
        year_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(year_frame, text="Jahr auswählen:", font=('Segoe UI', 10, 'bold')).pack(side="left", padx=(0, 10))

        self.year_spinbox = ttk.Spinbox(year_frame, from_=2020, to=2050, textvariable=self.year_var, width=8,
                                        command=self.load_locks_for_year)
        self.year_spinbox.pack(side="left")

        list_frame = ttk.LabelFrame(main_frame, text="Monate sperren/entsperren", padding="10")
        list_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(list_frame, columns=('Month', 'Status'), show='headings')
        self.tree.heading('Month', text='Monat')
        self.tree.heading('Status', text='Status')
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.tag_configure('Gesperrt', background='#F8D7DA')
        self.tree.tag_configure('Offen', background='#D4EDDA')

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)

        ttk.Button(button_frame, text="Ausgewählten Monat sperren", command=self.lock_month).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Ausgewählten Monat entsperren", command=self.unlock_month).pack(side="left",
                                                                                                       padx=5)

    def load_locks_for_year(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        year = int(self.year_var.get())
        locks = RequestLockManager.load_locks()

        for month in range(1, 13):
            month_name = datetime(year, month, 1).strftime("%B")
            lock_key = f"{year}-{month:02d}"

            is_locked = locks.get(lock_key, False)
            status = "Gesperrt" if is_locked else "Offen"
            tag = status

            self.tree.insert('', 'end', values=(f"{month_name} {year}", status), tags=(tag,), iid=lock_key)

    def lock_month(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Monat zum Sperren aus.", parent=self)
            return

        lock_key = selected[0]
        year, month = map(int, lock_key.split('-'))

        if messagebox.askyesno("Bestätigen",
                               f"Möchten Sie den {datetime(year, month, 1).strftime('%B %Y')} wirklich für neue Anträge sperren?",
                               parent=self):
            locks = RequestLockManager.load_locks()
            locks[lock_key] = True
            if RequestLockManager.save_locks(locks):
                messagebox.showinfo("Erfolg", "Der Monat wurde gesperrt.", parent=self)
                self.app.refresh_antragssperre_views()
            else:
                messagebox.showerror("Fehler", "Die Sperre konnte nicht gespeichert werden.", parent=self)

    def unlock_month(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Monat zum Entsperren aus.", parent=self)
            return

        lock_key = selected[0]
        year, month = map(int, lock_key.split('-'))

        if messagebox.askyesno("Bestätigen",
                               f"Möchten Sie den {datetime(year, month, 1).strftime('%B %Y')} wirklich für neue Anträge freigeben?",
                               parent=self):
            locks = RequestLockManager.load_locks()
            if lock_key in locks:
                del locks[lock_key]

            if RequestLockManager.save_locks(locks):
                messagebox.showinfo("Erfolg", "Der Monat wurde entsperrt.", parent=self)
                self.app.refresh_antragssperre_views()
            else:
                messagebox.showerror("Fehler", "Die Sperre konnte nicht aufgehoben werden.", parent=self)