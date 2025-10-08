# gui/tabs/bug_reports_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_manager import get_all_bug_reports, update_bug_report_status, archive_bug_report, unarchive_bug_report


class BugReportsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # === Aktive Reports ===
        active_frame = ttk.LabelFrame(self, text="Aktive Reports", padding=10)
        active_frame.grid(row=0, column=0, sticky="nsew", columnspan=2, pady=(0, 10))
        active_frame.columnconfigure(0, weight=1)
        active_frame.rowconfigure(0, weight=1)

        columns = ("user", "timestamp", "title", "status")
        self.bug_tree = ttk.Treeview(active_frame, columns=columns, show="headings")
        self.bug_tree.heading("user", text="Benutzer")
        self.bug_tree.heading("timestamp", text="Zeitpunkt")
        self.bug_tree.heading("title", text="Titel")
        self.bug_tree.heading("status", text="Status")
        self.bug_tree.grid(row=0, column=0, sticky="nsew")

        self.bug_tree.tag_configure("Neu", background="#FFCDD2")
        self.bug_tree.tag_configure("In Bearbeitung", background="#FFF9C4")
        self.bug_tree.tag_configure("Erledigt", background="#C8E6C9")

        # === Archivierte Reports ===
        archive_frame = ttk.LabelFrame(self, text="Archiv", padding=10)
        archive_frame.grid(row=2, column=0, sticky="nsew", columnspan=2, pady=(10, 0))
        archive_frame.columnconfigure(0, weight=1)
        archive_frame.rowconfigure(0, weight=1)

        self.archive_tree = ttk.Treeview(archive_frame, columns=columns, show="headings")
        self.archive_tree.heading("user", text="Benutzer")
        self.archive_tree.heading("timestamp", text="Zeitpunkt")
        self.archive_tree.heading("title", text="Titel")
        self.archive_tree.heading("status", text="Status")
        self.archive_tree.grid(row=0, column=0, sticky="nsew")
        self.archive_tree.tag_configure("Archived", foreground="grey", background="#E0E0E0")

        # === Details und Aktionen ===
        details_frame = ttk.Frame(self, padding="10")
        details_frame.grid(row=0, column=2, rowspan=3, sticky="ns", padx=10)

        ttk.Label(details_frame, text="Beschreibung:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.description_text = tk.Text(details_frame, height=15, width=40, wrap="word", state="disabled")
        self.description_text.pack(fill="both", expand=True, pady=(5, 10))

        self.status_frame = ttk.Frame(details_frame)
        self.status_frame.pack(fill="x", pady=5)
        ttk.Label(self.status_frame, text="Status ändern:").pack(side="left")
        self.status_combobox = ttk.Combobox(self.status_frame, values=["Neu", "In Bearbeitung", "Erledigt"],
                                            state="readonly")
        self.status_combobox.pack(side="left", padx=5)
        ttk.Button(self.status_frame, text="Ändern", command=self.change_status).pack(side="left")

        self.archive_button = ttk.Button(details_frame, text="Archivieren", command=self.archive_selected_report)
        self.archive_button.pack(fill="x", pady=5)

        self.unarchive_button = ttk.Button(details_frame, text="Wiederherstellen",
                                           command=self.unarchive_selected_report)
        # unarchive_button wird initial versteckt

        self.bug_tree.bind("<<TreeviewSelect>>", lambda e: self.on_bug_selected(e, self.bug_tree))
        self.archive_tree.bind("<<TreeviewSelect>>", lambda e: self.on_bug_selected(e, self.archive_tree))

        self.refresh_bug_trees()

    def refresh_bug_trees(self):
        for item in self.bug_tree.get_children():
            self.bug_tree.delete(item)
        for item in self.archive_tree.get_children():
            self.archive_tree.delete(item)

        bug_reports = get_all_bug_reports()
        for report in bug_reports:
            values = (
                f"{report['vorname']} {report['name']}",
                report['timestamp'],
                report['title'],
                report['status']
            )
            if report['archived']:
                self.archive_tree.insert("", tk.END, iid=report['id'], values=values, tags=("Archived",))
            else:
                self.bug_tree.insert("", tk.END, iid=report['id'], values=values, tags=(report['status'],))

    def on_bug_selected(self, event, tree_widget):
        other_tree = self.archive_tree if tree_widget is self.bug_tree else self.bug_tree
        if other_tree.selection():
            other_tree.selection_remove(other_tree.selection())

        selection = tree_widget.selection()

        # UI-Elemente basierend auf Auswahl anpassen
        if not selection:
            self.status_frame.pack_forget()
            self.archive_button.pack_forget()
            self.unarchive_button.pack_forget()
            return

        if tree_widget is self.bug_tree:
            self.status_frame.pack(fill="x", pady=5)
            self.archive_button.pack(fill="x", pady=5)
            self.unarchive_button.pack_forget()
        else:  # archive_tree
            self.status_frame.pack_forget()
            self.archive_button.pack_forget()
            self.unarchive_button.pack(fill="x", pady=5)

        bug_id = int(selection[0])
        bug_reports = get_all_bug_reports()
        report = next((r for r in bug_reports if r['id'] == bug_id), None)

        if report:
            self.description_text.config(state="normal")
            self.description_text.delete("1.0", tk.END)
            self.description_text.insert(tk.END, report['description'])
            self.description_text.config(state="disabled")
            self.status_combobox.set(report['status'])

    def change_status(self):
        selection = self.bug_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen aktiven Fehlerbericht aus.",
                                   parent=self.app)
            return

        bug_id = int(selection[0])
        new_status = self.status_combobox.get()
        if not new_status:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Status aus.", parent=self.app)
            return

        success, message = update_bug_report_status(bug_id, new_status)
        if success:
            messagebox.showinfo("Erfolg", "Status wurde aktualisiert.", parent=self.app)
            self.refresh_bug_trees()
            self.app.update_notification_indicators()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Aktualisieren des Status: {message}", parent=self.app)

    def archive_selected_report(self):
        selection = self.bug_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen aktiven Report zum Archivieren aus.",
                                   parent=self.app)
            return

        bug_id = int(selection[0])
        if not messagebox.askyesno("Bestätigen", "Möchten Sie diesen Report wirklich archivieren?", parent=self.app):
            return

        success, message = archive_bug_report(bug_id)
        if success:
            messagebox.showinfo("Erfolg", message, parent=self.app)
            self.refresh_bug_trees()
            self.app.update_notification_indicators()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Archivieren: {message}", parent=self.app)

    def unarchive_selected_report(self):
        selection = self.archive_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl",
                                   "Bitte wählen Sie einen archivierten Report zum Wiederherstellen aus.",
                                   parent=self.app)
            return

        bug_id = int(selection[0])
        success, message = unarchive_bug_report(bug_id)
        if success:
            messagebox.showinfo("Erfolg", message, parent=self.app)
            self.refresh_bug_trees()
            self.app.update_notification_indicators()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Wiederherstellen: {message}", parent=self.app)