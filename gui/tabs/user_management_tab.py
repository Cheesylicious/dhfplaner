# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from gui.user_edit_window import UserEditWindow
from gui.dialogs.user_order_window import UserOrderWindow
from database.db_users import (get_all_users_with_details, delete_user, save_user_order, get_ordered_users_for_schedule,
                               get_pending_approval_users, approve_user)
from database.db_core import ROLE_HIERARCHY


class UserManagementTab(ttk.Frame):
    def __init__(self, master, current_user_data):
        super().__init__(master)
        # HINWEIS: master ist das Notebook. Wir brauchen den MainAdminWindow
        # Wir gehen davon aus, dass current_user_data hier das AdminWindow-Objekt ist,
        # da der Tab-Lader es so übergibt. Wir extrahieren die ID.
        if isinstance(current_user_data, dict):
            # Normaler Fall im Lade-Thread, wenn direkt user_data übergeben wird
            self.current_user_id = current_user_data['id']
            self.master_window = master.winfo_toplevel()  # Nur eine Annahme
        else:
            # Wenn das MainAdminWindow-Objekt übergeben wird (häufig in den Tabs)
            self.current_user_id = current_user_data.user_data['id']
            self.master_window = current_user_data  # Dies ist das MainAdminWindow

        self.user_data = []  # Liste aller Benutzer

        # --- Frames ---
        self.top_frame = ttk.Frame(self)
        self.top_frame.pack(fill='x', padx=10, pady=(10, 0))

        # Der pending_frame wird als erstes angezeigt (vor der Benutzerliste)
        self.pending_frame = ttk.Frame(self, padding=(10, 0))
        self.pending_frame.pack(fill='x', pady=(5, 10))

        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.setup_ui()
        self.load_data()
        self.check_pending_approvals()

    def setup_ui(self):
        # Top Frame (Buttons)
        ttk.Button(self.top_frame, text="Benutzer bearbeiten", command=self.open_edit_window).pack(side='left', padx=5)
        ttk.Button(self.top_frame, text="Benutzer löschen", command=self.delete_selected_user).pack(side='left', padx=5)
        ttk.Button(self.top_frame, text="Reihenfolge/Sichtbarkeit", command=self.open_order_window).pack(side='left',
                                                                                                         padx=5)

        # Treeview (Benutzerliste)
        columns = ("ID", "Vorname", "Name", "Rolle", "Geburtstag", "Telefon", "Diensthund", "Urlaub Gesamt",
                   "Urlaub Rest", "Freigeschaltet")
        self.tree = ttk.Treeview(self.main_frame, columns=columns, show="headings")

        # Scrollbar hinzufügen
        vsb = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(fill='both', expand=True)

        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(self.tree, c, False))
            self.tree.column(col, width=100, anchor=tk.CENTER)

        self.tree.column("Vorname", width=120, anchor=tk.W)
        self.tree.column("Name", width=120, anchor=tk.W)
        self.tree.column("ID", width=50)
        self.tree.column("Freigeschaltet", width=100)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind('<Double-1>', self.open_edit_window)

    # =====================================================================================
    # --- FREISCHALTUNGSLOGIK ---
    # =====================================================================================

    def check_pending_approvals(self):
        """Prüft und zeigt Benachrichtigungen für ausstehende Freischaltungen an."""
        for widget in self.pending_frame.winfo_children():
            widget.destroy()

        pending_users = get_pending_approval_users()
        count = len(pending_users)

        if count > 0:
            self.pending_frame.configure(relief='solid', borderwidth=1, padding=10)

            # Titel
            title_label = ttk.Label(self.pending_frame, text=f"⚠️ {count} neue(r) Benutzer warten auf Freischaltung",
                                    font=('Segoe UI', 12, 'bold'), foreground='red')
            title_label.pack(anchor='w', pady=(0, 5))

            # Liste der Benutzer
            for user in pending_users:
                user_text = f"{user['vorname']} {user['name']} (Registriert: {user['entry_date']})"
                row_frame = ttk.Frame(self.pending_frame)
                row_frame.pack(fill='x', pady=2)

                ttk.Label(row_frame, text=user_text).pack(side='left')

                # Button zum Freischalten
                approve_btn = ttk.Button(row_frame, text="Freischalten",
                                         command=lambda u_id=user['id']: self.approve_user_action(u_id),
                                         style='Accent.TButton')
                approve_btn.pack(side='right', padx=10)

                # Button zum Löschen (Ablehnen)
                delete_btn = ttk.Button(row_frame, text="Löschen/Ablehnen",
                                        command=lambda u_id=user['id'],
                                                       u_name=f"{user['vorname']} {user['name']}": self.delete_user_action(
                                            u_id, u_name),
                                        style='Danger.TButton')
                delete_btn.pack(side='right')

        else:
            # Entferne visuelle Begrenzung wenn leer
            self.pending_frame.configure(relief='flat', borderwidth=0, padding=0)

    def approve_user_action(self, user_id):
        """Führt die Freischaltung des Benutzers durch."""
        success, message = approve_user(user_id, self.current_user_id)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.load_data()  # Hauptliste aktualisieren
            self.check_pending_approvals()  # Pending-Liste aktualisieren
            # Informiere das Hauptfenster, dass eine Aktualisierung der Benachrichtigungen nötig ist
            if hasattr(self.master_window, 'check_for_updates'):
                self.master_window.check_for_updates()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def delete_user_action(self, user_id, user_name):
        """Löscht einen Benutzer, z.B. wenn die Registrierung abgelehnt wird."""
        if messagebox.askyesno("Benutzer löschen",
                               f"Sind Sie sicher, dass Sie den Benutzer {user_name} dauerhaft löschen (die Registrierung ablehnen) möchten? Alle Daten werden entfernt.",
                               parent=self):

            # Nutzt die bestehende delete_user Funktion
            success, message = delete_user(user_id, self.current_user_id)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_data()
                self.check_pending_approvals()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    # =====================================================================================
    # --- BESTEHENDE METHODEN ---
    # =====================================================================================

    def load_data(self):
        """Lädt alle Benutzerdaten und befüllt das Treeview."""
        # Lösche vorhandene Einträge
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Verwende get_all_users_with_details, da dieser Query alle Spalten inkl. is_approved abruft
        self.user_data = get_all_users_with_details()

        for user in self.user_data:
            # Defensive Abfrage der is_approved Spalte
            is_approved_value = user.get('is_approved', 1)
            is_approved = "Ja" if is_approved_value == 1 else "Nein ❌"

            # Bestimme den Tag-Stil
            tag = 'approved' if is_approved_value == 1 else 'pending'

            self.tree.insert('', tk.END, iid=user['id'], tags=(tag,), values=(
                user['id'],
                user['vorname'],
                user['name'],
                user['role'],
                user.get('geburtstag', ''),
                user.get('telefon', ''),
                user.get('diensthund', ''),
                user.get('urlaub_gesamt', ''),
                user.get('urlaub_rest', ''),
                is_approved
            ))

        # Konfiguriere Tags für Farben
        self.tree.tag_configure('pending', background='#ffe0e0', foreground='red')  # Rot für ausstehende Freischaltung
        self.tree.tag_configure('approved', background='white', foreground='black')  # Normal

        # Nach dem Laden der Daten, Status der ausstehenden Freischaltungen prüfen
        self.check_pending_approvals()

    def on_select(self, event):
        # Hält die ausgewählte Benutzer-ID
        selected_item = self.tree.selection()
        if selected_item:
            self.selected_user_id = int(selected_item[0])
        else:
            self.selected_user_id = None

    def get_selected_user(self):
        selected_item = self.tree.selection()
        if selected_item:
            user_id = int(selected_item[0])
            return next((u for u in self.user_data if u['id'] == user_id), None)
        return None

    def open_edit_window(self, event=None):
        user = self.get_selected_user()
        if user:
            # Stelle sicher, dass das Passwort-Hash nicht mitgegeben wird
            UserEditWindow(self.master, user, self.current_user_id, self.load_data)
        elif event is None:  # Nur eine Warnung anzeigen, wenn der Button geklickt wird
            messagebox.showinfo("Auswahl erforderlich", "Bitte wählen Sie einen Benutzer zum Bearbeiten aus.")

    def delete_selected_user(self):
        user = self.get_selected_user()
        if not user:
            messagebox.showinfo("Auswahl erforderlich", "Bitte wählen Sie einen Benutzer zum Löschen aus.")
            return

        user_name = f"{user['vorname']} {user['name']}"
        if messagebox.askyesno("Löschen bestätigen",
                               f"Sind Sie sicher, dass Sie den Benutzer '{user_name}' dauerhaft löschen möchten?",
                               parent=self):
            success, message = delete_user(user['id'], self.current_user_id)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_data()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def open_order_window(self):
        # Der UserOrderWindow benötigt die aktuelle ungefilterte Liste aller Benutzer
        # Wir können hier get_all_users_with_details verwenden, da die Sortierfunktion
        # die Freischaltung nicht interessiert, aber die Sortierliste sollte nur
        # freigeschaltete und sichtbare Benutzer anzeigen.
        all_users = get_all_users_with_details()
        # Wir müssen den MainAdminWindow übergeben, um die refresh_all_tabs Methode aufzurufen
        UserOrderWindow(self.master_window, all_users, self.current_user_id, self.master_window.refresh_all_tabs)

    def sort_treeview(self, tree, col, reverse):
        # Sortierlogik bleibt unverändert
        l = [(tree.set(k, col), k) for k in tree.get_children('')]

        # Spezielle Sortierung für Zahlen (ID, Urlaub etc.)
        if col in ["ID", "Urlaub Gesamt", "Urlaub Rest"]:
            # Versuch, als Integer zu sortieren, falls möglich
            try:
                l.sort(key=lambda x: int(x[0]) if x[0] else float('-inf'), reverse=reverse)
            except ValueError:
                l.sort(key=lambda x: x[0], reverse=reverse)

        # Sortierung nach Rolle (basierend auf der Hierarchie)
        elif col == "Rolle":
            l.sort(key=lambda x: ROLE_HIERARCHY.get(x[0], 0), reverse=reverse)

        # Standardsortierung für Text
        else:
            l.sort(key=lambda x: x[0], reverse=reverse)

        # Neu in Treeview einfügen
        for index, (val, k) in enumerate(l):
            tree.move(k, '', index)

        # Nächste Sortierrichtung festlegen
        tree.heading(col, command=lambda: self.sort_treeview(tree, col, not reverse))