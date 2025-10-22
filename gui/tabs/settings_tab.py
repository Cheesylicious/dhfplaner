# gui/tabs/settings_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
# WICHTIG: db_core muss hier importiert werden
from database.db_core import run_db_update_v1, run_db_update_is_approved


class SettingsTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        self.setup_ui()

    def setup_ui(self):
        # Frame für allgemeine Einstellungen
        general_frame = ttk.LabelFrame(self, text="🛠️ Datenbank-Wartung und Updates", padding=(20, 10))
        general_frame.pack(fill="x", padx=20, pady=20, anchor='n')

        # --- 1. Update für 'is_approved' Spalte (Fehlerbehebung) ---
        ttk.Label(general_frame,
                  text="Fehler 'Unknown column is_approved' bei Registrierung beheben:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(10, 5))

        ttk.Button(general_frame,
                   text="DB Update: Benutzer-Freischaltung Spalte hinzufügen",
                   command=self.run_update_is_approved,
                   style='Danger.TButton').pack(fill='x', padx=5, pady=5)

        # Separator
        ttk.Separator(general_frame, orient='horizontal').pack(fill='x', pady=15)

        # --- 2. Update für Chat (Bestehende Funktion) ---
        ttk.Label(general_frame,
                  text="Datenbank-Update für die Chat-Funktion (last_seen und chat_messages):",
                  font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(10, 5))

        ttk.Button(general_frame,
                   text="DB Update: Chat-Funktion aktivieren/reparieren",
                   command=self.run_chat_update,
                   style='Success.TButton').pack(fill='x', padx=5, pady=5)

    def run_update_is_approved(self):
        """Löst das Update für die is_approved Spalte aus."""
        if not messagebox.askyesno("Update bestätigen",
                                   "Sind Sie sicher, dass Sie die fehlende 'is_approved' Spalte hinzufügen möchten? Dies behebt den Registrierungsfehler.",
                                   parent=self):
            return

        success, message = run_db_update_is_approved()
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
        else:
            messagebox.showerror("Fehler", f"Update fehlgeschlagen: {message}", parent=self)

    def run_chat_update(self):
        """Löst das Update für die Chat-Funktion aus."""
        if not messagebox.askyesno("Update bestätigen",
                                   "Sind Sie sicher, dass Sie das Update für die Chat-Funktion ausführen möchten? (last_seen Spalte und chat_messages Tabelle)",
                                   parent=self):
            return

        success, message = run_db_update_v1()
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
        else:
            messagebox.showerror("Fehler", f"Update fehlgeschlagen: {message}", parent=self)