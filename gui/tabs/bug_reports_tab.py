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

        # --- NEU: ThreadManager und Schleifen-Steuerung ---
        self.thread_manager = self.app.thread_manager
        self.auto_refresh_active = False
        self.auto_refresh_job_id = None
        # ------------------------------------------------

        self.reports_data = {}
        self.selected_report_id = None
        # self.auto_refresh_id = None # Veraltet
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
        # --- NEU: Thread-basierten initialen Ladevorgang starten ---
        self.refresh_data_manual(initial_load=True)

        if self.app and self.app.notebook:
            self.app.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
            # Bind an Zerstörung des Tabs, um die Schleife sicher zu stoppen
            self.bind("<Destroy>", self.on_close)
            self.after(100, self.start_stop_refresh_check)

    def on_close(self, event=None):
        """Wird aufgerufen, wenn der Tab zerstört wird."""
        self.stop_auto_refresh()

    def start_stop_refresh_check(self):
        """Prüft, ob der Tab sichtbar ist und startet/stoppt die Schleife."""
        try:
            if not self.winfo_exists() or not self.app.notebook.winfo_exists():
                self.stop_auto_refresh()
                return

            current_tab_widget = self.app.notebook.nametowidget(self.app.notebook.select())
            if current_tab_widget is self:
                self.start_auto_refresh()
            else:
                self.stop_auto_refresh()
        except tk.TclError:
            self.stop_auto_refresh()

    def on_tab_changed(self, event):
        """Wird aufgerufen, wenn der Benutzer den Tab wechselt."""
        self.start_stop_refresh_check()

    def start_auto_refresh(self):
        """Startet die Auto-Refresh-Schleife, falls sie nicht schon läuft."""
        if self.auto_refresh_active:
            return
        self.auto_refresh_active = True
        print("[BugReportsTab] Starte Auto-Refresh-Schleife.")
        self.auto_refresh_loop()

    def stop_auto_refresh(self):
        """Stoppt die Auto-Refresh-Schleife."""
        if not self.auto_refresh_active:
            return
        self.auto_refresh_active = False
        if self.auto_refresh_job_id:
            self.after_cancel(self.auto_refresh_job_id)
            self.auto_refresh_job_id = None
        print("[BugReportsTab] Stoppe Auto-Refresh-Schleife.")

    def auto_refresh_loop(self):
        """
        [LÄUFT IM GUI-THREAD]
        Der "Kopf" der Schleife. Startet den Worker-Thread.
        """
        if not self.auto_refresh_active or not self.winfo_exists():
            self.auto_refresh_active = False
            return

        print("[BugReportsTab] Auto-Refresh: Starte Worker...")
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self._fetch_reports_data,
            self._on_auto_refresh_fetched
        )
        # ----------------------------------

    def _fetch_reports_data(self):
        """
        [LÄUFT IM THREAD]
        Ruft die blockierende DB-Funktion auf.
        """
        try:
            return get_all_bug_reports()
        except Exception as e:
            print(f"[FEHLER] _fetch_reports_data (Thread): {e}")
            return e

    def _on_auto_refresh_fetched(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback für die Auto-Refresh-Schleife.
        """
        if not self.auto_refresh_active or not self.winfo_exists():
            self.auto_refresh_active = False
            return

        if error:
            print(f"[BugReportsTab] Auto-Refresh Fehler: {error}")
        elif isinstance(result, Exception):
            print(f"[BugReportsTab] Auto-Refresh Thread-Fehler: {result}")
        else:
            self._update_reports_ui(result)

        self.auto_refresh_job_id = self.after(self.refresh_interval_ms, self.auto_refresh_loop)

    def setup_ui(self):
        # (UI-Code bleibt unverändert)
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
        # --- Geändert: command ruft refresh_data_manual auf ---
        ttk.Checkbutton(filter_frame, text="Archivierte anzeigen", variable=self.show_archived_var,
                        command=self.refresh_data_manual).pack(side="left")
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
        self.tree.tag_configure('separator', background='#E0E0E0', foreground='gray')
        self.tree.tag_configure('erledigt', foreground='gray')

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
        self.feedback_response_bar.grid_remove()

    def sort_by_column(self, col, reverse):
        # (Unverändert)
        children = [child for child in self.tree.get_children('') if child != 'separator']
        data = [(self.tree.set(child, col), child) for child in children]

        if col == "category":
            data.sort(key=lambda item: SEVERITY_ORDER.get(item[0], 0), reverse=reverse)
        else:
            data.sort(reverse=reverse)

        for index, (val, child) in enumerate(data):
            self.tree.move(child, '', index)

        if self.tree.exists("separator"):
            first_completed_index = -1
            for index, child_id in enumerate(self.tree.get_children('')):
                tags = self.tree.item(child_id, "tags")
                if "erledigt" in tags:
                    first_completed_index = index
                    break

            if first_completed_index != -1:
                self.tree.move("separator", "", first_completed_index)
            else:
                self.tree.move("separator", "", "end")

        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    def refresh_data(self, initial_load=False):
        """
        [VERALTET] Ruft die neue manuelle Refresh-Funktion auf.
        """
        self.refresh_data_manual(initial_load=initial_load)

    def refresh_data_manual(self, initial_load=False):
        """
        [LÄUFT IM GUI-THREAD]
        Startet einen manuellen, thread-basierten Refresh.
        """
        if not self.winfo_exists():
            return

        print("[BugReportsTab] Manueller Refresh: Starte Worker...")
        self.thread_manager.start_worker(
            self._fetch_reports_data,
            lambda res, err: self._on_manual_refresh_fetched(res, err, initial_load)
        )

    def _on_manual_refresh_fetched(self, result, error, initial_load):
        """
        [LÄUFT IM GUI-THREAD]
        Callback für den manuellen Refresh.
        """
        if not self.winfo_exists():
            return

        if error:
            print(f"[BugReportsTab] Manueller Refresh Fehler: {error}")
        elif isinstance(result, Exception):
            print(f"[BugReportsTab] Manueller Refresh Thread-Fehler: {result}")
        else:
            self._update_reports_ui(result)

        # --- KORREKTUR: AttributeError (Regel 1) ---
        # Ruft die korrekte, nicht-blockierende Funktion im NotificationManager auf
        if not initial_load and self.app and hasattr(self.app, 'notification_manager'):
            print("[BugReportsTab] Manueller Refresh ruft check_for_updates_threaded auf.")
            self.app.notification_manager.check_for_updates_threaded()
        # --- ENDE KORREKTUR ---

    def _update_reports_ui(self, all_reports):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert das Treeview sicher mit den neuen Daten.
        """
        if not self.winfo_exists() or all_reports is None:
            return

        try:
            selected_ids = self.tree.selection()
            scroll_pos = self.tree.yview()

            for item in self.tree.get_children():
                self.tree.delete(item)
            self.reports_data.clear()

            show_archived = self.show_archived_var.get()
            visible_reports = [r for r in all_reports if show_archived or not r.get('archived')]
            self.reports_data = {r['id']: r for r in all_reports}

            active_reports = [r for r in visible_reports if r.get('status') != 'Erledigt']
            completed_reports = [r for r in visible_reports if r.get('status') == 'Erledigt']

            def insert_report(report):
                user = f"{report.get('vorname', '')} {report.get('name', '')}".strip() or "Unbekannt"
                try:
                    ts = datetime.strptime(report['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
                except (ValueError, TypeError):
                    ts = report.get('timestamp', 'N/A')

                tags = []
                status = report.get('status', 'N/A')
                category = report.get('category', 'N/A')

                if report.get('archived'):
                    tags.append('archived')

                if status == 'Erledigt':
                    tags.append('erledigt')
                else:
                    status_tag = status.replace(" ", "_").replace("(", "").replace(")", "").lower()
                    if status and status in self.category_colors:
                        tags.append(status_tag)
                    elif category and category in self.category_colors:
                        tags.append(category.replace(" ", "_").lower())

                values = (category, user, ts, report.get('title', 'N/A'), status)
                self.tree.insert("", tk.END, iid=report['id'], values=values, tags=tags)

            active_reports.sort(key=lambda r: SEVERITY_ORDER.get(r.get('category'), 0), reverse=True)
            for report in active_reports:
                insert_report(report)

            if active_reports and completed_reports:
                self.tree.insert("", tk.END, iid="separator", values=("", "--- ERLEDIGTE MELDUNGEN ---", "", "", ""),
                                 tags=('separator',))

            completed_reports.sort(key=lambda r: r['timestamp'], reverse=True)
            for report in completed_reports:
                insert_report(report)

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

        except Exception as e:
            print(f"[FEHLER] _update_reports_ui: {e}")
            self.clear_details()

    def on_report_selected(self, event):
        # (Unverändert)
        selection = self.tree.selection()
        if "separator" in selection:
            self.clear_details()
            return

        self.feedback_response_bar.grid_remove()
        self.re_request_feedback_button.pack_forget()
        self.close_bug_button.pack_forget()

        if len(selection) != 1:
            self.clear_details()
            return

        try:
            self.selected_report_id = int(selection[0])
        except ValueError:
            self.clear_details()
            return

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
        # (Unverändert)
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
            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                append_admin_note,
                lambda res, err: self._on_db_action_complete(res, err, "Notiz"),
                self.selected_report_id,
                note
            )
            # ----------------------------------

    def re_request_feedback(self):
        if not self.selected_report_id: return
        note = askstring("Erneut anfordern", "Optionale Notiz an den User (z.B. 'Bitte prüfe X nochmal'):", parent=self)
        if note is not None:
            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                self._update_and_add_note,  # Eine Wrapper-Funktion
                lambda res, err: self._on_db_action_complete(res, err, "Feedback-Anforderung"),
                self.selected_report_id,
                "Warte auf Rückmeldung",
                note if note else None
            )
            # -----------------------------------------------

    def close_bug(self):
        if not self.selected_report_id: return
        if messagebox.askyesno("Bestätigen", "Möchtest du diesen Bug-Report wirklich als 'Erledigt' schließen?",
                               parent=self):
            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                update_bug_report_status,
                lambda res, err: self._on_db_action_complete(res, err, "Schließen"),
                self.selected_report_id,
                "Erledigt"
            )
            # ----------------------------------

    def on_category_changed(self, event):
        if not self.selected_report_id: return
        new_category = self.category_combobox_admin.get()
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            update_bug_report_category,
            lambda res, err: self._on_db_action_complete(res, err, "Kategorie"),
            self.selected_report_id,
            new_category
        )
        # ----------------------------------

    def on_status_changed(self, event):
        if not self.selected_report_id: return
        new_status = self.status_combobox.get()
        if new_status in ["Rückmeldung (Offen)", "Rückmeldung (Behoben)"]:
            messagebox.showwarning("Aktion erforderlich",
                                   "Bitte benutze die Buttons 'Feedback erneut anfordern' oder 'Bug schließen', um auf das User-Feedback zu reagieren.",
                                   parent=self)
            self.status_combobox.set(self.reports_data[self.selected_report_id]['status'])
            return
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            update_bug_report_status,
            lambda res, err: self._on_db_action_complete(res, err, "Status"),
            self.selected_report_id,
            new_status
        )
        # ----------------------------------

    def toggle_archive_status(self):
        if not self.selected_report_id: return
        report = self.reports_data.get(self.selected_report_id)
        if not report: return

        action_func = unarchive_bug_report if report.get('archived') else archive_bug_report
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            action_func,
            lambda res, err: self._on_db_action_complete(res, err, "Archivierung"),
            self.selected_report_id
        )
        # ----------------------------------

    def delete_selected_reports(self):
        selected_ids_str = self.tree.selection()
        if not selected_ids_str:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie die zu löschenden Reports aus.", parent=self)
            return

        ids_to_delete = [int(id_str) for id_str in selected_ids_str if id_str != "separator"]
        if not ids_to_delete:
            return

        msg = f"Möchten Sie die {len(ids_to_delete)} ausgewählten Bug-Report(s) wirklich endgültig löschen?"
        if messagebox.askyesno("Löschen bestätigen", msg, icon='warning', parent=self):
            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                delete_bug_reports,
                lambda res, err: self._on_db_action_complete(res, err, "Löschen"),
                ids_to_delete
            )
            # ----------------------------------

    # --- NEUE HILFSFUNKTIONEN für Threads ---

    def _update_and_add_note(self, report_id, new_status, note):
        """
        [LÄUFT IM THREAD]
        Kombiniert zwei DB-Operationen für 're_request_feedback'.
        """
        try:
            if note:
                append_admin_note(report_id, note)
            success, message = update_bug_report_status(report_id, new_status)
            return success, message
        except Exception as e:
            return False, str(e)

    def _on_db_action_complete(self, result, error, action_name="Aktion"):
        """
        [GUI-Thread]
        Generischer Callback für einfache DB-Operationen.
        """
        if not self.winfo_exists(): return

        success, message = result if isinstance(result, tuple) else (None, None)

        if error or isinstance(result, Exception):
            messagebox.showerror("Fehler", f"{action_name} fehlgeschlagen:\n{error or result}", parent=self)
        elif success:
            if message:
                messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_data_manual()  # UI nach Erfolg aktualisieren
        else:
            messagebox.showerror("Fehler", f"{action_name} fehlgeschlagen:\n{message}", parent=self)