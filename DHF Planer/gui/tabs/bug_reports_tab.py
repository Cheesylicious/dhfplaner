# gui/tabs/bug_reports_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from database import db_manager


class BugReportsTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.bug_reports_data = {}
        self.selected_bug_id = None
        self.setup_ui()
        self.load_bug_reports()

    def setup_ui(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Linke Seite: Liste der Bug-Reports
        list_frame = ttk.Frame(main_pane, padding=5)
        self.setup_ui_list(list_frame)
        main_pane.add(list_frame, weight=1)

        # Rechte Seite: Details des ausgewählten Reports
        details_frame = ttk.Frame(main_pane, padding=10)
        self.setup_ui_details(details_frame)
        main_pane.add(details_frame, weight=2)

    def setup_ui_list(self, parent):
        ttk.Label(parent, text="Alle Bug-Meldungen", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 5))

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("gemeldet_am", "gemeldet_von", "titel", "status", "archiviert")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")

        # Spalten-Konfiguration
        self.tree.heading("gemeldet_am", text="Gemeldet am")
        self.tree.column("gemeldet_am", width=120, anchor=tk.W)
        self.tree.heading("gemeldet_von", text="Gemeldet von")
        self.tree.column("gemeldet_von", width=120, anchor=tk.W)
        self.tree.heading("titel", text="Titel")
        self.tree.column("titel", width=200, anchor=tk.W)
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=80, anchor=tk.CENTER)
        self.tree.heading("archiviert", text="Archiviert")
        self.tree.column("archiviert", width=80, anchor=tk.CENTER)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.bind("<<TreeviewSelect>>", self.on_bug_select)

        self.tree.tag_configure("archived", foreground="grey")

    def setup_ui_details(self, parent):
        parent.columnconfigure(1, weight=1)

        # Titel
        ttk.Label(parent, text="Details zur Meldung", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2,
                                                                                          sticky="w", pady=(0, 10))

        # Felder
        self.detail_title_var = tk.StringVar()
        self.detail_user_var = tk.StringVar()
        self.detail_timestamp_var = tk.StringVar()

        ttk.Label(parent, text="Titel:").grid(row=1, column=0, sticky="nw")
        ttk.Label(parent, textvariable=self.detail_title_var, wraplength=500).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(parent, text="Gemeldet von:").grid(row=2, column=0, sticky="nw")
        ttk.Label(parent, textvariable=self.detail_user_var).grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(parent, text="Zeitpunkt:").grid(row=3, column=0, sticky="nw")
        ttk.Label(parent, textvariable=self.detail_timestamp_var).grid(row=3, column=1, sticky="w", pady=2)

        # Beschreibung
        ttk.Label(parent, text="Beschreibung:").grid(row=4, column=0, sticky="nw", pady=(10, 0))
        self.description_text = tk.Text(parent, height=8, width=60, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.description_text.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=2)
        self.description_text.config(state=tk.DISABLED)

        # Admin-Notizen
        ttk.Label(parent, text="Admin-Notizen (für alle sichtbar):").grid(row=6, column=0, sticky="nw", pady=(10, 0))
        self.admin_notes_text = tk.Text(parent, height=8, width=60, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1,
                                        bg="#FFFFE0")
        self.admin_notes_text.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=2)

        parent.rowconfigure(5, weight=1)
        parent.rowconfigure(7, weight=1)

        # Aktionen
        actions_frame = ttk.Frame(parent)
        actions_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(15, 0))

        ttk.Button(actions_frame, text="Notizen speichern", command=self.save_admin_notes).pack(side=tk.LEFT,
                                                                                                padx=(0, 10))

        ttk.Label(actions_frame, text="Status ändern:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar()
        status_options = ["Neu", "In Bearbeitung", "Auf Rückmeldung warten", "Erledigt"]
        status_menu = ttk.OptionMenu(actions_frame, self.status_var, "", *status_options, command=self.update_status)
        status_menu.pack(side=tk.LEFT, padx=5)

        self.archive_button = ttk.Button(actions_frame, text="Archivieren", command=self.toggle_archive_status)
        self.archive_button.pack(side=tk.RIGHT)

    def load_bug_reports(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        reports = db_manager.get_all_bug_reports()
        self.bug_reports_data.clear()

        for report in reports:
            report_id = report['id']
            self.bug_reports_data[str(report_id)] = report

            ts = datetime.strptime(report['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            reporter = f"{report['vorname']} {report['name']}"
            is_archived = "Ja" if report['archived'] else "Nein"
            tags = ("archived",) if report['archived'] else ()

            self.tree.insert("", "end", iid=report_id,
                             values=(ts, reporter, report['title'], report['status'], is_archived), tags=tags)

        self.clear_details()

    def on_bug_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return

        self.selected_bug_id = int(selection[0])
        self.display_bug_details(self.selected_bug_id)

    def display_bug_details(self, bug_id):
        bug = self.bug_reports_data.get(str(bug_id))
        if not bug:
            self.clear_details()
            return

        self.detail_title_var.set(bug.get('title', 'N/A'))
        reporter = f"{bug.get('vorname', '')} {bug.get('name', '')}"
        self.detail_user_var.set(reporter)
        ts = datetime.strptime(bug['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y um %H:%M Uhr')
        self.detail_timestamp_var.set(ts)

        self.description_text.config(state=tk.NORMAL)
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, bug.get('description', ''))
        self.description_text.config(state=tk.DISABLED)

        self.admin_notes_text.delete("1.0", tk.END)
        self.admin_notes_text.insert(tk.END, bug.get('admin_notes') or '')

        self.status_var.set(bug.get('status', ''))

        archive_text = "Wiederherstellen" if bug.get('archived') else "Archivieren"
        self.archive_button.config(text=archive_text)

    def clear_details(self):
        self.selected_bug_id = None
        self.detail_title_var.set("")
        self.detail_user_var.set("")
        self.detail_timestamp_var.set("")
        self.description_text.config(state=tk.NORMAL)
        self.description_text.delete("1.0", tk.END)
        self.description_text.config(state=tk.DISABLED)
        self.admin_notes_text.delete("1.0", tk.END)
        self.status_var.set("")
        self.archive_button.config(text="Archivieren")

    def save_admin_notes(self):
        if self.selected_bug_id is None:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie zuerst eine Meldung aus.", parent=self)
            return

        notes = self.admin_notes_text.get("1.0", tk.END).strip()
        success, message = db_manager.update_bug_report_notes(self.selected_bug_id, notes)

        if success:
            messagebox.showinfo("Erfolg", "Notizen erfolgreich gespeichert.", parent=self)
            self.load_bug_reports()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Notizen:\n{message}", parent=self)

    def update_status(self, *args):
        if self.selected_bug_id is None:
            return  # Verhindert Ausführung, wenn keine Auswahl getroffen

        new_status = self.status_var.get()
        if new_status:
            success, message = db_manager.update_bug_report_status(self.selected_bug_id, new_status)
            if success:
                messagebox.showinfo("Status-Update", f"Status wurde auf '{new_status}' geändert.", parent=self)
                self.load_bug_reports()
            else:
                messagebox.showerror("Fehler", f"Fehler beim Ändern des Status:\n{message}", parent=self)

    def toggle_archive_status(self):
        if self.selected_bug_id is None:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie zuerst eine Meldung aus.", parent=self)
            return

        bug = self.bug_reports_data.get(str(self.selected_bug_id))
        if not bug: return

        if bug['archived']:
            success, message = db_manager.unarchive_bug_report(self.selected_bug_id)
        else:
            success, message = db_manager.archive_bug_report(self.selected_bug_id)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.load_bug_reports()
        else:
            messagebox.showerror("Fehler", f"Ein Fehler ist aufgetreten:\n{message}", parent=self)