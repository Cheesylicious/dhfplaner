# gui/tabs/protokoll_tab.py
import tkinter as tk
from tkinter import ttk
from database.db_reports import get_login_logout_logs_formatted


class ProtokollTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(button_frame, text="An- und Abmelde-Protokoll", font=('Segoe UI', 12, 'bold')).pack(side="left",
                                                                                                      padx=(0, 10))
        ttk.Button(button_frame, text="Aktualisieren", command=self.refresh_data).pack(side="left")

        # Spalten für den neuen Reiter (mit Dauer)
        columns = ("timestamp", "user", "action", "details", "duration")
        self.log_tree = ttk.Treeview(self, columns=columns, show="headings")
        self.log_tree.heading("timestamp", text="Zeitstempel")
        self.log_tree.heading("user", text="Benutzer")
        self.log_tree.heading("action", text="Aktion")
        self.log_tree.heading("details", text="Details")
        self.log_tree.heading("duration", text="Dauer")

        self.log_tree.column("timestamp", width=150, anchor="w")
        self.log_tree.column("user", width=150, anchor="w")
        self.log_tree.column("action", width=150, anchor="w")
        self.log_tree.column("details", width=400, anchor="w")
        self.log_tree.column("duration", width=100, anchor="w")
        self.log_tree.pack(fill="both", expand=True)

        self.refresh_data()

    def refresh_data(self):
        """Aktualisiert die Daten im Treeview."""
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

        # Neue Funktion zum Abrufen der Protokoll-Logs verwenden
        logs = get_login_logout_logs_formatted()
        for log_entry in logs:
            self.log_tree.insert("", tk.END, values=(
                log_entry['timestamp'],
                log_entry['user_name'],
                log_entry['action_type'],
                log_entry['details'],
                log_entry.get('duration', '')
            ))