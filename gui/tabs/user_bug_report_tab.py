# gui/tabs/user_bug_report_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_reports import get_visible_bug_reports, submit_user_feedback


class UserBugReportTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.reports = []
        self.selected_report_id = None
        self.category_colors = {
            "Unwichtiger Fehler": "#FFFFE0",
            "Schönheitsfehler": "#FFD700",
            "Kleiner Fehler": "#FFA500",
            "Mittlerer Fehler": "#FF4500",
            "Kritischer Fehler": "#B22222",
            "Erledigt": "#90EE90",
            "Warte auf Rückmeldung": "#87CEFA"
        }
        self.setup_ui()
        self.load_reports()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(main_frame, columns=("category", "timestamp", "title", "status"), show="headings",
                                 selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.heading("category", text="Kategorie")
        self.tree.heading("timestamp", text="Gemeldet am")
        self.tree.heading("title", text="Titel")
        self.tree.heading("status", text="Status")
        self.tree.column("category", width=120, anchor='w')
        self.tree.column("timestamp", width=140, anchor='w')
        self.tree.column("title", width=300, anchor='w')
        self.tree.column("status", width=100, anchor='center')

        vsb = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        for name, color in self.category_colors.items():
            tag_name = name.replace(" ", "_").lower()
            self.tree.tag_configure(tag_name, background=color)

        # Neue Tags für den Separator und erledigte Meldungen
        self.tree.tag_configure('separator', background='#E0E0E0', foreground='gray')
        self.tree.tag_configure('erledigt_style', foreground='gray')

        self.tree.bind("<<TreeviewSelect>>", self.on_report_selected)

        self.bottom_frame = ttk.Frame(main_frame)
        self.bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.details_frame = ttk.LabelFrame(self.bottom_frame, text="Details des Reports", padding="10")
        self.details_frame.grid(row=0, column=0, sticky="nsew")
        self.details_frame.grid_columnconfigure(0, weight=1)
        self.details_text = tk.Text(self.details_frame, height=10, wrap="word", state="disabled", relief="flat")
        self.details_text.grid(row=0, column=0, sticky="nsew")
        self.details_text.tag_configure("bold", font=("Segoe UI", 10, "bold"))

        self.feedback_frame = ttk.LabelFrame(self.bottom_frame, text="Deine Rückmeldung ist gefragt!", padding="10")
        self.feedback_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(self.feedback_frame, text="Notiz vom Admin:").pack(anchor="w")
        self.admin_notes_text = tk.Text(self.feedback_frame, height=4, wrap="word", relief="solid", borderwidth=1,
                                        state="disabled", font=("Segoe UI", 9, "italic"), foreground="gray")
        self.admin_notes_text.pack(fill="x", expand=True, pady=(0, 10))

        ttk.Label(self.feedback_frame, text="Deine Anmerkung (optional):").pack(anchor="w")
        self.feedback_text = tk.Text(self.feedback_frame, height=4, wrap="word", relief="solid", borderwidth=1)
        self.feedback_text.pack(fill="x", expand=True, pady=5)

        button_bar = ttk.Frame(self.feedback_frame)
        button_bar.pack(fill="x", pady=5)
        ttk.Button(button_bar, text="✅ Problem ist behoben", command=lambda: self.send_feedback(True)).pack(side="left",
                                                                                                            expand=True,
                                                                                                            fill="x",
                                                                                                            padx=2)
        ttk.Button(button_bar, text="❌ Problem besteht weiterhin", command=lambda: self.send_feedback(False)).pack(
            side="left", expand=True, fill="x", padx=2)

        self.clear_details()

    def load_reports(self):
        self.clear_details()
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.reports = get_visible_bug_reports()

        # Reports aufteilen in aktive und erledigte
        active_reports = [r for r in self.reports if r.get('status') != 'Erledigt']
        completed_reports = [r for r in self.reports if r.get('status') == 'Erledigt']

        # Aktive Reports sortieren (neueste zuerst)
        active_reports.sort(key=lambda r: r['timestamp'], reverse=True)
        # Erledigte Reports sortieren (neueste zuerst)
        completed_reports.sort(key=lambda r: r['timestamp'], reverse=True)

        # Hilfsfunktion, um einen Report in die Treeview einzufügen
        def insert_report(report, is_completed=False):
            try:
                ts = datetime.strptime(report['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            except (ValueError, TypeError):
                ts = report['timestamp']

            tags = []
            status = report.get('status')
            category = report.get('category')

            if is_completed:
                tags.append('erledigt_style')
            else:
                if status == 'Warte auf Rückmeldung':
                    tags.append('warte_auf_rückmeldung')
                elif category and category in self.category_colors:
                    tags.append(category.replace(" ", "_").lower())

            values = (category or 'N/A', ts, report['title'], status)
            self.tree.insert("", "end", iid=report['id'], values=values, tags=tags)

        # Aktive Reports einfügen
        for report in active_reports:
            insert_report(report, is_completed=False)

        # Separator einfügen, wenn beide Listen gefüllt sind
        if active_reports and completed_reports:
            self.tree.insert("", "end", iid="separator", values=("", "--- ERLEDIGTE MELDUNGEN ---", "", ""),
                             tags=('separator',))

        # Erledigte Reports einfügen
        for report in completed_reports:
            insert_report(report, is_completed=True)

    def on_report_selected(self, event):
        selection = self.tree.selection()
        if not selection or selection[0] == "separator":
            self.clear_details()
            return

        self.selected_report_id = int(selection[0])
        selected_report = next((r for r in self.reports if r['id'] == self.selected_report_id), None)

        if selected_report:
            if selected_report.get('status') == 'Warte auf Rückmeldung':
                self.details_frame.grid_remove()
                self.feedback_frame.grid(row=0, column=0, sticky="nsew")

                self.admin_notes_text.config(state="normal")
                self.admin_notes_text.delete("1.0", tk.END)
                admin_notes = selected_report.get('admin_notes')
                if admin_notes:
                    self.admin_notes_text.insert("1.0", admin_notes)
                else:
                    self.admin_notes_text.insert("1.0", "Keine Notiz vom Admin vorhanden.")
                self.admin_notes_text.config(state="disabled")

                self.feedback_text.delete("1.0", tk.END)
            else:
                self.feedback_frame.grid_remove()
                self.details_frame.grid(row=0, column=0, sticky="nsew")
                self.display_report_details(selected_report)

    def display_report_details(self, report):
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)

        title = report.get('title', 'Kein Titel')
        description = report.get('description', 'Keine Beschreibung vorhanden.')
        admin_notes = report.get('admin_notes')

        self.details_text.insert("1.0", f"Titel: {title}\n\n", "bold")
        self.details_text.insert(tk.END, f"Beschreibung:\n{description}\n\n")

        if admin_notes:
            self.details_text.insert(tk.END, "Notizen vom Admin:\n", "bold")
            self.details_text.insert(tk.END, admin_notes)

        self.details_text.config(state="disabled")

    def clear_details(self):
        self.selected_report_id = None
        self.feedback_frame.grid_remove()
        self.details_frame.grid(row=0, column=0, sticky="nsew")
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.config(state="disabled")
        # Auswahl in der Treeview aufheben
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection())

    def send_feedback(self, is_fixed):
        if not self.selected_report_id: return
        note = self.feedback_text.get("1.0", tk.END).strip()
        success, message = submit_user_feedback(self.selected_report_id, is_fixed, note)

        if success:
            messagebox.showinfo("Danke!", message, parent=self)
            self.load_reports()
            self.clear_details()
            if hasattr(self.app, 'check_for_bug_feedback_requests'):
                self.app.check_for_bug_feedback_requests()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def select_report(self, report_id):
        """Wählt einen bestimmten Report in der Liste aus."""
        if self.tree.exists(str(report_id)):
            self.tree.selection_set(str(report_id))
            self.tree.focus(str(report_id))
            self.tree.see(str(report_id))
            self.on_report_selected(None)