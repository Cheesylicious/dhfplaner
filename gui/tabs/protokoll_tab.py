# gui/tabs/protokoll_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_reports import get_all_logs_formatted, get_login_logout_logs_formatted, delete_activity_logs


class ProtokollTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.log_data_cache = []  # Cache für die geladenen Logs

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # --- Filter- und Aktionsleiste ---
        filter_frame = ttk.Frame(main_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(filter_frame, text="Filter:").pack(side="left", padx=(0, 5))

        self.filter_var = tk.StringVar(value="Alle")
        self.filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_var,
                                         values=["Alle", "Login/Logout"], state="readonly", width=15)
        self.filter_combo.pack(side="left", padx=5)
        self.filter_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)

        self.refresh_button = ttk.Button(filter_frame, text="Aktualisieren", command=self.load_data)
        self.refresh_button.pack(side="left", padx=5)

        self.delete_button = ttk.Button(filter_frame, text="Markierte löschen", command=self.delete_selected_logs)
        self.delete_button.pack(side="left", padx=20)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side="right", padx=(5, 0))
        ttk.Label(filter_frame, text="Suchen:").pack(side="right")
        self.search_var.trace_add("write", self.filter_treeview)

        # --- Treeview für die Logs ---
        tree_container = ttk.Frame(main_frame)
        tree_container.grid(row=1, column=0, sticky="nsew")
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # Spalten: id (hidden), timestamp, user, action_type, details, duration
        self.tree = ttk.Treeview(tree_container,
                                 columns=("timestamp", "user", "action_type", "details", "duration"),
                                 show="headings", selectmode="extended")

        # Spalten-Konfiguration
        self.tree.heading("timestamp", text="Zeitstempel", command=lambda: self.sort_by_column("timestamp", True))
        self.tree.heading("user", text="Benutzer", command=lambda: self.sort_by_column("user", False))
        self.tree.heading("action_type", text="Aktion", command=lambda: self.sort_by_column("action_type", False))
        self.tree.heading("details", text="Details", command=lambda: self.sort_by_column("details", False))
        self.tree.heading("duration", text="Dauer", command=lambda: self.sort_by_column("duration", False))

        self.tree.column("timestamp", width=160, stretch=False)
        self.tree.column("user", width=180, stretch=False)
        self.tree.column("action_type", width=140, stretch=False)
        self.tree.column("details", width=500, stretch=True)
        self.tree.column("duration", width=100, stretch=False, anchor="e")

        # Scrollbars
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, columnspan=2, sticky="ew")

        # Details-Textfeld (Nur-Lesen)
        self.details_text = tk.Text(main_frame, height=5, wrap="word", state="disabled", font=("Segoe UI", 9))
        self.details_text.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self.tree.bind("<<TreeviewSelect>>", self.on_item_selected)

    def load_data(self):
        """Lädt die Daten basierend auf dem Filter aus der DB."""
        self.tree.delete(*self.tree.get_children())
        filter_mode = self.filter_var.get()

        if filter_mode == "Alle":
            self.log_data_cache = get_all_logs_formatted()
        else:  # "Login/Logout"
            self.log_data_cache = get_login_logout_logs_formatted()

        self.populate_treeview(self.log_data_cache)

    def populate_treeview(self, logs):
        """Füllt das Treeview mit den übergebenen Log-Daten."""
        self.tree.delete(*self.tree.get_children())

        for log in logs:
            try:
                # Formatierung des Zeitstempels
                ts_obj = datetime.strptime(log['timestamp'], '%Y-%m-%d %H:%M:%S')
                ts_formatted = ts_obj.strftime('%d.%m.%Y %H:%M:%S')
            except (ValueError, TypeError):
                ts_formatted = log.get('timestamp', 'N/A')

            user = log.get('user_name', 'System')
            action = log.get('action_type', 'N/A')
            details = log.get('details', '')
            duration = log.get('duration', '')  # Nur bei Login/Logout relevant

            # iid (Item ID) ist die DB-ID für die Löschfunktion
            log_db_id = log.get('id', 'N/A')

            self.tree.insert("", tk.END, iid=log_db_id,
                             values=(ts_formatted, user, action, details, duration))

    def on_filter_changed(self, event=None):
        """Wird aufgerufen, wenn der Filter geändert wird."""
        self.load_data()
        self.search_var.set("")  # Suchfeld zurücksetzen
        self.clear_details_text()

    def filter_treeview(self, *args):
        """Filtert die im Treeview angezeigten Daten basierend auf der Suche (ohne DB-Aufruf)."""
        search_term = self.search_var.get().lower()

        # Daten aus dem Cache filtern
        filtered_logs = []
        if not search_term:
            filtered_logs = self.log_data_cache
        else:
            for log in self.log_data_cache:
                # Durchsuche alle relevanten Felder
                if (search_term in str(log.get('timestamp', '')).lower() or
                        search_term in str(log.get('user_name', '')).lower() or
                        search_term in str(log.get('action_type', '')).lower() or
                        search_term in str(log.get('details', '')).lower()):
                    filtered_logs.append(log)

        self.populate_treeview(filtered_logs)
        self.clear_details_text()

    def on_item_selected(self, event=None):
        """Zeigt die Details des ausgewählten Eintrags im Textfeld an."""
        selection = self.tree.selection()
        if len(selection) == 1:
            item_id = selection[0]
            item_values = self.tree.item(item_id, "values")
            if item_values:
                # Hole Details (Spalte 3) und Zeitstempel (Spalte 0)
                ts = item_values[0]
                user = item_values[1]
                action = item_values[2]
                details = item_values[3]
                full_text = f"Zeit: {ts}\nBenutzer: {user}\nAktion: {action}\n---\nDetails:\n{details}"

                self.details_text.config(state="normal")
                self.details_text.delete("1.0", tk.END)
                self.details_text.insert("1.0", full_text)
                self.details_text.config(state="disabled")
        else:
            self.clear_details_text()

    def clear_details_text(self):
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.config(state="disabled")

    def delete_selected_logs(self):
        """Löscht die im Treeview ausgewählten Einträge."""
        selected_ids = self.tree.selection()
        if not selected_ids:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie die zu löschenden Einträge aus.", parent=self)
            return

        # Die 'selection()' gibt die 'iids' zurück, die wir als DB-IDs gespeichert haben
        try:
            ids_to_delete = [int(id_str) for id_str in selected_ids if id_str.isdigit()]
        except ValueError:
            messagebox.showerror("Fehler", "Auswahl enthält ungültige IDs.", parent=self)
            return

        if not ids_to_delete:
            messagebox.showwarning("Keine Auswahl", "Keine gültigen Einträge zum Löschen ausgewählt.", parent=self)
            return

        msg = f"Möchten Sie die {len(ids_to_delete)} ausgewählten Protokolleinträge wirklich endgültig löschen?"
        if messagebox.askyesno("Löschen bestätigen", msg, icon='warning', parent=self):
            success, message = delete_activity_logs(ids_to_delete)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_data()  # Daten neu laden
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def sort_by_column(self, col, reverse):
        """Sortiert das Treeview nach einer Spalte."""
        # Daten aus dem Treeview extrahieren
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]

        # Sortieren
        # Spezielle Sortierung für Zeitstempel
        if col == "timestamp":
            def sort_key(item):
                try:
                    return datetime.strptime(item[0], '%d.%m.%Y %H:%M:%S')
                except ValueError:
                    return datetime.min  # Fallback für ungültige Daten

            data.sort(key=sort_key, reverse=reverse)
        else:
            data.sort(key=lambda item: str(item[0]).lower(), reverse=reverse)

        # Neu anordnen
        for index, (val, child) in enumerate(data):
            self.tree.move(child, '', index)

        # Umgekehrte Sortierrichtung für den nächsten Klick
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))

    def refresh_data(self):
        """Öffentliche Methode zum Aktualisieren (alias für load_data)."""
        self.load_data()