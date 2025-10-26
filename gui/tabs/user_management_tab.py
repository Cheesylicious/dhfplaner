# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog  # simpledialog importiert
from gui.user_edit_window import UserEditWindow
from gui.dialogs.user_order_window import UserOrderWindow
from database.db_users import (get_all_users_with_details, delete_user, save_user_order, get_ordered_users_for_schedule,
                               get_pending_approval_users, approve_user,
                               archive_user, unarchive_user)  # NEUE IMPORTE
from database.db_core import ROLE_HIERARCHY
from datetime import datetime, timedelta # datetime importiert


class UserManagementTab(ttk.Frame):
    def __init__(self, master, current_user_data):
        super().__init__(master)
        # HINWEIS: master ist das Notebook. Wir brauchen den MainAdminWindow
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
        # NEUER BUTTON
        ttk.Button(self.top_frame, text="Archivieren / Reaktivieren", command=self.toggle_archive_status).pack(
            side='left', padx=5)
        ttk.Button(self.top_frame, text="Reihenfolge/Sichtbarkeit", command=self.open_order_window).pack(side='left',
                                                                                                         padx=5)
        ttk.Button(self.top_frame, text="Benutzer löschen", command=self.delete_selected_user).pack(side='left', padx=5)

        # Treeview (Benutzerliste)
        # KORREKTUR: Spalte "Freigeschaltet" in "Status" geändert
        columns = ("ID", "Vorname", "Name", "Rolle", "Geburtstag", "Telefon", "Diensthund", "Urlaub Gesamt",
                   "Urlaub Rest", "Status")
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
        self.tree.column("Status", width=100)  # Geänderte Spalte

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind('<Double-1>', self.open_edit_window)

    # =====================================================================================
    # --- FREISCHALTUNGSLOGIK ---
    # =====================================================================================

    def check_pending_approvals(self):
        """Prüft und zeigt Benachrichtigungen für ausstehende Freischaltungen an."""
        for widget in self.pending_frame.winfo_children():
            widget.destroy()

        # Diese Funktion holt dank DB-Update nur noch (is_approved=0 AND is_archived=0)
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
            self.load_data()  # Hauptliste aktualisieren (Status ändert sich)
            self.check_pending_approvals()  # Pending-Liste aktualisieren
            # Informiere das Hauptfenster, dass eine Aktualisierung der Benachrichtigungen nötig ist
            if hasattr(self.master_window, 'check_for_updates'):
                self.master_window.check_for_updates()
            if hasattr(self.master_window, 'refresh_shift_plan'):
                self.master_window.refresh_shift_plan()  # Wichtig
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
                if hasattr(self.master_window, 'refresh_shift_plan'):
                    self.master_window.refresh_shift_plan()  # Wichtig
            else:
                messagebox.showerror("Fehler", message, parent=self)

    # =====================================================================================
    # --- NEUE METHODE FÜR ARCHIVIERUNG (ÜBERARBEITET) ---
    # =====================================================================================

    def toggle_archive_status(self):
        """Archiviert oder reaktiviert den ausgewählten Benutzer."""
        user = self.get_selected_user()
        if not user:
            messagebox.showinfo("Auswahl erforderlich", "Bitte wählen Sie einen Benutzer aus.", parent=self)
            return

        user_id = user['id']
        user_name = f"{user['vorname']} {user['name']}"
        is_archived = user.get('is_archived', 0)
        is_approved = user.get('is_approved', 0)
        archived_date = user.get('archived_date')  # Hinzugefügt

        if is_approved == 0:
            messagebox.showwarning("Aktion nicht möglich",
                                   f"Der Benutzer '{user_name}' muss zuerst freigeschaltet werden, bevor er archiviert werden kann.",
                                   parent=self)
            return

        # Prüfen, ob eine zukünftige Archivierung vorliegt
        is_future_archive = False
        if is_archived and archived_date and archived_date > datetime.now():
            is_future_archive = True

        success = False
        message = ""

        if is_archived:
            # --- Reaktivieren (gilt für sofort und zukünftig Archivierte) ---
            prompt_msg = f"Möchten Sie den Benutzer '{user_name}' wirklich reaktivieren?\n"
            if is_future_archive:
                prompt_msg += f"Die geplante Archivierung zum {archived_date.strftime('%d.%m.%Y')} wird damit aufgehoben."
            else:
                prompt_msg += "Er/Sie kann sich danach wieder anmelden und wird in zukünftigen Plänen berücksichtigt."

            if not messagebox.askyesno("Benutzer reaktivieren", prompt_msg, parent=self):
                return
            success, message = unarchive_user(user_id, self.current_user_id)

        else:
            # --- Archivieren ---
            msg = f"Möchten Sie den Benutzer '{user_name}' archivieren?\n\n[Ja] = Sofort archivieren\n[Nein] = Zukünftiges Datum festlegen\n[Abbrechen] = Nichts tun"
            response = messagebox.askyesnocancel("Archivieren", msg, parent=self)

            archive_dt = None

            if response is True:  # JA - Sofort
                if messagebox.askyesno("Sofort archivieren",
                                       f"Sind Sie sicher, dass Sie '{user_name}' sofort archivieren möchten?",
                                       parent=self):
                    archive_dt = datetime.now()
                    success, message = archive_user(user_id, self.current_user_id, archive_dt)

            elif response is False:  # NEIN - Zukünftiges Datum
                today_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                date_str = simpledialog.askstring("Zukünftiges Datum",
                                                  f"Geben Sie das Datum ein, an dem '{user_name}' archiviert werden soll.\nDer Benutzer ist bis zu diesem Datum (exklusive) aktiv.\n(Format: YYYY-MM-DD, z.B. {today_str})",
                                                  parent=self)
                if date_str:
                    try:
                        # Wir setzen die Uhrzeit auf Mitternacht (Anfang des Tages)
                        archive_dt = datetime.strptime(date_str, '%Y-%m-%d')
                        # Prüfen, ob das Datum heute oder in der Vergangenheit liegt
                        if archive_dt < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0):
                            messagebox.showerror("Fehler", "Das Datum darf nicht in der Vergangenheit liegen.",
                                                 parent=self)
                        else:
                            success, message = archive_user(user_id, self.current_user_id, archive_dt)
                    except ValueError:
                        messagebox.showerror("Ungültiges Format", "Das Datum muss im Format YYYY-MM-DD sein.",
                                             parent=self)

            else:  # Cancel (response is None)
                return

        # --- Ergebnisverarbeitung ---
        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.load_data()  # Liste neu laden, um Status anzuzeigen
            # Schichtplan und andere Tabs müssen aktualisiert werden
            if hasattr(self.master_window, 'refresh_all_tabs'):
                self.master_window.refresh_all_tabs()
        elif message:  # Nur Fehler anzeigen, wenn 'message' gesetzt, aber 'success' false ist
            messagebox.showerror("Fehler", message, parent=self)

    # =====================================================================================
    # --- BESTEHENDE METHODEN (ANGEPASST) ---
    # =====================================================================================

    def load_data(self):
        """Lädt alle Benutzerdaten und befüllt das Treeview."""
        # Lösche vorhandene Einträge
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Holt alle User, inkl. archivierter (SELECT * from users)
        self.user_data = get_all_users_with_details()

        for user in self.user_data:
            # NEUE STATUSLOGIK
            is_approved = user.get('is_approved', 0)
            is_archived = user.get('is_archived', 0)
            archived_date = user.get('archived_date')  # Hinzugefügt

            status_text = ""
            tag = ""

            if is_approved == 0:
                status_text = "Ausstehend ⚠️"
                tag = 'pending'
            elif is_archived == 1:
                if archived_date and archived_date > datetime.now():
                    status_text = f"Archiviert ab {archived_date.strftime('%d.%m.%Y')} 🗓️"
                    tag = 'future_archive'
                else:
                    status_text = "Archiviert 📦"
                    tag = 'archived'
            else:
                status_text = "Aktiv ✅"
                tag = 'approved'
            # ENDE NEUE LOGIK

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
                status_text  # Status statt 'is_approved'
            ))

        # Konfiguriere Tags für Farben
        self.tree.tag_configure('pending', background='#ffe0e0', foreground='red')  # Rot für ausstehende Freischaltung
        self.tree.tag_configure('approved', background='white', foreground='black')  # Normal (Aktiv)
        self.tree.tag_configure('archived', background='#f0f0f0', foreground='#555555')  # Grau für Archiviert
        self.tree.tag_configure('future_archive', background='#fffbe0',
                                foreground='#a18c00')  # Gelb für zukünftige Archivierung

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
            # (Unverändert, Aufruf ist korrekt seit letztem Fix)
            allowed_roles = []
            if hasattr(self.master_window, 'get_allowed_roles'):
                allowed_roles = self.master_window.get_allowed_roles()
            else:
                print("[WARN] UserManagementTab: MainAdminWindow 'get_allowed_roles' not found.")
                allowed_roles = list(ROLE_HIERARCHY.keys())

            UserEditWindow(
                self.master_window,
                user['id'],
                user,
                self.load_data,
                False,
                allowed_roles,
                self.current_user_id
            )
        elif event is None:
            messagebox.showinfo("Auswahl erforderlich", "Bitte wählen Sie einen Benutzer zum Bearbeiten aus.")

    def delete_selected_user(self):
        user = self.get_selected_user()
        if not user:
            messagebox.showinfo("Auswahl erforderlich", "Bitte wählen Sie einen Benutzer zum Löschen aus.")
            return

        user_name = f"{user['vorname']} {user['name']}"

        # Zusatzwarnung, wenn Benutzer nicht archiviert ist
        is_archived = user.get('is_archived', 0)
        archived_date = user.get('archived_date')

        warning = ""
        is_active = True
        if is_archived == 1:
            if not archived_date or archived_date <= datetime.now():
                is_active = False  # Bereits archiviert

        if is_active:
            warning = "\n\nWARNUNG: Dieser Benutzer ist noch aktiv.\nBevorzugen Sie die 'Archivieren'-Funktion, wenn der Benutzer nur deaktiviert werden soll."

        if messagebox.askyesno("Löschen bestätigen",
                               f"Sind Sie sicher, dass Sie den Benutzer '{user_name}' DAUERHAFT löschen möchten?\nAlle seine Daten (auch alte Schichten) werden unwiderruflich entfernt.{warning}",
                               parent=self):
            success, message = delete_user(user['id'], self.current_user_id)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_data()
                if hasattr(self.master_window, 'refresh_all_tabs'):
                    self.master_window.refresh_all_tabs()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def open_order_window(self):
        # HINWEIS: Diese Funktion ist unverändert.
        # UserOrderWindow ruft get_ordered_users_for_schedule(include_hidden=True) auf.
        # Da diese DB-Funktion jetzt (is_archived = 0 ODER zukünftiges Datum) filtert,
        # werden archivierte Benutzer hier korrekterweise nicht mehr angezeigt,
        # aber zukünftig zu archivierende Benutzer schon.
        UserOrderWindow(self.master_window, callback=self.master_window.refresh_all_tabs)

    def sort_treeview(self, tree, col, reverse):
        # Sortierlogik bleibt unverändert
        l = [(tree.set(k, col), k) for k in tree.get_children('')]

        # Spezielle Sortierung für Zahlen (ID, Urlaub etc.)
        if col in ["ID", "Urlaub Gesamt", "Urlaub Rest"]:
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