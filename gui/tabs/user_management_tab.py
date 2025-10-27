# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog # simpledialog hinzugefügt
# datetime und date importieren
from datetime import datetime, date, timedelta # timedelta hinzugefügt
from database.db_users import (
    get_all_users_with_details, delete_user, approve_user,
    get_pending_approval_users, archive_user, unarchive_user,
    clear_user_order_cache
)
from database.db_admin import admin_reset_password # create_user_by_admin wird nicht direkt hier gebraucht
from database.db_core import save_config_json, load_config_json
from ..user_edit_window import UserEditWindow

USER_MGMT_VISIBLE_COLUMNS_KEY = "USER_MGMT_VISIBLE_COLUMNS"

class UserManagementTab(ttk.Frame):
    def __init__(self, master, admin_window):
        super().__init__(master)
        self.admin_window = admin_window
        self.current_user = admin_window.user_data

        self.all_columns = {
            "id": ("ID", 0),
            "vorname": ("Vorname", 150),
            "name": ("Nachname", 150),
            "role": ("Rolle", 100),
            "geburtstag": ("Geburtstag", 100),
            "telefon": ("Telefon", 120),
            "diensthund": ("Diensthund", 100),
            "urlaub_gesamt": ("Urlaub Total", 80),
            "urlaub_rest": ("Urlaub Rest", 80),
            "entry_date": ("Eintritt", 100),
            "last_ausbildung": ("Letzte Ausb.", 100),
            "last_schiessen": ("Letztes Sch.", 100),
            "last_seen": ("Zuletzt Online", 120),
            "is_approved": ("Freigegeben?", 80),
            "is_archived": ("Archiviert?", 80),
            "archived_date": ("Archiviert am", 120)
        }
        loaded_visible_keys = load_config_json(USER_MGMT_VISIBLE_COLUMNS_KEY)
        if loaded_visible_keys and isinstance(loaded_visible_keys, list):
             self.visible_column_keys = [key for key in loaded_visible_keys if key in self.all_columns]
        else:
            self.visible_column_keys = [k for k in self.all_columns if k not in ['id', 'is_approved', 'is_archived', 'archived_date', 'last_seen']]

        if 'id' not in self.visible_column_keys:
            self.visible_column_keys.insert(0, 'id')

        self._sort_by = 'name'
        self._sort_desc = False

        self._create_widgets()
        self.load_users()

    def _create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", pady=10, padx=10)

        ttk.Button(top_frame, text="🔄 Aktualisieren", command=self.load_users).pack(side="left", padx=5)
        ttk.Button(top_frame, text="➕ Mitarbeiter hinzufügen", command=self.add_user).pack(side="left", padx=5)
        ttk.Button(top_frame, text="📊 Spalten auswählen", command=self.open_column_chooser).pack(side="left", padx=5)
        # --- KORREKTUR: Button-Text angepasst ---
        ttk.Button(top_frame, text="🕒 Freischaltungen prüfen", command=self.check_pending_approvals).pack(side="right", padx=5)
        # --- ENDE KORREKTUR ---

        tree_frame = ttk.Frame(self)
        tree_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        all_col_keys = list(self.all_columns.keys())
        self.tree = ttk.Treeview(tree_frame, columns=all_col_keys, show="headings")

        display_keys = [key for key in self.visible_column_keys if key != 'id' or self.all_columns['id'][1] > 0]
        self.tree.configure(displaycolumns=display_keys)

        for col_key in all_col_keys:
            col_name, col_width = self.all_columns[col_key]
            is_displayed = col_key in display_keys
            width = col_width if is_displayed else 0
            minwidth = 30 if is_displayed and col_key != "id" else 0
            stretch = tk.YES if is_displayed and col_key != "id" else tk.NO
            heading_options = {'text': col_name}
            if is_displayed: heading_options['command'] = lambda _col=col_key: self.sort_column(_col)
            self.tree.heading(col_key, **heading_options)
            self.tree.column(col_key, width=width, minwidth=minwidth, stretch=stretch, anchor=tk.W)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        hsb.pack(side='bottom', fill='x')
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(expand=True, fill="both")
        self.tree.bind("<Double-1>", self.edit_user_dialog)
        self.tree.bind("<Button-3>", self.show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="✏️ Bearbeiten", command=self.edit_user_context)
        self.context_menu.add_command(label="🔑 Passwort zurücksetzen", command=self.reset_password_context)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✅ Freischalten", command=self.approve_user_context)
        self.context_menu.add_command(label="🔒 Archivieren...", command=self.archive_user_context) # Text angepasst
        self.context_menu.add_command(label="🔓 Reaktivieren", command=self.unarchive_user_context)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="❌ Löschen", command=self.delete_user_context)

        self.selected_user_id = None
        self.selected_user_data = None


    def load_users(self):
        for i in self.tree.get_children():
            try: self.tree.delete(i)
            except tk.TclError: pass

        try:
            self.all_users_data = get_all_users_with_details()
            if not self.all_users_data: return

            def sort_key(user_item):
                value = user_item.get(self._sort_by)
                if value is None or value == "":
                    is_date_col = self._sort_by in ['entry_date', 'last_ausbildung', 'last_schiessen', 'archived_date', 'geburtstag', 'last_seen']
                    if self._sort_desc: return date.min if is_date_col else ""
                    else: return date.max if is_date_col else "~~~~"
                if isinstance(value, str): return value.lower()
                if self._sort_by in ['entry_date', 'last_ausbildung', 'last_schiessen', 'archived_date', 'geburtstag']:
                     try:
                         if isinstance(value, datetime): return value.date()
                         if isinstance(value, date): return value
                         return datetime.strptime(str(value), '%Y-%m-%d').date()
                     except: return date.min
                if self._sort_by == 'last_seen':
                     try:
                         if isinstance(value, datetime): return value
                         if isinstance(value, date): return datetime.combine(value, datetime.min.time())
                         return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
                     except: return datetime.min
                try:
                    if isinstance(value, (int, float)): return value
                    return float(value)
                except: return float('-inf')

            sorted_users = sorted(self.all_users_data, key=sort_key, reverse=self._sort_desc)
            current_tree_columns = list(self.tree['columns'])
            if not current_tree_columns: current_tree_columns = list(self.all_columns.keys())

            for user in sorted_users:
                values_to_insert = []
                for col_key in current_tree_columns:
                    value = user.get(col_key, "")
                    if value is None: value = ""
                    if col_key in ["is_approved", "is_archived"]: value = "Ja" if value == 1 else "Nein"
                    elif col_key in ['entry_date', 'last_ausbildung', 'last_schiessen', 'geburtstag']:
                         if isinstance(value, datetime): value = value.strftime('%Y-%m-%d')
                         elif isinstance(value, date): value = value.strftime('%Y-%m-%d')
                    elif col_key == 'last_seen':
                         if isinstance(value, datetime): value = value.strftime('%Y-%m-%d %H:%M')
                    elif col_key == 'archived_date':
                         # --- KORREKTUR: Auch hier nur Datum anzeigen, wenn Datum gesetzt ---
                         if isinstance(value, datetime): value = value.strftime('%Y-%m-%d') # Nur Datum
                         elif isinstance(value, date): value = value.strftime('%Y-%m-%d')
                         else: value = "" # Ansonsten leer
                         # --- ENDE KORREKTUR ---
                    values_to_insert.append(value)
                try: self.tree.insert("", "end", iid=user['id'], values=tuple(values_to_insert))
                except tk.TclError as e: print(f"TclError User {user['id']}: {e}. Skip.")

        except Exception as e:
            messagebox.showerror("Fehler Laden", f"Benutzerdaten laden fehlgeschlagen:\n{e}", parent=self)
            import traceback; traceback.print_exc()

    def sort_column(self, col):
        if col not in self.all_columns: return
        if self._sort_by == col: self._sort_desc = not self._sort_desc
        else: self._sort_by = col; self._sort_desc = False
        for c_key, (c_name, _) in self.all_columns.items():
            try: self.tree.heading(c_key, text=c_name)
            except tk.TclError: pass
        current_display_columns = self.tree['displaycolumns']
        if not current_display_columns: current_display_columns = [key for key in self.visible_column_keys if key != 'id' or self.all_columns['id'][1] > 0]
        if col in current_display_columns:
            try:
                header_text = self.all_columns[col][0]
                sort_indicator = " ▼" if self._sort_desc else " ▲"
                self.tree.heading(col, text=header_text + sort_indicator)
            except tk.TclError: pass
        self.load_users()

    def open_column_chooser(self):
        visible_for_chooser = [key for key in self.visible_column_keys if key != 'id' or self.all_columns['id'][1] > 0]
        ColumnChooser(self, self.all_columns, visible_for_chooser, self.update_visible_columns)

    def update_visible_columns(self, new_visible_keys_from_chooser):
        print(f"[DEBUG] update_visible_columns: Empfangen: {new_visible_keys_from_chooser}")
        new_visible_keys = list(new_visible_keys_from_chooser)
        if 'id' not in new_visible_keys: new_visible_keys.insert(0, 'id')
        self.visible_column_keys = new_visible_keys
        if not save_config_json(USER_MGMT_VISIBLE_COLUMNS_KEY, self.visible_column_keys):
             messagebox.showwarning("Speichern fehlgeschlagen", "Spaltenauswahl nicht gespeichert.", parent=self)
        display_keys = [key for key in self.visible_column_keys if key != 'id' or self.all_columns['id'][1] > 0]
        try: self.tree.configure(displaycolumns=display_keys)
        except tk.TclError as e:
             print(f"Fehler displaycolumns: {e}")
             valid_display_keys = [k for k in display_keys if k in self.tree['columns']]
             try: self.tree.configure(displaycolumns=valid_display_keys)
             except tk.TclError: print("Setzen displaycolumns erneut fehlgeschlagen.")
        for col_key in self.all_columns:
            col_name, col_width = self.all_columns[col_key]
            is_displayed = col_key in display_keys
            width = col_width if is_displayed else 0
            minwidth = 30 if is_displayed and col_key != "id" else 0
            stretch = tk.YES if is_displayed and col_key != "id" else tk.NO
            heading_options = {'text': col_name}
            if is_displayed: heading_options['command'] = lambda _col=col_key: self.sort_column(_col)
            if col_key == self._sort_by and is_displayed:
                 sort_indicator = " ▼" if self._sort_desc else " ▲"
                 heading_options['text'] += sort_indicator
            try:
                self.tree.heading(col_key, **heading_options)
                self.tree.column(col_key, width=width, minwidth=minwidth, stretch=stretch, anchor=tk.W)
            except tk.TclError: pass
        self.load_users()

    def add_user(self):
        edit_win = UserEditWindow(master=self, user_id=None, user_data=None, is_new=True,
                                  allowed_roles=self.admin_window.get_allowed_roles(),
                                  admin_user_id=self.current_user['id'], callback=self.on_user_saved)
        edit_win.grab_set()

    def edit_user_dialog(self, event=None):
        selected_item = self.tree.focus()
        if not selected_item: return
        try: user_id = int(selected_item)
        except ValueError: return
        user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
        if user_data:
            edit_win = UserEditWindow(master=self, user_id=user_id, user_data=user_data, is_new=False,
                                      allowed_roles=self.admin_window.get_allowed_roles(),
                                      admin_user_id=self.current_user['id'], callback=self.on_user_saved)
            edit_win.grab_set()
        else:
             print(f"Warnung: User {user_id} nicht im Cache bei Doppelklick.")
             self.load_users()
             user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
             if user_data:
                  edit_win = UserEditWindow(master=self, user_id=user_id, user_data=user_data, is_new=False,
                                            allowed_roles=self.admin_window.get_allowed_roles(),
                                            admin_user_id=self.current_user['id'], callback=self.on_user_saved)
                  edit_win.grab_set()
             else: messagebox.showerror("Fehler", f"User {user_id} nicht geladen.", parent=self)

    def on_user_saved(self):
        clear_user_order_cache(); self.load_users()

    def show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid); self.tree.focus(iid)
            try: self.selected_user_id = int(iid)
            except ValueError: return
            self.selected_user_data = next((user for user in self.all_users_data if user['id'] == self.selected_user_id), None)
            if self.selected_user_data:
                is_approved = self.selected_user_data.get('is_approved', 0) == 1
                is_archived = self.selected_user_data.get('is_archived', 0) == 1
                states = { "Freischalten": tk.DISABLED if is_approved else tk.NORMAL,
                           "Archivieren...": tk.DISABLED if is_archived else tk.NORMAL, # Text angepasst
                           "Reaktivieren": tk.DISABLED if not is_archived else tk.NORMAL,
                           "Bearbeiten": tk.NORMAL, "Passwort zurücksetzen": tk.NORMAL, "Löschen": tk.NORMAL }
                for label, state in states.items():
                     try: self.context_menu.entryconfigure(label, state=state)
                     except tk.TclError: pass
                self.context_menu.tk_popup(event.x_root, event.y_root)
            else: self.selected_user_id = None; self.selected_user_data = None
        else:
            self.selected_user_id = None; self.selected_user_data = None
            try: self.tree.selection_remove(self.tree.selection())
            except tk.TclError: pass

    def _get_selected_user_id_and_data(self):
         selected_item = self.tree.focus()
         if not selected_item: messagebox.showwarning("Auswahl", "Bitte Mitarbeiter wählen.", parent=self); return None, None
         try:
             user_id = int(selected_item)
             user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
             if not user_data: messagebox.showerror("Fehler", "User nicht gefunden.", parent=self); return None, None
             return user_id, user_data
         except ValueError: return None, None

    def edit_user_context(self):
         user_id, user_data = self._get_selected_user_id_and_data()
         if user_id and user_data:
             edit_win = UserEditWindow(master=self, user_id=user_id, user_data=user_data, is_new=False,
                                       allowed_roles=self.admin_window.get_allowed_roles(),
                                       admin_user_id=self.current_user['id'], callback=self.on_user_saved)
             edit_win.grab_set()

    def reset_password_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            name = f"{user_data.get('vorname','')} {user_data.get('name','')}".strip()
            if messagebox.askyesno("Reset", f"Passwort für '{name}' resetten?", parent=self):
                pw = "NeuesPasswort123"
                ok, msg = admin_reset_password(user_id, pw)
                if ok: messagebox.showinfo("OK", f"{msg}\nTemp. PW: {pw}", parent=self)
                else: messagebox.showerror("Fehler", msg, parent=self)

    def approve_user_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            if user_data.get('is_approved') == 1: return
            name = f"{user_data.get('vorname','')} {user_data.get('name','')}".strip()
            if messagebox.askyesno("Freigabe", f"'{name}' freischalten?", parent=self):
                ok, msg = approve_user(user_id, self.current_user['id'])
                if ok: messagebox.showinfo("OK", msg, parent=self); self.load_users(); self.admin_window.check_for_updates()
                else: messagebox.showerror("Fehler", msg, parent=self)

    # --- KORRIGIERTE FUNKTION ---
    def archive_user_context(self):
        """Archiviert einen Benutzer sofort oder zu einem gewählten Datum."""
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            if user_data.get('is_archived') == 1:
                messagebox.showinfo("Bereits archiviert", "Dieser Benutzer ist bereits archiviert.", parent=self)
                return

            user_fullname = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            archive_date = None # Standard: Sofort

            # Frage, ob sofort oder später
            choice = messagebox.askyesnocancel("Archivieren", f"Möchten Sie '{user_fullname}' **sofort** archivieren?\n\n(Klicken Sie auf 'Nein', um ein Datum auszuwählen)", parent=self)

            if choice is None: # Abbrechen
                return
            elif choice is False: # Nein -> Datum wählen
                # Verwende simpledialog, um das Datum abzufragen
                today_str = date.today().strftime('%Y-%m-%d')
                prompt = f"Geben Sie das Datum (JJJJ-MM-TT) ein, ab dem '{user_fullname}' archiviert sein soll:\n(Muss in der Zukunft liegen)"
                date_str = simpledialog.askstring("Archivierungsdatum", prompt, initialvalue=today_str, parent=self)

                if not date_str: # Leere Eingabe oder Abbrechen im Dialog
                    return

                try:
                    # Versuche, das Datum zu parsen und zu validieren
                    chosen_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if chosen_date <= date.today():
                         messagebox.showwarning("Ungültiges Datum", "Das Archivierungsdatum muss in der Zukunft liegen.", parent=self)
                         return
                    # Setze die Uhrzeit auf 00:00:00 für den Vergleich in der DB
                    archive_date = datetime.combine(chosen_date, datetime.min.time())
                    print(f"[DEBUG] Gewähltes Archivierungsdatum: {archive_date}")
                except ValueError:
                    messagebox.showerror("Ungültiges Format", "Bitte geben Sie das Datum im Format JJJJ-MM-TT ein.", parent=self)
                    return

            # Führe die Archivierung durch (entweder mit None für sofort oder mit dem gewählten Datum)
            success, message = archive_user(user_id, self.current_user['id'], archive_date=archive_date)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                clear_user_order_cache()
                self.load_users() # Lade neu, um das Datum anzuzeigen (wenn Spalte sichtbar)
                self.admin_window.check_for_updates()
            else:
                messagebox.showerror("Fehler", message, parent=self)
    # --- ENDE KORRIGIERTE FUNKTION ---

    def unarchive_user_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            if user_data.get('is_archived') == 0: return
            name = f"{user_data.get('vorname','')} {user_data.get('name','')}".strip()
            if messagebox.askyesno("Reaktivieren", f"'{name}' reaktivieren?", parent=self):
                ok, msg = unarchive_user(user_id, self.current_user['id'])
                if ok: messagebox.showinfo("OK", msg, parent=self); clear_user_order_cache(); self.load_users(); self.admin_window.check_for_updates()
                else: messagebox.showerror("Fehler", msg, parent=self)

    def delete_user_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
             name = f"{user_data.get('vorname','')} {user_data.get('name','')}".strip()
             if messagebox.askyesno("Löschen", f"'{name}' wirklich löschen?", icon='warning', parent=self):
                 ok, msg = delete_user(user_id, self.current_user['id'])
                 if ok: messagebox.showinfo("OK", msg, parent=self); clear_user_order_cache(); self.load_users(); self.admin_window.check_for_updates()
                 else: messagebox.showerror("Fehler", msg, parent=self)

    # --- KORRIGIERTE FUNKTION ---
    def check_pending_approvals(self):
        """Prüft auf Freischaltungen und zeigt Meldung NUR wenn welche anstehen."""
        try:
            pending_users = get_pending_approval_users()
            if pending_users: # Nur wenn Liste nicht leer ist
                user_list = "\n".join([f"- {user['vorname']} {user['name']}" for user in pending_users])
                messagebox.showinfo("Ausstehende Freischaltungen",
                                    f"Die folgenden Benutzer warten auf Freischaltung:\n{user_list}",
                                    parent=self)
            # else: Keine Meldung ausgeben, wenn nichts ansteht
        except Exception as e:
             messagebox.showerror("Fehler", f"Fehler beim Prüfen der Freischaltungen:\n{e}", parent=self)
    # --- ENDE KORRIGIERTE FUNKTION ---

    def refresh_data(self):
        self.load_users()

# --- Klasse ColumnChooser (unverändert) ---
class ColumnChooser(tk.Toplevel):
    def __init__(self, master, all_columns, visible_keys, callback):
        super().__init__(master)
        self.title("Spalten auswählen")
        self.all_columns = all_columns
        self.visible_keys_for_display = [k for k in visible_keys if k != 'id' or self.all_columns['id'][1] > 0]
        self.callback = callback
        self.vars = {}
        self.resizable(False, False)
        self.geometry(f"+{master.winfo_rootx()+50}+{master.winfo_rooty()+50}")
        main_frame = ttk.Frame(self, padding="10"); main_frame.pack(expand=True, fill="both")
        ttk.Label(main_frame, text="Wählen Sie die anzuzeigenden Spalten aus:").pack(pady=(0, 10))
        checkbox_frame = ttk.Frame(main_frame); checkbox_frame.pack(expand=True, fill="x")
        sorted_column_items = sorted(self.all_columns.items(), key=lambda item: item[1][0])
        for key, (name, width) in sorted_column_items:
            if key == "id" and width <= 0 : continue
            is_visible = key in self.visible_keys_for_display
            var = tk.BooleanVar(value=is_visible)
            ttk.Checkbutton(checkbox_frame, text=name, variable=var).pack(anchor="w", padx=5)
            self.vars[key] = var
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(button_frame, text="OK", command=self.apply_changes, style="Accent.TButton").pack(side="right", padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right")
        self.grab_set(); self.focus_set(); self.wait_window()

    def apply_changes(self):
        new_visible = []
        for key in self.all_columns:
            if key == 'id':
                if key in self.vars and self.vars[key].get() and self.all_columns['id'][1] > 0:
                    new_visible.append(key)
                continue
            if key in self.vars and self.vars[key].get():
                new_visible.append(key)
        self.callback(new_visible); self.destroy()