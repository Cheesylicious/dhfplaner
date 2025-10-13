# gui/tabs/bug_reports_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_reports import (
    get_all_bug_reports, update_bug_report_status, archive_bug_report,
    unarchive_bug_report, update_bug_report_notes, delete_bug_reports
)


class BugReportsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.reports_data = {}
        self.selected_report_id = None

        # NEU: Automatischer Refresh (30 Sekunden)
        self.refresh_interval_ms = 30000
        self.auto_refresh_id = None

        self.setup_ui()
        self.refresh_data(initial_load=True)  # Ruft refresh_data mit Flag auf

        # Binde an das Notebook, um zu starten/stoppen, und starte den initialen Check
        if self.app and self.app.notebook:
            self.app.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
            # Prüft nach kurzer Verzögerung, ob dieser Tab der initial aktive ist
            self.after(100, self.start_stop_refresh_check)

    def start_stop_refresh_check(self):
        """Prüft, ob dieser Tab aktiv ist, um den Refresh-Loop zu steuern."""
        if self.app.notebook.winfo_children():
            current_tab_widget = self.app.notebook.nametowidget(self.app.notebook.select())
            if current_tab_widget is self:
                self.start_auto_refresh()
            else:
                self.stop_auto_refresh()

    def on_tab_changed(self, event):
        """Wird ausgelöst, wenn der Tab gewechselt wird."""
        self.start_stop_refresh_check()

    def start_auto_refresh(self):
        """Startet den automatischen Refresh-Timer."""
        if self.auto_refresh_id is None:
            self.auto_refresh_loop()

    def stop_auto_refresh(self):
        """Stoppt den automatischen Refresh-Timer."""
        if self.auto_refresh_id is not None:
            self.after_cancel(self.auto_refresh_id)
            self.auto_refresh_id = None

    def auto_refresh_loop(self):
        """Führt den Refresh durch und plant den nächsten Durchlauf."""
        self.refresh_data()
        # Setze den Timer neu
        self.auto_refresh_id = self.after(self.refresh_interval_ms, self.auto_refresh_loop)

    def __del__(self):
        """Stellt sicher, dass der Timer beim Zerstören des Objekts gestoppt wird."""
        self.stop_auto_refresh()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=2)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tree_frame.grid_rowconfigure(1, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        filter_frame = ttk.Frame(tree_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.show_archived_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="Archivierte anzeigen", variable=self.show_archived_var,
                        command=self.refresh_data).pack(side="left")

        self.delete_button = ttk.Button(filter_frame, text="Markierte löschen", command=self.delete_selected_reports)
        self.delete_button.pack(side="left", padx=20)

        # NEU: Label für Auto-Update-Status
        ttk.Label(filter_frame, text=f"(Auto-Aktualisierung: {self.refresh_interval_ms / 1000:.0f}s)").pack(
            side="right", padx=10)

        self.tree = ttk.Treeview(tree_frame, columns=("user", "timestamp", "title", "status"), show="headings",
                                 selectmode="extended")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.heading("user", text="Benutzer")
        self.tree.heading("timestamp", text="Zeitpunkt")
        self.tree.heading("title", text="Titel")
        self.tree.heading("status", text="Status")
        self.tree.column("user", width=150)
        self.tree.column("timestamp", width=140)
        self.tree.column("status", width=100)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.bind("<<TreeviewSelect>>", self.on_report_selected)

        details_frame = ttk.LabelFrame(main_frame, text="Details und Bearbeitung", padding="10")
        details_frame.grid(row=0, column=1, sticky="nsew")
        details_frame.grid_rowconfigure(4, weight=1)
        details_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(details_frame, text="Titel:").grid(row=0, column=0, sticky="w", pady=2)
        self.title_var = tk.StringVar()
        ttk.Label(details_frame, textvariable=self.title_var, wraplength=400).grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(details_frame, text="Beschreibung:").grid(row=1, column=0, sticky="nw", pady=2)
        self.description_text = tk.Text(details_frame, height=8, wrap="word", state="disabled", relief="solid",
                                        borderwidth=1, font=("Segoe UI", 9))
        self.description_text.grid(row=1, column=1, sticky="nsew", pady=2)

        ttk.Label(details_frame, text="Status:").grid(row=2, column=0, sticky="w", pady=5)
        self.status_combobox = ttk.Combobox(details_frame,
                                            values=["Neu", "In Bearbeitung", "Warte auf Rückmeldung", "Erledigt"],
                                            state="readonly")
        self.status_combobox.grid(row=2, column=1, sticky="ew", pady=5)
        self.status_combobox.bind("<<ComboboxSelected>>", self.on_status_changed)

        ttk.Label(details_frame, text="Admin-Notizen:").grid(row=3, column=0, sticky="nw", pady=2)
        self.notes_text = tk.Text(details_frame, height=10, wrap="word", relief="solid", borderwidth=1,
                                  font=("Segoe UI", 9))
        self.notes_text.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(2, 5))

        button_bar = ttk.Frame(details_frame)
        button_bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.save_notes_button = ttk.Button(button_bar, text="Notizen speichern", command=self.save_notes)
        self.save_notes_button.pack(side="left")
        self.archive_button = ttk.Button(button_bar, text="Archivieren", command=self.toggle_archive_status)
        self.archive_button.pack(side="right")

    def refresh_data(self, initial_load=False):
        """
        Lädt die Reports neu. Ruft check_for_updates nur bei aktiven Änderungen
        oder nach Abschluss der Initialisierung auf.
        """
        selected_ids = self.tree.selection()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.reports_data.clear()

        reports = get_all_bug_reports()
        show_archived = self.show_archived_var.get()

        for report in reports:
            report_id = report['id']
            self.reports_data[report_id] = report

            if not show_archived and report['archived']:
                continue

            user = f"{report['vorname']} {report['name']}"
            try:
                ts = datetime.strptime(report['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            except ValueError:
                ts = report['timestamp']

            values = (user, ts, report['title'], report['status'])
            tag = "archived" if report['archived'] else ""
            self.tree.insert("", tk.END, iid=report_id, values=values, tags=(tag,))

        self.tree.tag_configure("archived", foreground="grey")

        if selected_ids:
            try:
                self.tree.selection_set(selected_ids)
            except tk.TclError:
                self.clear_details()
        else:
            self.clear_details()

        # 💥 KORREKTUR: App-Update nur aufrufen, wenn Initialisierung abgeschlossen ist
        if not initial_load:
            self.app.check_for_updates()  # Stellt sicher, dass die Kopfzeile aktualisiert wird

    def on_report_selected(self, event):
        selection = self.tree.selection()
        if len(selection) != 1:
            self.selected_report_id = None
            self.clear_details()
            return

        # ... (Rest der Funktion bleibt unverändert) ...

    def clear_details(self):
        # ... (Funktion bleibt unverändert) ...
        self.archive_button.config(text="Archivieren")

    def on_status_changed(self, event):
        if not self.selected_report_id:
            return
        new_status = self.status_combobox.get()
        success, message = update_bug_report_status(self.selected_report_id, new_status)
        if success:
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def save_notes(self):
        if not self.selected_report_id:
            return
        notes = self.notes_text.get("1.0", tk.END).strip()
        success, message = update_bug_report_notes(self.selected_report_id, notes)
        if success:
            messagebox.showinfo("Gespeichert", "Die Notizen wurden erfolgreich gespeichert.", parent=self)
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def toggle_archive_status(self):
        if not self.selected_report_id:
            return
        report = self.reports_data.get(self.selected_report_id)
        if not report:
            return

        if report.get('archived'):
            success, message = unarchive_bug_report(self.selected_report_id)
        else:
            success, message = archive_bug_report(self.selected_report_id)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def delete_selected_reports(self):
        selected_ids_str = self.tree.selection()
        if not selected_ids_str:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie die zu löschenden Reports aus.", parent=self)
            return

        ids_to_delete = [int(id_str) for id_str in selected_ids_str]

        msg = f"Möchten Sie die {len(ids_to_delete)} ausgewählten Bug-Report(s) wirklich endgültig löschen? Diese Aktion kann nicht rückgängig gemacht werden."
        if messagebox.askyesno("Löschen bestätigen", msg, icon='warning', parent=self):
            success, message = delete_bug_reports(ids_to_delete)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", message, parent=self)