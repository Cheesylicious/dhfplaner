# gui/tabs/bug_reports_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.simpledialog import askstring
from datetime import datetime
from database.db_reports import (
    get_all_bug_reports, update_bug_report_status, archive_bug_report,
    unarchive_bug_report, append_admin_note, delete_bug_reports,
    update_bug_report_category, SEVERITY_ORDER
)


class BugReportsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.reports_data = {}
        self.selected_report_id = None
        self.auto_refresh_id = None
        self.refresh_interval_ms = 30000

        self.categories = list(SEVERITY_ORDER.keys())

        self.category_colors = {
            "Unwichtiger Fehler": "#FFFFE0",
            "Schönheitsfehler": "#FFD700",
            "Kleiner Fehler": "#FFA500",
            "Mittlerer Fehler": "#FF4500",
            "Kritischer Fehler": "#B22222",
            "Erledigt": "#90EE90",
            "Rückmeldung (Offen)": "#FF6347",
            "Rückmeldung (Behoben)": "#32CD32",
            "Warte auf Rückmeldung": "#87CEFA"
        }

        self.status_values = ["Neu", "In Bearbeitung", "Warte auf Rückmeldung", "Erledigt", "Rückmeldung (Offen)",
                              "Rückmeldung (Behoben)"]

        self.setup_ui()
        self.refresh_data(initial_load=True)

        if self.app and self.app.notebook:
            self.app.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
            self.after(100, self.start_stop_refresh_check)

    def on_close(self):
        self.stop_auto_refresh()

    def start_stop_refresh_check(self):
        try:
            if self.winfo_exists() and self.app.notebook.winfo_exists() and self.app.notebook.winfo_children():
                current_tab_widget = self.app.notebook.nametowidget(self.app.notebook.select())
                if current_tab_widget is self:
                    self.start_auto_refresh()
                else:
                    self.stop_auto_refresh()
        except tk.TclError:
            self.stop_auto_refresh()

    def on_tab_changed(self, event):
        self.start_stop_refresh_check()

    def start_auto_refresh(self):
        if self.auto_refresh_id is None:
            self.auto_refresh_loop()

    def stop_auto_refresh(self):
        if self.auto_refresh_id is not None:
            self.after_cancel(self.auto_refresh_id)
            self.auto_refresh_id = None

    def auto_refresh_loop(self):
        self.refresh_data()
        self.auto_refresh_id = self.after(self.refresh_interval_ms, self.auto_refresh_loop)

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
        ttk.Label(filter_frame, text=f"(Auto-Aktualisierung: {self.refresh_interval_ms / 1000:.0f}s)").pack(
            side="right", padx=10)

        self.tree = ttk.Treeview(tree_frame, columns=("category", "user", "timestamp", "title", "status"),
                                 show="headings", selectmode="extended")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.heading("category", text="Kategorie", command=lambda: self.sort_by_column("category", False))
        self.tree.heading("user", text="Benutzer", command=lambda: self.sort_by_column("user", False))
        self.tree.heading("timestamp", text="Zeitpunkt", command=lambda: self.sort_by_column("timestamp", True))
        self.tree.heading("title", text="Titel", command=lambda: self.sort_by_column("title", False))
        self.tree.heading("status", text="Status", command=lambda: self.sort_by_column("status", False))
        self.tree.column("category", width=120)
        self.tree.column("user", width=150)
        self.tree.column("timestamp", width=140)
        self.tree.column("status", width=100)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_report_selected)

        for name, color in self.category_colors.items():
            tag_name = name.replace(" ", "_").replace("(", "").replace(")", "").lower()
            self.tree.tag_configure(tag_name, background=color)
        self.tree.tag_configure("archived", foreground="grey", font=("Segoe UI", 9, "italic"))

        details_frame = ttk.LabelFrame(main_frame, text="Details und Bearbeitung", padding="10")
        details_frame.grid(row=0, column=1, sticky="nsew")
        details_frame.grid_rowconfigure(5, weight=1)
        details_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(details_frame, text="Titel:").grid(row=0, column=0, sticky="w", pady=2)
        self.title_var = tk.StringVar()
        ttk.Label(details_frame, textvariable=self.title_var, wraplength=400, font=("Segoe UI", 9, "bold")).grid(row=0,
                                                                                                                 column=1,
                                                                                                                 sticky="w",
                                                                                                                 pady=2)
        ttk.Label(details_frame, text="Beschreibung:").grid(row=1, column=0, sticky="nw", pady=2)
        self.description_text = tk.Text(details_frame, height=8, wrap="word", state="disabled", relief="solid",
                                        borderwidth=1, font=("Segoe UI", 9))
        self.description_text.grid(row=1, column=1, sticky="nsew", pady=2)
        ttk.Label(details_frame, text="Kategorie:").grid(row=2, column=0, sticky="w", pady=5)
        self.category_combobox_admin = ttk.Combobox(details_frame, values=self.categories, state="disabled")
        self.category_combobox_admin.grid(row=2, column=1, sticky="ew", pady=5)
        self.category_combobox_admin.bind("<<ComboboxSelected>>", self.on_category_changed)
        ttk.Label(details_frame, text="Status:").grid(row=3, column=0, sticky="w", pady=5)
        self.status_combobox = ttk.Combobox(details_frame, values=self.status_values, state="disabled")
        self.status_combobox.grid(row=3, column=1, sticky="ew", pady=5)
        self.status_combobox.bind("<<ComboboxSelected>>", self.on_status_changed)
        ttk.Label(details_frame, text="Notizen (Admin & User):").grid(row=4, column=0, sticky="nw", pady=2)
        self.notes_text = tk.Text(details_frame, height=10, wrap="word", relief="solid", borderwidth=1,
                                  font=("Segoe UI", 9), state="disabled")
        self.notes_text.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(2, 5))

        button_bar = ttk.Frame(details_frame)
        button_bar.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.add_note_button = ttk.Button(button_bar, text="Notiz hinzufügen", command=self.add_admin_note,
                                          state="disabled")
        self.add_note_button.pack(side="left")
        self.archive_button = ttk.Button(button_bar, text="Archivieren", command=self.toggle_archive_status,
                                         state="disabled")
        self.archive_button.pack(side="right")

        self.feedback_response_bar = ttk.Frame(details_frame)
        self.feedback_response_bar.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.re_request_feedback_button = ttk.Button(self.feedback_response_bar, text="Feedback erneut anfordern",
                                                     command=self.re_request_feedback)
        self.close_bug_button = ttk.Button(self.feedback_response_bar, text="Bug als 'Erledigt' schließen",
                                           command=self.close_bug)

    def sort_by_column(self, col, reverse):
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]

        if col == "category":
            data.sort(key=lambda item: SEVERITY_ORDER.get(item[0], 0), reverse=reverse)
        else:
            data.sort(reverse=reverse)

        for index, (val, child) in enumerate(data):
            self.tree.move(child, '', index)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    def refresh_data(self, initial_load=False):
        selected_ids = self.tree.selection()
        scroll_pos = self.tree.yview()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.reports_data.clear()

        reports = get_all_bug_reports()
        show_archived = self.show_archived_var.get()

        for report in reports:
            report_id = report['id']
            self.reports_data[report_id] = report
            if not show_archived and report.get('archived'):
                continue

            user = f"{report.get('vorname', '')} {report.get('name', '')}".strip() or "Unbekannt"
            try:
                ts = datetime.strptime(report['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            except (ValueError, TypeError):
                ts = report['timestamp']

            tags = []
            status = report.get('status')
            category = report.get('category')

            if report.get('archived'):
                tags.append('archived')
            else:
                status_tag = status.replace(" ", "_").replace("(", "").replace(")", "").lower() if status else ""
                if status and status in self.category_colors:
                    tags.append(status_tag)
                elif category and category in self.category_colors:
                    tags.append(category.replace(" ", "_").lower())

            values = (report.get('category', 'N/A'), user, ts, report['title'], status)
            self.tree.insert("", tk.END, iid=report_id, values=values, tags=tags)

        if selected_ids:
            valid_ids = [sid for sid in selected_ids if self.tree.exists(sid)]
            if valid_ids:
                self.tree.selection_set(valid_ids)
                if len(valid_ids) == 1: self.on_report_selected(None)
            else:
                self.clear_details()
        else:
            self.clear_details()

        self.tree.yview_moveto(scroll_pos[0])
        if not initial_load and self.app: self.app.check_for_updates()

    def on_report_selected(self, event):
        selection = self.tree.selection()
        self.feedback_response_bar.grid_remove()
        self.re_request_feedback_button.pack_forget()
        self.close_bug_button.pack_forget()

        if len(selection) != 1:
            self.clear_details()
            return

        self.selected_report_id = int(selection[0])
        report = self.reports_data.get(self.selected_report_id)
        if not report:
            self.clear_details()
            return

        self.title_var.set(report.get('title', 'Kein Titel'))
        description = report.get('description') or ''
        self.description_text.config(state="normal")
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", description)
        self.description_text.config(state="disabled")
        self.category_combobox_admin.config(state="readonly")
        self.category_combobox_admin.set(report.get('category', ''))
        self.status_combobox.config(state="readonly")
        self.status_combobox.set(report.get('status', ''))

        admin_notes = report.get('admin_notes') or ''
        user_notes = report.get('user_notes') or ''
        full_notes = ""
        if admin_notes: full_notes += f"--- ADMIN NOTIZEN ---\n{admin_notes}\n\n"
        if user_notes: full_notes += f"--- USER FEEDBACK ---\n{user_notes}"
        self.notes_text.config(state="normal")
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", full_notes.strip())
        self.notes_text.config(state="disabled")

        self.add_note_button.config(state="normal")
        self.archive_button.config(state="normal")
        self.archive_button.config(text="Dearchivieren" if report.get('archived') else "Archivieren")

        status = report.get('status')
        if status in ['Rückmeldung (Offen)', 'Rückmeldung (Behoben)']:
            self.feedback_response_bar.grid()
            self.re_request_feedback_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
            self.close_bug_button.pack(side="left", expand=True, fill="x", padx=(5, 0))

    def clear_details(self):
        self.selected_report_id = None
        self.title_var.set("")
        self.description_text.config(state="normal");
        self.description_text.delete("1.0", tk.END);
        self.description_text.config(state="disabled")
        self.category_combobox_admin.set("");
        self.category_combobox_admin.config(state="disabled")
        self.status_combobox.set("");
        self.status_combobox.config(state="disabled")
        self.notes_text.config(state="normal");
        self.notes_text.delete("1.0", tk.END);
        self.notes_text.config(state="disabled")
        self.add_note_button.config(state="disabled")
        self.archive_button.config(state="disabled")
        self.archive_button.config(text="Archivieren")
        self.feedback_response_bar.grid_remove()

    def add_admin_note(self):
        if not self.selected_report_id: return
        note = askstring("Neue Notiz", "Bitte gib deine Notiz ein:", parent=self)
        if note:
            success, message = append_admin_note(self.selected_report_id, note)
            if success:
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def re_request_feedback(self):
        if not self.selected_report_id: return
        note = askstring("Erneut anfordern", "Optionale Notiz an den User (z.B. 'Bitte prüfe X nochmal'):", parent=self)
        if note is not None:
            if note:
                append_admin_note(self.selected_report_id, note)
            update_bug_report_status(self.selected_report_id, "Warte auf Rückmeldung")
            messagebox.showinfo("Erfolg", "Feedback wurde erneut beim Benutzer angefordert.", parent=self)
            self.refresh_data()

    def close_bug(self):
        if not self.selected_report_id: return
        if messagebox.askyesno("Bestätigen", "Möchtest du diesen Bug-Report wirklich als 'Erledigt' schließen?",
                               parent=self):
            success, message = update_bug_report_status(self.selected_report_id, "Erledigt")
            if success:
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def on_category_changed(self, event):
        if not self.selected_report_id: return
        new_category = self.category_combobox_admin.get()
        success, message = update_bug_report_category(self.selected_report_id, new_category)
        if success:
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def on_status_changed(self, event):
        if not self.selected_report_id: return
        new_status = self.status_combobox.get()
        if new_status in ["Rückmeldung (Offen)", "Rückmeldung (Behoben)"]:
            messagebox.showwarning("Aktion erforderlich",
                                   "Bitte benutze die Buttons 'Feedback erneut anfordern' oder 'Bug schließen', um auf das User-Feedback zu reagieren.",
                                   parent=self)
            self.status_combobox.set(self.reports_data[self.selected_report_id]['status'])  # Status zurücksetzen
            return
        success, message = update_bug_report_status(self.selected_report_id, new_status)
        if success:
            self.refresh_data()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def toggle_archive_status(self):
        if not self.selected_report_id: return
        report = self.reports_data.get(self.selected_report_id)
        if not report: return
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
        msg = f"Möchten Sie die {len(ids_to_delete)} ausgewählten Bug-Report(s) wirklich endgültig löschen?"
        if messagebox.askyesno("Löschen bestätigen", msg, icon='warning', parent=self):
            success, message = delete_bug_reports(ids_to_delete)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.refresh_data()
            else:
                messagebox.showerror("Fehler", message, parent=self)