# gui/tabs/user_bug_report_tab.py
import tkinter as tk
from tkinter import ttk
from datetime import datetime

# --- Hier ist die Korrektur ---
from database.db_reports import get_visible_bug_reports


# --- Ende der Korrektur ---


class UserBugReportTab(ttk.Frame):
    def __init__(self, master, app_logic):
        super().__init__(master)
        self.app = app_logic
        self.all_reports_data = {}
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
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(top_frame, text="Aktuelle Bug-Meldungen", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT,
                                                                                                anchor="w")
        ttk.Button(top_frame, text="Aktualisieren", command=self.load_bug_reports).pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("gemeldet_am", "titel", "status")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")

        self.tree.heading("gemeldet_am", text="Gemeldet am")
        self.tree.column("gemeldet_am", width=120, anchor=tk.W)
        self.tree.heading("titel", text="Titel")
        self.tree.column("titel", width=200, anchor=tk.W)
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=100, anchor=tk.CENTER)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.bind("<<TreeviewSelect>>", self.on_bug_select)

    def setup_ui_details(self, parent):
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Details zur Meldung", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2,
                                                                                          sticky="w", pady=(0, 10))

        self.detail_title_var = tk.StringVar(value="Bitte eine Meldung auswählen")
        self.detail_status_var = tk.StringVar()
        self.detail_timestamp_var = tk.StringVar()

        ttk.Label(parent, text="Titel:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="nw")
        ttk.Label(parent, textvariable=self.detail_title_var, wraplength=500).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(parent, text="Status:", font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="nw")
        ttk.Label(parent, textvariable=self.detail_status_var).grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(parent, text="Gemeldet am:", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="nw")
        ttk.Label(parent, textvariable=self.detail_timestamp_var).grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(parent, text="Beschreibung:", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="nw",
                                                                                    pady=(10, 0))
        self.description_text = tk.Text(parent, height=8, width=60, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1,
                                        state=tk.DISABLED, bg="#f0f0f0")
        self.description_text.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=2)

        ttk.Label(parent, text="Notizen vom Admin:", font=("Segoe UI", 10, "bold")).grid(row=6, column=0, sticky="nw",
                                                                                         pady=(10, 0))
        self.admin_notes_text = tk.Text(parent, height=8, width=60, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1,
                                        state=tk.DISABLED, bg="#f0f0f0")
        self.admin_notes_text.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=2)

        parent.rowconfigure(5, weight=1)
        parent.rowconfigure(7, weight=1)

    def load_bug_reports(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        # --- Hier ist die zweite Korrektur ---
        self.all_reports_data = {str(report['id']): report for report in get_visible_bug_reports()}
        # --- Ende der Korrektur ---

        for report_id, report in self.all_reports_data.items():
            ts = datetime.strptime(report['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            self.tree.insert("", "end", iid=report_id, values=(ts, report['title'], report['status']))

        self.clear_details()

    def on_bug_select(self, event):
        selection = self.tree.selection()
        if selection:
            self.display_bug_details(selection[0])

    def display_bug_details(self, bug_id):
        bug = self.all_reports_data.get(bug_id)
        if not bug:
            self.clear_details()
            return

        self.detail_title_var.set(bug.get('title', 'N/A'))
        self.detail_status_var.set(bug.get('status', 'N/A'))
        ts = datetime.strptime(bug['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y um %H:%M Uhr')
        self.detail_timestamp_var.set(ts)

        for text_widget, content in [
            (self.description_text, bug.get('description', '')),
            (self.admin_notes_text, bug.get('admin_notes') or 'Keine Notizen vorhanden.')
        ]:
            text_widget.config(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.insert(tk.END, content)
            text_widget.config(state=tk.DISABLED)

    def clear_details(self):
        self.detail_title_var.set("Bitte eine Meldung aus der Liste links auswählen.")
        self.detail_status_var.set("")
        self.detail_timestamp_var.set("")
        for text_widget in [self.description_text, self.admin_notes_text]:
            text_widget.config(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.config(state=tk.DISABLED)