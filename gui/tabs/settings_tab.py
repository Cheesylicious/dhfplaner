# gui/tabs/settings_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
# --- NEUE IMPORTE ---
from database.db_core import (
    run_db_update_v1, run_db_update_is_approved,
    load_config_json, save_config_json, VACATION_RULES_CONFIG_KEY
)
from database.db_users import admin_batch_update_vacation_entitlements


# --- ENDE NEU ---


class SettingsTab(ttk.Frame):
    def __init__(self, master, session_user):  # Session-User wird benötigt
        super().__init__(master)
        # --- NEU: Session-User speichern ---
        self.session_user = session_user
        self.vacation_rules = []  # Cache für die Regeln
        # --- ENDE NEU ---

        self.setup_ui()
        # --- NEU: Regeln laden ---
        self.load_rules_data()
        # --- ENDE NEU ---

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

        # --- 3. NEU: FRAME FÜR URLAUBSREGELN ---
        vacation_frame = ttk.LabelFrame(self, text="📅 Urlaubsanspruch nach Dienstjahren", padding=(20, 10))
        vacation_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        vacation_frame.columnconfigure(0, weight=1)
        vacation_frame.rowconfigure(0, weight=1)

        # Treeview zur Anzeige der Regeln
        self.rules_tree = ttk.Treeview(vacation_frame, columns=("years", "days"), show="headings")
        self.rules_tree.heading("years", text="Mindest-Dienstjahre")
        self.rules_tree.heading("days", text="Urlaubstage")
        self.rules_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Scrollbar
        scrollbar = ttk.Scrollbar(vacation_frame, orient="vertical", command=self.rules_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.rules_tree.configure(yscrollcommand=scrollbar.set)

        # Button-Frame rechts
        btn_frame = ttk.Frame(vacation_frame)
        btn_frame.grid(row=0, column=2, sticky="ns", padx=(10, 0))

        ttk.Button(btn_frame, text="Regel Hinzufügen", command=self.add_rule).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Regel Entfernen", command=self.remove_rule).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Regeln Speichern", command=self.save_rules, style="Success.TButton").pack(fill="x",
                                                                                                              pady=2)

        ttk.Separator(btn_frame, orient='horizontal').pack(fill='x', pady=10)

        ttk.Button(btn_frame, text="Ansprüche JETZT\naktualisieren", command=self.run_batch_update,
                   style="Accent.TButton").pack(fill="x", pady=2)
        # --- ENDE NEU ---

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

    # --- NEUE METHODEN FÜR URLAUBSREGELN ---

    def load_rules_data(self):
        """Lädt die Regeln aus der DB und füllt den Treeview."""
        self.rules_tree.delete(*self.rules_tree.get_children())

        config_data = load_config_json(VACATION_RULES_CONFIG_KEY)

        if not config_data or not isinstance(config_data, list):
            # Standard-Regel (Basisanspruch)
            self.vacation_rules = [{"years": 0, "days": 30}]
        else:
            # Sortieren für die Anzeige (nach Jahren aufsteigend)
            self.vacation_rules = sorted(config_data, key=lambda r: r.get('years', 0))

        for rule in self.vacation_rules:
            self.rules_tree.insert("", "end", values=(rule["years"], rule["days"]))

    def add_rule(self):
        """Fügt eine neue Regel hinzu (via Dialog)."""
        try:
            years = simpledialog.askinteger("Dienstjahre", "Nach wie vielen vollen Dienstjahren gilt die Regel?",
                                            parent=self, minvalue=0)
            if years is None:
                return

            days = simpledialog.askinteger("Urlaubstage", f"Wie viele Urlaubstage gibt es ab {years} Jahren?",
                                           parent=self, minvalue=0)
            if days is None:
                return

            # Prüfen, ob die Regel (Jahre) schon existiert
            for item_id in self.rules_tree.get_children():
                existing_years = self.rules_tree.item(item_id, "values")[0]
                if int(existing_years) == years:
                    messagebox.showwarning("Doppelt",
                                           f"Eine Regel für {years} Jahre existiert bereits. Bitte entfernen Sie die alte Regel zuerst.",
                                           parent=self)
                    return

            # Zur GUI hinzufügen
            item_id = self.rules_tree.insert("", "end", values=(years, days))
            # Sortieren
            self.sort_treeview()
            self.rules_tree.selection_set(item_id)

        except ValueError:
            messagebox.showerror("Ungültig", "Bitte geben Sie gültige Zahlen ein.", parent=self)
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein Fehler ist aufgetreten: {e}", parent=self)

    def remove_rule(self):
        """Entfernt die ausgewählte Regel."""
        selected_item = self.rules_tree.selection()
        if not selected_item:
            messagebox.showwarning("Auswahl fehlt",
                                   "Bitte wählen Sie zuerst eine Regel aus, die Sie entfernen möchten.", parent=self)
            return

        if not messagebox.askyesno("Löschen", "Möchten Sie die ausgewählte Regel wirklich entfernen?", parent=self):
            return

        self.rules_tree.delete(selected_item)

    def sort_treeview(self):
        """Sortiert den Treeview nach Jahren (aufsteigend)."""
        items = [(int(self.rules_tree.item(i, "values")[0]), i) for i in self.rules_tree.get_children()]
        items.sort()
        for index, (years, item_id) in enumerate(items):
            self.rules_tree.move(item_id, "", index)

    def save_rules(self):
        """Speichert die Regeln aus dem Treeview in der Datenbank."""
        new_rules = []
        try:
            for item_id in self.rules_tree.get_children():
                values = self.rules_tree.item(item_id, "values")
                rule = {"years": int(values[0]), "days": int(values[1])}
                new_rules.append(rule)
        except (ValueError, TypeError):
            messagebox.showerror("Fehler", "Ungültige Daten im Treeview.", parent=self)
            return

        if not new_rules:
            if not messagebox.askyesno("Warnung",
                                       "Sie sind im Begriff, alle Regeln zu löschen. Der Standard-Urlaubsanspruch (30 Tage) wird dann verwendet. Fortfahren?",
                                       parent=self):
                return

        if save_config_json(VACATION_RULES_CONFIG_KEY, new_rules):
            self.vacation_rules = new_rules  # Cache aktualisieren
            messagebox.showinfo("Gespeichert", "Die Urlaubsregeln wurden erfolgreich gespeichert.", parent=self)
        else:
            messagebox.showerror("Fehler", "Die Regeln konnten nicht in der Datenbank gespeichert werden.", parent=self)

    def run_batch_update(self):
        """Startet das Batch-Update für alle Benutzer."""
        if not self.session_user:
            messagebox.showerror("Fehler", "Sitzungsbenutzer nicht gefunden.", parent=self)
            return

        if not messagebox.askyesno("Update Bestätigen",
                                   "Möchten Sie jetzt die Urlaubsansprüche (Gesamt UND Rest) aller aktiven Mitarbeiter basierend auf den gespeicherten Regeln neu berechnen?\n\n"
                                   "Dies sollte typischerweise nur einmal pro Jahr oder nach einer Regeländerung geschehen.",
                                   parent=self):
            return

        try:
            current_user_id = self.session_user['id']
            success, message = admin_batch_update_vacation_entitlements(current_user_id)

            if success:
                messagebox.showinfo("Erfolg", f"Update abgeschlossen.\n{message}", parent=self)
            else:
                messagebox.showerror("Fehler", f"Update fehlgeschlagen:\n{message}", parent=self)
        except Exception as e:
            messagebox.showerror("Kritischer Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self)

    # --- ENDE NEU ---