# gui/tabs/tasks_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.simpledialog import askstring
from datetime import datetime
from database.db_tasks import (
    get_all_tasks, update_task_status, archive_task,
    unarchive_task, append_task_note, delete_tasks,
    update_task_category, update_task_priority, create_task,
    TASK_PRIORITY_ORDER, TASK_CATEGORIES, TASK_STATUS_VALUES
)


class _CreateTaskDialog(tk.Toplevel):
    """Dialog zur Erstellung einer neuen Aufgabe."""

    # (Diese Klasse bleibt unverändert)
    def __init__(self, parent, categories, priorities):
        super().__init__(parent)
        self.title("Neue Aufgabe erstellen")
        self.transient(parent)
        self.grab_set()
        self.result = None

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Titel:").grid(row=0, column=0, sticky="w", pady=5)
        self.title_entry = ttk.Entry(main_frame, width=60)
        self.title_entry.grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(main_frame, text="Beschreibung:").grid(row=1, column=0, sticky="nw", pady=5)
        self.desc_text = tk.Text(main_frame, height=10, width=60, wrap="word")
        self.desc_text.grid(row=1, column=1, sticky="nsew", pady=5)

        ttk.Label(main_frame, text="Kategorie:").grid(row=2, column=0, sticky="w", pady=5)
        self.category_combo = ttk.Combobox(main_frame, values=categories, state="readonly")
        self.category_combo.grid(row=2, column=1, sticky="ew", pady=5)
        if categories: self.category_combo.current(0)

        ttk.Label(main_frame, text="Priorität:").grid(row=3, column=0, sticky="w", pady=5)
        self.priority_combo = ttk.Combobox(main_frame, values=list(priorities.keys()), state="readonly")
        self.priority_combo.grid(row=3, column=1, sticky="ew", pady=5)
        if priorities: self.priority_combo.set("Mittel")

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))

        ttk.Button(button_frame, text="Erstellen", command=self.on_create).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right")

        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        self.wait_window()

    def on_create(self):
        title = self.title_entry.get().strip()
        description = self.desc_text.get("1.0", tk.END).strip()
        category = self.category_combo.get()
        priority = self.priority_combo.get()

        if not title or not description or not category or not priority:
            messagebox.showwarning("Fehlende Eingabe", "Bitte alle Felder ausfüllen.", parent=self)
            return

        self.result = {
            "title": title,
            "description": description,
            "category": category,
            "priority": priority
        }
        self.destroy()


class TasksTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.admin_user_id = self.app.user_data.get('id')
        self.admin_user_name = f"{self.app.user_data.get('vorname', '')} {self.app.user_data.get('name', '')}".strip()

        # --- NEU: ThreadManager und Schleifen-Steuerung ---
        self.thread_manager = self.app.thread_manager
        self.auto_refresh_active = False
        self.auto_refresh_job_id = None
        # ------------------------------------------------

        self.tasks_data = {}
        self.selected_task_id = None
        self.refresh_interval_ms = 60000

        self.categories = TASK_CATEGORIES
        self.priorities = list(TASK_PRIORITY_ORDER.keys())
        self.status_values = TASK_STATUS_VALUES

        self.priority_colors = {
            "Info": "#E0F7FA",
            "Niedrig": "#FFFFE0",
            "Mittel": "#FFD700",
            "Hoch": "#FFA500",
            "Kritisch": "#B22222",
            "Erledigt": "#90EE90",
        }

        self.setup_ui()
        self.refresh_data_manual(initial_load=True)

        if self.app and self.app.notebook:
            self.app.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
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
        print("[TasksTab] Starte Auto-Refresh-Schleife.")
        self.auto_refresh_loop()

    def stop_auto_refresh(self):
        """Stoppt die Auto-Refresh-Schleife."""
        if not self.auto_refresh_active:
            return
        self.auto_refresh_active = False
        if self.auto_refresh_job_id:
            self.after_cancel(self.auto_refresh_job_id)
            self.auto_refresh_job_id = None
        print("[TasksTab] Stoppe Auto-Refresh-Schleife.")

    def auto_refresh_loop(self):
        """
        [LÄUFT IM GUI-THREAD]
        Der "Kopf" der Schleife. Startet den Worker-Thread.
        """
        if not self.auto_refresh_active or not self.winfo_exists():
            self.auto_refresh_active = False
            return

        print("[TasksTab] Auto-Refresh: Starte Worker...")
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self._fetch_tasks_data,
            self._on_auto_refresh_fetched
        )
        # ----------------------------------

    def _fetch_tasks_data(self):
        """
        [LÄUFT IM THREAD]
        Ruft die blockierende DB-Funktion auf.
        """
        try:
            return get_all_tasks()
        except Exception as e:
            print(f"[FEHLER] _fetch_tasks_data (Thread): {e}")
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
            print(f"[TasksTab] Auto-Refresh Fehler: {error}")
        elif isinstance(result, Exception):
            print(f"[TasksTab] Auto-Refresh Thread-Fehler: {result}")
        else:
            self._update_tasks_ui(result)

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

        ttk.Button(filter_frame, text="Neue Aufgabe", command=self.create_new_task).pack(side="left", padx=(0, 20))

        self.show_archived_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="Archivierte anzeigen", variable=self.show_archived_var,
                        command=self.refresh_data_manual).pack(side="left")
        self.delete_button = ttk.Button(filter_frame, text="Markierte löschen", command=self.delete_selected_tasks)
        self.delete_button.pack(side="left", padx=20)
        ttk.Label(filter_frame, text=f"(Auto-Aktualisierung: {self.refresh_interval_ms / 1000:.0f}s)").pack(
            side="right", padx=10)

        self.tree = ttk.Treeview(tree_frame, columns=("category", "priority", "user", "timestamp", "title", "status"),
                                 show="headings", selectmode="extended")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.heading("category", text="Kategorie", command=lambda: self.sort_by_column("category", False))
        self.tree.heading("priority", text="Priorität", command=lambda: self.sort_by_column("priority", True))
        self.tree.heading("user", text="Ersteller", command=lambda: self.sort_by_column("user", False))
        self.tree.heading("timestamp", text="Zeitpunkt", command=lambda: self.sort_by_column("timestamp", True))
        self.tree.heading("title", text="Titel", command=lambda: self.sort_by_column("title", False))
        self.tree.heading("status", text="Status", command=lambda: self.sort_by_column("status", False))
        self.tree.column("category", width=120)
        self.tree.column("priority", width=80)
        self.tree.column("user", width=130)
        self.tree.column("timestamp", width=140)
        self.tree.column("status", width=100)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_task_selected)

        for name, color in self.priority_colors.items():
            tag_name = name.replace(" ", "_").replace("(", "").replace(")", "").lower()
            self.tree.tag_configure(tag_name, background=color)
        self.tree.tag_configure("archived", foreground="grey", font=("Segoe UI", 9, "italic"))
        self.tree.tag_configure('separator', background='#E0E0E0', foreground='gray')
        self.tree.tag_configure('erledigt', foreground='gray')

        details_frame = ttk.LabelFrame(main_frame, text="Details und Bearbeitung", padding="10")
        details_frame.grid(row=0, column=1, sticky="nsew")
        details_frame.grid_rowconfigure(6, weight=1)
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

        ttk.Label(details_frame, text="Priorität:").grid(row=3, column=0, sticky="w", pady=5)
        self.priority_combobox_admin = ttk.Combobox(details_frame, values=self.priorities, state="disabled")
        self.priority_combobox_admin.grid(row=3, column=1, sticky="ew", pady=5)
        self.priority_combobox_admin.bind("<<ComboboxSelected>>", self.on_priority_changed)

        ttk.Label(details_frame, text="Status:").grid(row=4, column=0, sticky="w", pady=5)
        self.status_combobox = ttk.Combobox(details_frame, values=self.status_values, state="disabled")
        self.status_combobox.grid(row=4, column=1, sticky="ew", pady=5)
        self.status_combobox.bind("<<ComboboxSelected>>", self.on_status_changed)

        ttk.Label(details_frame, text="Notizen (Admin):").grid(row=5, column=0, sticky="nw", pady=2)
        self.notes_text = tk.Text(details_frame, height=10, wrap="word", relief="solid", borderwidth=1,
                                  font=("Segoe UI", 9), state="disabled")
        self.notes_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(2, 5))

        button_bar = ttk.Frame(details_frame)
        button_bar.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.add_note_button = ttk.Button(button_bar, text="Notiz hinzufügen", command=self.add_task_note,
                                          state="disabled")
        self.add_note_button.pack(side="left")
        self.archive_button = ttk.Button(button_bar, text="Archivieren", command=self.toggle_archive_status,
                                         state="disabled")
        self.archive_button.pack(side="right")

    def sort_by_column(self, col, reverse):
        # (Unverändert)
        children = [child for child in self.tree.get_children('') if child != 'separator']
        data = [(self.tree.set(child, col), child) for child in children]

        if col == "priority":
            data.sort(key=lambda item: TASK_PRIORITY_ORDER.get(item[0], 0), reverse=reverse)
        else:
            data.sort(reverse=reverse)

        for index, (val, child) in enumerate(data):
            self.tree.move(child, '', index)

        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    def refresh_data_manual(self, initial_load=False):
        """
        [LÄUFT IM GUI-THREAD]
        Startet einen manuellen, thread-basierten Refresh.
        """
        if not self.winfo_exists():
            return

        print("[TasksTab] Manueller Refresh: Starte Worker...")
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self._fetch_tasks_data,
            # Wir nutzen lambda, um 'initial_load' an den Callback zu übergeben
            lambda res, err: self._on_manual_refresh_fetched(res, err, initial_load)
        )
        # ----------------------------------

    def _on_manual_refresh_fetched(self, result, error, initial_load):
        """
        [LÄUFT IM GUI-THREAD]
        Callback für den manuellen Refresh.
        """
        if not self.winfo_exists():
            return

        if error:
            print(f"[TasksTab] Manueller Refresh Fehler: {error}")
        elif isinstance(result, Exception):
            print(f"[TasksTab] Manueller Refresh Thread-Fehler: {result}")
        else:
            self._update_tasks_ui(result)

        if not initial_load and self.app and hasattr(self.app, 'notification_manager'):
            print("[TasksTab] Manueller Refresh ruft check_for_updates_threaded auf.")
            self.app.notification_manager.check_for_updates_threaded()

    def _update_tasks_ui(self, all_tasks):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert das Treeview sicher mit den neuen Daten.
        """
        if not self.winfo_exists() or all_tasks is None:
            return

        try:
            selected_ids = self.tree.selection()
            scroll_pos = self.tree.yview()

            for item in self.tree.get_children():
                self.tree.delete(item)
            self.tasks_data.clear()

            show_archived = self.show_archived_var.get()

            visible_tasks = [r for r in all_tasks if show_archived or not r.get('archived')]
            self.tasks_data = {r['id']: r for r in all_tasks}

            active_tasks = [r for r in visible_tasks if r.get('status') != 'Erledigt']
            completed_tasks = [r for r in visible_tasks if r.get('status') == 'Erledigt']

            def insert_task(task):
                user = f"{task.get('vorname', '')} {task.get('name', '')}".strip() or "Unbekannt"
                try:
                    ts = datetime.strptime(task['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
                except (ValueError, TypeError):
                    ts = task.get('timestamp', 'N/A')

                tags = []
                status = task.get('status', 'N/A')
                priority = task.get('priority', 'N/A')

                if task.get('archived'):
                    tags.append('archived')

                if status == 'Erledigt':
                    tags.append('erledigt')
                elif priority and priority in self.priority_colors:
                    tags.append(priority.replace(" ", "_").lower())

                values = (task.get('category', 'N/A'), priority, user, ts, task.get('title', 'N/A'), status)
                self.tree.insert("", tk.END, iid=task['id'], values=values, tags=tags)

            for task in active_tasks:
                insert_task(task)

            if active_tasks and completed_tasks:
                self.tree.insert("", tk.END, iid="separator", values=("", "", "--- ERLEDIGTE AUFGABEN ---", "", "", ""),
                                 tags=('separator',))

            for task in completed_tasks:
                insert_task(task)

            if selected_ids:
                valid_ids = [sid for sid in selected_ids if self.tree.exists(sid)]
                if valid_ids:
                    self.tree.selection_set(valid_ids)
                    if len(valid_ids) == 1:
                        self.on_task_selected(None)
                else:
                    self.clear_details()
            else:
                self.clear_details()

            self.tree.yview_moveto(scroll_pos[0])

        except Exception as e:
            print(f"[FEHLER] _update_tasks_ui: {e}")
            self.clear_details()

    def on_task_selected(self, event):
        """[GUI-Thread] Zeigt Details für die Auswahl an (keine DB-Abfrage)."""
        selection = self.tree.selection()
        if "separator" in selection:
            self.clear_details()
            return
        if len(selection) != 1:
            self.clear_details()
            return

        try:
            self.selected_task_id = int(selection[0])
        except ValueError:
            self.clear_details()
            return

        task = self.tasks_data.get(self.selected_task_id)
        if not task:
            self.clear_details()
            return

        self.title_var.set(task.get('title', 'Kein Titel'))
        description = task.get('description') or ''
        self.description_text.config(state="normal")
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", description)
        self.description_text.config(state="disabled")

        self.category_combobox_admin.config(state="readonly")
        self.category_combobox_admin.set(task.get('category', ''))

        self.priority_combobox_admin.config(state="readonly")
        self.priority_combobox_admin.set(task.get('priority', ''))

        self.status_combobox.config(state="readonly")
        self.status_combobox.set(task.get('status', ''))

        admin_notes = task.get('admin_notes') or ''
        self.notes_text.config(state="normal")
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", admin_notes.strip())
        self.notes_text.config(state="disabled")

        self.add_note_button.config(state="normal")
        self.archive_button.config(state="normal")
        self.archive_button.config(text="Dearchivieren" if task.get('archived') else "Archivieren")

    def clear_details(self):
        """[GUI-Thread] Setzt die Detailansicht zurück."""
        self.selected_task_id = None
        self.title_var.set("")
        self.description_text.config(state="normal");
        self.description_text.delete("1.0", tk.END);
        self.description_text.config(state="disabled")
        self.category_combobox_admin.set("");
        self.category_combobox_admin.config(state="disabled")
        self.priority_combobox_admin.set("");
        self.priority_combobox_admin.config(state="disabled")
        self.status_combobox.set("");
        self.status_combobox.config(state="disabled")
        self.notes_text.config(state="normal");
        self.notes_text.delete("1.0", tk.END);
        self.notes_text.config(state="disabled")
        self.add_note_button.config(state="disabled")
        self.archive_button.config(state="disabled")
        self.archive_button.config(text="Archivieren")

    # --- Aktionen (Aufrufe an refresh_data_manual geändert) ---

    def create_new_task(self):
        dialog = _CreateTaskDialog(self, self.categories, TASK_PRIORITY_ORDER)
        result = dialog.result

        if result:
            # --- KORREKTUR: 'kwargs=' entfernt, stattdessen 'target_func_kwargs' ---
            # (Annahme: Der ThreadManager unterstützt 'target_func_kwargs' für benannte Argumente)
            # NEIN, mein ThreadManager war einfacher. Wir müssen die Argumente positional übergeben.

            # --- KORREKTUR 2: Argumente positional übergeben ---
            self.thread_manager.start_worker(
                create_task,
                self._on_task_created,
                self.admin_user_id,  # creator_admin_id
                result["title"],  # title
                result["description"],  # description
                result["category"],  # category
                result["priority"]  # priority
            )
            # ----------------------------------------------------

    def _on_task_created(self, result, error):
        if not self.winfo_exists(): return

        success, message = result if isinstance(result, tuple) else (None, None)

        if error or isinstance(result, Exception):
            messagebox.showerror("Fehler", f"Aufgabe konnte nicht erstellt werden:\n{error or result}", parent=self)
        elif success:
            messagebox.showinfo("Erfolg", "Neue Aufgabe erfolgreich erstellt.", parent=self)
            self.refresh_data_manual()
        else:
            messagebox.showerror("Fehler", f"Aufgabe konnte nicht erstellt werden:\n{message}", parent=self)

    def add_task_note(self):
        if not self.selected_task_id: return
        note = askstring("Neue Notiz", "Bitte gib deine Notiz ein:", parent=self)
        if note:
            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                append_task_note,
                lambda res, err: self._on_db_action_complete(res, err, "Notiz"),
                self.selected_task_id,
                note,
                self.admin_user_name
            )
            # ----------------------------------

    def on_category_changed(self, event):
        if not self.selected_task_id: return
        new_category = self.category_combobox_admin.get()
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            update_task_category,
            lambda res, err: self._on_db_action_complete(res, err, "Kategorie"),
            self.selected_task_id,
            new_category
        )
        # ----------------------------------

    def on_priority_changed(self, event):
        if not self.selected_task_id: return
        new_priority = self.priority_combobox_admin.get()
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            update_task_priority,
            lambda res, err: self._on_db_action_complete(res, err, "Priorität"),
            self.selected_task_id,
            new_priority
        )
        # ----------------------------------

    def on_status_changed(self, event):
        if not self.selected_task_id: return
        new_status = self.status_combobox.get()
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            update_task_status,
            lambda res, err: self._on_db_action_complete(res, err, "Status"),
            self.selected_task_id,
            new_status
        )
        # ----------------------------------

    def toggle_archive_status(self):
        if not self.selected_task_id: return
        task = self.tasks_data.get(self.selected_task_id)
        if not task: return

        action_func = unarchive_task if task.get('archived') else archive_task
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            action_func,
            lambda res, err: self._on_db_action_complete(res, err, "Archivierung"),
            self.selected_task_id
        )
        # ----------------------------------

    def delete_selected_tasks(self):
        selected_ids_str = self.tree.selection()
        if not selected_ids_str:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie die zu löschenden Aufgaben aus.", parent=self)
            return

        ids_to_delete = [int(id_str) for id_str in selected_ids_str if id_str != "separator"]
        if not ids_to_delete:
            return

        msg = f"Möchten Sie die {len(ids_to_delete)} ausgewählte(n) Aufgabe(n) wirklich endgültig löschen?"
        if messagebox.askyesno("Löschen bestätigen", msg, icon='warning', parent=self):
            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                delete_tasks,
                lambda res, err: self._on_db_action_complete(res, err, "Löschen"),
                ids_to_delete
            )
            # ----------------------------------

    def _on_db_action_complete(self, result, error, action_name="Aktion"):
        """
        [GUI-Thread]
        Generischer Callback für einfache DB-Operationen (Aktualisieren, Löschen etc.)
        """
        if not self.winfo_exists(): return

        success, message = result if isinstance(result, tuple) else (None, None)

        if error or isinstance(result, Exception):
            messagebox.showerror("Fehler", f"{action_name} fehlgeschlagen:\n{error or result}", parent=self)
        elif success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_data_manual()  # UI nach Erfolg aktualisieren
        else:
            messagebox.showerror("Fehler", f"{action_name} fehlgeschlagen:\n{message}", parent=self)