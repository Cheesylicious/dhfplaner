# gui/tabs/user_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog  # simpledialog hinzugefügt
# datetime und date importieren
from datetime import datetime, date, timedelta  # timedelta hinzugefügt
from database.db_users import (
    get_all_users_with_details, delete_user, approve_user,
    get_pending_approval_users, archive_user, unarchive_user,
    clear_user_order_cache
)
from database.db_admin import admin_reset_password  # create_user_by_admin wird nicht direkt hier gebraucht
from database.db_core import save_config_json, load_config_json
from ..user_edit_window import UserEditWindow

# --- NEUE IMPORTE FÜR ROLLENVERWALTUNG ---
from ..dialogs.role_management_dialog import RoleManagementDialog
# --- INNOVATION (Regel 2 & 4): Lade Rollen-Definitionen ---
from database.db_roles import get_all_roles_details

# -------------------------------------------

USER_MGMT_VISIBLE_COLUMNS_KEY = "USER_MGMT_VISIBLE_COLUMNS"


class UserManagementTab(ttk.Frame):
    def __init__(self, master, admin_window, initial_data_cache=None):
        """
        Konstruktor für den UserManagementTab.
        Akzeptiert optional vorgeladene Daten, um DB-Wartezeiten zu vermeiden (Regel 2).
        """
        super().__init__(master)
        self.admin_window = admin_window
        # --- KORREKTUR (Fehlerbehebung): Speichert die ID des Admins, der den Tab bedient ---
        self.current_user = admin_window.user_data
        # --- ENDE KORREKTUR ---

        # Speichert die Rohdaten (entweder aus Cache or DB)
        self.all_users_data = []

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
            "archived_date": ("Archiviert am", 120),
            # --- NEUES FELD FÜR BEARBEITUNG ---
            "activation_date": ("Aktiv ab Datum", 120)
            # --- ENDE NEUES FELD ---
        }

        # Sicherstellen, dass alle Spalten, die in self.all_columns definiert wurden,
        # im ColumnChooser berücksichtigt werden können.

        loaded_visible_keys = load_config_json(USER_MGMT_VISIBLE_COLUMNS_KEY)
        if loaded_visible_keys and isinstance(loaded_visible_keys, list):
            # Filtere nur gültige Schlüssel
            self.visible_column_keys = [key for key in loaded_visible_keys if key in self.all_columns]
        else:
            self.visible_column_keys = [k for k in self.all_columns if
                                        k not in ['id', 'is_approved', 'is_archived', 'archived_date', 'last_seen',
                                                  'activation_date']]

        if 'id' not in self.visible_column_keys:
            self.visible_column_keys.insert(0, 'id')

        self._sort_by = 'name'
        self._sort_desc = False

        # --- INNOVATION (Regel 2 & 4): Dynamische Rollenfarben ---
        # (Palette entfernt, wird jetzt in DB gespeichert)
        # Speichert die Zuordnung von Rollenname (klein) zu Tag-Name
        self.role_color_map = {}
        # --- ENDE INNOVATION ---

        self._create_widgets()

        # --- INNOVATION: Lade und konfiguriere Rollenfarben ---
        self._load_and_configure_role_colors()
        # --- ENDE INNOVATION ---

        # --- INNOVATION (Regel 1 & 2) ---
        # Daten entweder aus dem Cache laden oder (als Fallback) aus der DB holen.
        if initial_data_cache is not None and initial_data_cache:
            # NEU: Überprüfen, ob der Cache vollständig ist (z.B. mehr Spalten als nur die Basis)
            # Wenn der Cache nur die Basisdaten enthält (z.B. von get_all_users()),
            # wird er trotzdem verwendet, aber der Bearbeiten-Dialog wird unvollständig.
            print(f"[UserMgmtTab] Lade Daten aus initialem Cache ({len(initial_data_cache)} Einträge).")
            self.all_users_data = initial_data_cache
            self._load_users_from_cache()  # Daten sortieren und anzeigen
        else:
            print("[UserMgmtTab] Initialer Cache leer/fehlerhaft. Lade aus DB (Fallback).")
            self.refresh_data()  # Daten aus DB holen und anzeigen
        # --- ENDE INNOVATION ---

    # --- NEUE METHODE (Regel 1 & 4) ---
    def update_data_cache(self, new_data_cache):
        """
        Methode für AdminTabManager/Preloader, um den vollständigen
        Datensatz synchron zu injizieren, NACHDEM er aus der DB geladen wurde.
        """
        if new_data_cache is not None:
            print(f"[UserMgmtTab] Aktualisiere internen Cache mit {len(new_data_cache)} Einträgen.")
            self.all_users_data = new_data_cache
            self._load_users_from_cache()

    # --- NEUE INNOVATION FÜR AKTUALISIERUNG BEIM FOKUS (Regel 1 & 2) ---
    def on_tab_focus(self):
        """
        Wird vom AdminTabManager aufgerufen, wenn dieser Tab aktiviert wird.
        Erzwingt eine Aktualisierung der Daten, um sicherzustellen, dass die
        Anzeige aktuell ist (Regel 2: Vermeidet Wartezeiten und manuelle Aktionen).
        """
        print("[UserMgmtTab] on_tab_focus aufgerufen. Aktualisiere Daten.")
        # Ruft refresh_data auf, welches entweder aus Cache oder DB lädt.
        self.refresh_data()

    # --- ENDE NEUE INNOVATION ---

    # --- INNOVATION (Regel 2 & 4): Rollenfarben dynamisch laden ---
    def _load_and_configure_role_colors(self):
        """
        Lädt alle Rollen aus der DB, liest die gespeicherte FARBE
        und konfiguriert die Treeview-Tags.
        """
        print("[UserMgmtTab] Lade und konfiguriere Rollenfarben...")
        try:
            # (Diese Funktion ruft jetzt die Farbe aus der DB ab)
            roles = get_all_roles_details()
            self.role_color_map.clear()

            for index, role in enumerate(roles):
                # Verwende 'name' (wie von get_all_roles_details zurückgegeben)
                role_name_key = str(role.get('name', '')).lower()
                if not role_name_key:
                    continue

                # --- INNOVATION (Regel 2): Lese Farbe aus DB ---
                color = role.get('color', '#FFFFFF')  # Fallback Weiß
                # --- ENDE INNOVATION ---

                # Tag-Name basierend auf Rollen-ID (eindeutig)
                tag_name = f"role_tag_{role.get('id', index)}"

                try:
                    # Konfiguriere Tag in der Treeview (Hintergrundfarbe)
                    self.tree.tag_configure(tag_name, background=color)

                    # Speichere die Zuordnung (Rollenname -> Tag)
                    self.role_color_map[role_name_key] = tag_name

                except tk.TclError:
                    print(f"Warnung: Konnte Tag {tag_name} nicht konfigurieren.")

        except Exception as e:
            print(f"Fehler beim Laden der Rollenfarben: {e}")
            # Fallback: leere Map
            self.role_color_map = {}

    # --- ENDE INNOVATION ---

    def _create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", pady=10, padx=10)

        # --- KORREKTUR: Ruft refresh_data() statt load_users() auf ---
        ttk.Button(top_frame, text="🔄 Aktualisieren", command=self.refresh_data).pack(side="left", padx=5)
        # --- ENDE KORREKTUR ---

        ttk.Button(top_frame, text="➕ Mitarbeiter hinzufügen", command=self.add_user).pack(side="left", padx=5)
        ttk.Button(top_frame, text="📊 Spalten auswählen", command=self.open_column_chooser).pack(side="left", padx=5)

        # --- NEUER BUTTON FÜR ROLLENVERWALTUNG (Regel 4) ---
        ttk.Button(top_frame, text="Rollen verwalten", command=self.open_role_management).pack(side="left", padx=5)
        # --------------------------------------------------

        # --- KORREKTUR: Button-Text angepasst ---
        ttk.Button(top_frame, text="🕒 Freischaltungen prüfen", command=self.check_pending_approvals).pack(side="right",
                                                                                                          padx=5)
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
            # HINWEIS: Sortierung (Request 1) wird hier bereits für alle Spalten aktiviert
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
        self.context_menu.add_command(label="🔒 Archivieren...", command=self.archive_user_context)  # Text angepasst
        self.context_menu.add_command(label="🔓 Reaktivieren", command=self.unarchive_user_context)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="❌ Löschen", command=self.delete_user_context)

        self.selected_user_id = None
        self.selected_user_data = None

        # --- NEU: Tags für farbliche Hervorhebung ---
        # (Farben können hier angepasst werden)
        self.tree.tag_configure('archived', foreground='#808080')  # Grau für Archivierte
        self.tree.tag_configure('pending', foreground='#E67E22')  # Orange für Nicht-Freigegebene
        # (Rollenfarben werden jetzt in _load_and_configure_role_colors() konfiguriert)
        # --- ENDE NEU ---

    def _load_users_from_cache(self):
        """
        (NEUE METHODE) Füllt die Treeview mit den Daten aus self.all_users_data.
        Diese Methode greift nicht auf die Datenbank zu. (Regel 2)
        """
        for i in self.tree.get_children():
            try:
                self.tree.delete(i)
            except tk.TclError:
                pass

        if not self.all_users_data:
            return

        # --- START FEHLERBEHEBUNG (TypeError bei Sortierung) ---
        # (Regel 1 & 2: Innovativere Sortierfunktion, die Typenkonflikte vermeidet)
        def sort_key(user_item):
            value = user_item.get(self._sort_by)

            # Definiere Spaltentypen
            date_cols = ['entry_date', 'last_ausbildung', 'last_schiessen', 'archived_date', 'geburtstag',
                         'activation_date']
            datetime_cols = ['last_seen']
            numeric_cols = ['id', 'urlaub_gesamt', 'urlaub_rest', 'is_approved', 'is_archived']

            # 1. Handle Datums-Spalten
            if self._sort_by in date_cols:
                if value is None or value == "":
                    # Sende leere Werte ans Ende (aufsteigend) oder Anfang (absteigend)
                    return date.max if not self._sort_desc else date.min
                try:
                    if isinstance(value, datetime): return value.date()
                    if isinstance(value, date): return value
                    # Handle DB-String-Format (YYYY-MM-DD)
                    return datetime.strptime(str(value).split(' ')[0], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return date.max if not self._sort_desc else date.min

            # 2. Handle DateTime-Spalten
            elif self._sort_by in datetime_cols:
                if value is None or value == "":
                    return datetime.max if not self._sort_desc else datetime.min
                try:
                    if isinstance(value, datetime): return value
                    if isinstance(value, date): return datetime.combine(value, datetime.min.time())
                    # Handle DB-String-Format (YYYY-MM-DD HH:MM:SS)
                    return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    return datetime.max if not self._sort_desc else datetime.min

            # 3. Handle Numerische-Spalten
            elif self._sort_by in numeric_cols:
                if value is None or value == "":
                    # Sende leere Werte ans Ende (aufsteigend) oder Anfang (absteigend)
                    return float('inf') if not self._sort_desc else float('-inf')
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return float('inf') if not self._sort_desc else float('-inf')

            # 4. Handle String-Spalten (Default)
            else:
                if value is None:
                    value = ""
                try:
                    # Leere Strings ans Ende (aufsteigend) oder Anfang (absteigend) schieben
                    val_str = str(value).lower()
                    if val_str == "":
                        return "~~~~~" if not self._sort_desc else ""
                    return val_str
                except:
                    return "~~~~~" if not self._sort_desc else ""

        # --- ENDE FEHLERBEHEBUNG ---

        sorted_users = sorted(self.all_users_data, key=sort_key, reverse=self._sort_desc)

        current_tree_columns = list(self.tree['columns'])
        if not current_tree_columns: current_tree_columns = list(self.all_columns.keys())

        for user in sorted_users:
            values_to_insert = []
            for col_key in current_tree_columns:
                value = user.get(col_key, "")
                if value is None: value = ""
                if col_key in ["is_approved", "is_archived"]:
                    value = "Ja" if value == 1 else "Nein"
                elif col_key in ['entry_date', 'last_ausbildung', 'last_schiessen', 'geburtstag', 'archived_date',
                                 'activation_date']:
                    # --- KORRIGIERTER CODEBLOCK FÜR DATUMSANZEIGE (NEUES FORMAT: TT.MM.YYYY) ---
                    DATE_FORMAT = '%d.%m.%Y'
                    if isinstance(value, datetime):
                        value = value.strftime(DATE_FORMAT)
                    elif isinstance(value, date):
                        value = value.strftime(DATE_FORMAT)
                    elif isinstance(value, str) and value:
                        try:
                            # Parsen mit DB-Format ('%Y-%m-%d'), Formatieren mit Anzeige-Format (DATE_FORMAT)
                            parsed_date = datetime.strptime(value.split(' ')[0], '%Y-%m-%d').date()
                            value = parsed_date.strftime(DATE_FORMAT)
                        except:
                            value = ""
                    else:
                        value = ""  # Leere Strings bei fehlendem/ungültigem Datum
                    # --- ENDE KORRIGIERTER CODEBLOCK ---
                elif col_key == 'last_seen':
                    DATE_TIME_FORMAT = '%d.%m.%Y %H:%M'
                    if isinstance(value, datetime):
                        # Auch hier das Datumsformat anpassen
                        value = value.strftime(DATE_TIME_FORMAT)
                    elif isinstance(value, str) and value:
                        try:
                            # Parsen mit DB-Format ('%Y-%m-%d %H:%M:%S'), Formatieren mit Anzeige-Format
                            parsed_dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                            value = parsed_dt.strftime(DATE_TIME_FORMAT)
                        except:
                            value = ""  # Fallback
                    else:
                        value = ""
                values_to_insert.append(value)

            # --- MODIFIZIERT: Tags für Hervorhebung bestimmen (inkl. Rollen) ---
            user_tags = []
            if user.get('is_archived') == 1:
                user_tags.append('archived')
            elif user.get('is_approved') == 0:
                user_tags.append('pending')
            else:
                # --- INNOVATION (Regel 2 & 4): Wende dynamische Rollenfarbe an ---
                user_role = str(user.get('role', '')).lower()
                if user_role in self.role_color_map:
                    # Weise den vorkonfigurierten Tag-Namen zu
                    user_tags.append(self.role_color_map[user_role])
                # --- ENDE INNOVATION ---
            # --- ENDE MODIFIKATION ---

            try:
                # --- MODIFIZIERT: tags=tuple(user_tags) hinzugefügt ---
                self.tree.insert("", "end", iid=user['id'], values=tuple(values_to_insert), tags=tuple(user_tags))
            except tk.TclError as e:
                print(f"TclError User {user['id']}: {e}. Skip.")

    def refresh_data(self, data_cache=None):
        """
        (Ehemals load_users) Aktualisiert die Daten.
        Nimmt optional einen Cache entgegen (Regel 2).
        Wenn kein Cache übergeben wird, lädt sie aus der DB (Fallback).
        """
        try:
            if data_cache is not None:
                print("[UserMgmtTab] Refresh aus Cache.")
                self.all_users_data = data_cache
            else:
                print("[UserMgmtTab] Refresh aus DB.")
                # Fallback: Direkter DB-Aufruf, wenn kein Cache bereitgestellt wird
                # DIESE FUNKTION LIEFERT ALLE DETAILS (für Bearbeitungsdialog)
                self.all_users_data = get_all_users_with_details()

            # Daten sortieren und in Treeview laden (ohne DB-Zugriff)
            self._load_users_from_cache()

        except Exception as e:
            messagebox.showerror("Fehler Laden", f"Benutzerdaten laden fehlgeschlagen:\n{e}", parent=self)
            import traceback;
            traceback.print_exc()

    def sort_column(self, col):
        if col not in self.all_columns: return
        if self._sort_by == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_by = col;
            self._sort_desc = False
        for c_key, (c_name, _) in self.all_columns.items():
            try:
                self.tree.heading(c_key, text=c_name)
            except tk.TclError:
                pass
        current_display_columns = self.tree['displaycolumns']
        if not current_display_columns: current_display_columns = [key for key in self.visible_column_keys if
                                                                   key != 'id' or self.all_columns['id'][1] > 0]
        if col in current_display_columns:
            try:
                header_text = self.all_columns[col][0]
                sort_indicator = " ▼" if self._sort_desc else " ▲"
                self.tree.heading(col, text=header_text + sort_indicator)
            except tk.TclError:
                pass

        # --- KORREKTUR: Ruft _load_users_from_cache() auf (kein DB-Zugriff) ---
        self._load_users_from_cache()
        # --- ENDE KORREKTUR ---

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
        try:
            self.tree.configure(displaycolumns=display_keys)
        except tk.TclError as e:
            print(f"Fehler displaycolumns: {e}")
            valid_display_keys = [k for k in display_keys if k in self.tree['columns']]
            try:
                self.tree.configure(displaycolumns=valid_display_keys)
            except tk.TclError:
                print("Setzen displaycolumns erneut fehlgeschlagen.")
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
            except tk.TclError:
                pass

        # --- KORREKTUR: Ruft _load_users_from_cache() auf (kein DB-Zugriff) ---
        self._load_users_from_cache()
        # --- ENDE KORREKTUR ---

    def add_user(self):
        edit_win = UserEditWindow(master=self, user_id=None, user_data=None, is_new=True,
                                  allowed_roles=self.admin_window.get_allowed_roles(),
                                  admin_user_id=self.current_user['id'], callback=self.on_user_saved)
        edit_win.grab_set()

    def edit_user_dialog(self, event=None):
        selected_item = self.tree.focus()
        if not selected_item: return
        try:
            user_id = int(selected_item)
        except ValueError:
            return
        user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
        if user_data:
            edit_win = UserEditWindow(master=self, user_id=user_id, user_data=user_data, is_new=False,
                                      allowed_roles=self.admin_window.get_allowed_roles(),
                                      admin_user_id=self.current_user['id'], callback=self.on_user_saved)
            edit_win.grab_set()
        else:
            print(f"Warnung: User {user_id} nicht im Cache bei Doppelklick. Versuche DB-Refresh.")
            # WICHTIG: Wenn die Daten fehlen (z.B. nach einem Preloader-Fehler),
            # erzwinge den Refresh und versuche es erneut.
            self.refresh_data()
            user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
            if user_data:
                edit_win = UserEditWindow(master=self, user_id=user_id, user_data=user_data, is_new=False,
                                          allowed_roles=self.admin_window.get_allowed_roles(),
                                          admin_user_id=self.current_user['id'], callback=self.on_user_saved)
                edit_win.grab_set()
            else:
                messagebox.showerror("Fehler", f"User {user_id} nicht geladen. DB-Fehler.", parent=self)

    def on_user_saved(self):
        clear_user_order_cache();
        # --- KORREKTUR: Ruft refresh_data() statt load_users() auf ---
        self.refresh_data()
        # --- ENDE KORREKTUR ---

    def show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid);
            self.tree.focus(iid)
            try:
                self.selected_user_id = int(iid)
            except ValueError:
                return
            self.selected_user_data = next(
                (user for user in self.all_users_data if user['id'] == self.selected_user_id), None)
            if self.selected_user_data:
                is_approved = self.selected_user_data.get('is_approved', 0) == 1
                is_archived = self.selected_user_data.get('is_archived', 0) == 1
                states = {"Freischalten": tk.DISABLED if is_approved else tk.NORMAL,
                          "Archivieren...": tk.DISABLED if is_archived else tk.NORMAL,  # Text angepasst
                          "Reaktivieren": tk.DISABLED if not is_archived else tk.NORMAL,
                          "Bearbeiten": tk.NORMAL, "Passwort zurücksetzen": tk.NORMAL, "Löschen": tk.NORMAL}
                for label, state in states.items():
                    try:
                        self.context_menu.entryconfigure(label, state=state)
                    except tk.TclError:
                        pass
                self.context_menu.tk_popup(event.x_root, event.y_root)
            else:
                self.selected_user_id = None;
                self.selected_user_data = None
            try:
                self.tree.selection_remove(self.tree.selection())
            except tk.TclError:
                pass

    def _get_selected_user_id_and_data(self):
        selected_item = self.tree.focus()
        if not selected_item: messagebox.showwarning("Auswahl", "Bitte Mitarbeiter wählen.",
                                                     parent=self); return None, None
        try:
            user_id = int(selected_item)
            user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
            if not user_data:
                # Zusätzlicher Check: Wenn user_data fehlt, erzwinge Refresh.
                self.refresh_data()
                user_data = next((user for user in self.all_users_data if user['id'] == user_id), None)
                if not user_data: messagebox.showerror("Fehler",
                                                       "User nicht gefunden (Cache und DB-Refresh fehlgeschlagen).",
                                                       parent=self); return None, None
            return user_id, user_data
        except ValueError:
            return None, None

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
            name = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            if messagebox.askyesno("Reset", f"Passwort für '{name}' resetten?", parent=self):
                pw = "NeuesPasswort123"

                # --- KORREKTUR (Fehlerbehebung): admin_id hinzugefügt (Regel 1) ---
                # Holt die ID des Admins, der eingeloggt ist und diese Aktion ausführt
                admin_id = self.current_user['id']
                ok, msg = admin_reset_password(user_id, pw, admin_id)
                # --- ENDE KORREKTUR ---

                if ok:
                    messagebox.showinfo("OK", f"{msg}\nTemp. PW: {pw}", parent=self)
                else:
                    messagebox.showerror("Fehler", msg, parent=self)

    def approve_user_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            if user_data.get('is_approved') == 1: return
            name = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            if messagebox.askyesno("Freigabe", f"'{name}' freischalten?", parent=self):
                ok, msg = approve_user(user_id, self.current_user['id'])
                if ok:
                    messagebox.showinfo("OK", msg, parent=self)
                    # --- KORREKTUR: AttributeError (Regel 1) ---
                    self.refresh_data()
                    if hasattr(self.admin_window, 'notification_manager'):
                        self.admin_window.notification_manager.check_for_updates()
                    # --- ENDE KORREKTUR ---
                else:
                    messagebox.showerror("Fehler", msg, parent=self)

    # --- KORRIGIERTE FUNKTION (War bereits korrekt in der Vorlage) ---
    def archive_user_context(self):
        """Archiviert einen Benutzer sofort oder zu einem gewählten Datum."""
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            if user_data.get('is_archived') == 1:
                messagebox.showinfo("Bereits archiviert", "Dieser Benutzer ist bereits archiviert.", parent=self)
                return

            user_fullname = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            archive_date = None  # Standard: Sofort

            # Frage, ob sofort oder später
            choice = messagebox.askyesnocancel("Archivieren",
                                               f"Möchten Sie '{user_fullname}' **sofort** archivieren?\n\n(Klicken Sie auf 'Nein', um ein Datum auszuwählen)",
                                               parent=self)

            if choice is None:  # Abbrechen
                return
            elif choice is False:  # Nein -> Datum wählen
                # Verwende simpledialog, um das Datum abzufragen
                today_str = date.today().strftime('%Y-%m-%d')
                prompt = f"Geben Sie das Datum (JJJJ-MM-TT) ein, ab dem '{user_fullname}' archiviert sein soll:\n(Muss in der Zukunft liegen)"
                date_str = simpledialog.askstring("Archivierungsdatum", prompt, initialvalue=today_str, parent=self)

                if not date_str:  # Leere Eingabe oder Abbrechen im Dialog
                    return

                try:
                    # Versuche, das Datum zu parsen und zu validieren
                    chosen_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if chosen_date <= date.today():
                        messagebox.showwarning("Ungültiges Datum", "Das Archivierungsdatum muss in der Zukunft liegen.",
                                               parent=self)
                        return
                    # Setze die Uhrzeit auf 00:00:00 für den Vergleich in der DB
                    archive_date = datetime.combine(chosen_date, datetime.min.time())
                    print(f"[DEBUG] Gewähltes Archivierungsdatum: {archive_date}")
                except ValueError:
                    messagebox.showerror("Ungültiges Format", "Bitte geben Sie das Datum im Format JJJJ-MM-TT ein.",
                                         parent=self)
                    return

            # Führe die Archivierung durch (entweder mit None für sofort oder mit dem gewählten Datum)
            success, message = archive_user(user_id, self.current_user['id'], archive_date=archive_date)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                clear_user_order_cache()
                # --- KORREKTUR: AttributeError (Regel 1) ---
                self.refresh_data()  # Lade neu, um das Datum anzuzeigen (wenn Spalte sichtbar)
                if hasattr(self.admin_window, 'notification_manager'):
                    self.admin_window.notification_manager.check_for_updates()
                # --- ENDE KORREKTUR ---
            else:
                messagebox.showerror("Fehler", message, parent=self)

    # --- ENDE KORRIGIERTE FUNKTION ---

    def unarchive_user_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            if user_data.get('is_archived') == 0: return
            name = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            if messagebox.askyesno("Reaktivieren", f"'{name}' reaktivieren?", parent=self):
                ok, msg = unarchive_user(user_id, self.current_user['id'])
                if ok:
                    messagebox.showinfo("OK", msg, parent=self)
                    clear_user_order_cache()
                    # --- KORREKTUR: AttributeError (Regel 1) ---
                    self.refresh_data()
                    if hasattr(self.admin_window, 'notification_manager'):
                        self.admin_window.notification_manager.check_for_updates()
                    # --- ENDE KORREKTUR ---
                else:
                    messagebox.showerror("Fehler", msg, parent=self)

    def delete_user_context(self):
        user_id, user_data = self._get_selected_user_id_and_data()
        if user_id and user_data:
            name = f"{user_data.get('vorname', '')} {user_data.get('name', '')}".strip()
            if messagebox.askyesno("Löschen", f"'{name}' wirklich löschen?", icon='warning', parent=self):
                ok, msg = delete_user(user_id, self.current_user['id'])
                if ok:
                    messagebox.showinfo("OK", msg, parent=self)
                    clear_user_order_cache()
                    # --- KORREKTUR: AttributeError (Regel 1) ---
                    self.refresh_data()
                    if hasattr(self.admin_window, 'notification_manager'):
                        self.admin_window.notification_manager.check_for_updates()
                    # --- ENDE KORREKTUR ---
                else:
                    messagebox.showerror("Fehler", msg, parent=self)

    # --- KORRIGIERTE FUNKTION (War bereits korrekt in der Vorlage) ---
    def check_pending_approvals(self):
        """Prüft auf Freischaltungen und zeigt Meldung NUR wenn welche anstehen."""
        try:
            pending_users = get_pending_approval_users()
            if pending_users:  # Nur wenn Liste nicht leer ist
                user_list = "\n".join([f"- {user['vorname']} {user['name']}" for user in pending_users])
                messagebox.showinfo("Ausstehende Freischaltungen",
                                    f"Die folgenden Benutzer warten auf Freischaltung:\n{user_list}",
                                    parent=self)
            # else: Keine Meldung ausgeben, wenn nichts ansteht
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Prüfen der Freischaltungen:\n{e}", parent=self)

    # --- INNOVATION (Regel 2 & 4): Neuer Callback ---
    def on_roles_changed(self):
        """
        Wird aufgerufen, wenn der Rollen-Dialog geschlossen wird.
        Lädt die Rollenfarben neu (aus der DB) UND aktualisiert
        die Benutzerliste. (Regel 1 & 2)
        """
        print("[UserMgmtTab] Rollenverwaltung geschlossen. Lade Farben und Daten neu.")
        self._load_and_configure_role_colors()
        self.refresh_data()

    # --- ENDE INNOVATION ---

    # --- NEUE METHODE FÜR ROLLENVERWALTUNG (Regel 4) ---
    def open_role_management(self):
        """
        Öffnet den Dialog zur Rollenverwaltung.
        """
        # --- INNOVATION (Regel 2 & 4): Ruft neuen Callback auf ---
        # (Verwendet die NEUE Datei role_management_dialog.py)
        RoleManagementDialog(self, on_close_callback=self.on_roles_changed)
    # --- ENDE NEUE METHODE ---


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
        self.geometry(f"+{master.winfo_rootx() + 50}+{master.winfo_rooty() + 50}")
        main_frame = ttk.Frame(self, padding="10");
        main_frame.pack(expand=True, fill="both")
        ttk.Label(main_frame, text="Wählen Sie die anzuzeigenden Spalten aus:").pack(pady=(0, 10))
        checkbox_frame = ttk.Frame(main_frame);
        checkbox_frame.pack(expand=True, fill="x")
        sorted_column_items = sorted(self.all_columns.items(), key=lambda item: item[1][0])
        for key, (name, width) in sorted_column_items:
            if key == "id" and width <= 0: continue
            is_visible = key in self.visible_keys_for_display
            var = tk.BooleanVar(value=is_visible)
            ttk.Checkbutton(checkbox_frame, text=name, variable=var).pack(anchor="w", padx=5)
            self.vars[key] = var
        button_frame = ttk.Frame(main_frame);
        button_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(button_frame, text="OK", command=self.apply_changes, style="Accent.TButton").pack(side="right",
                                                                                                     padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right")
        self.grab_set();
        self.focus_set();
        self.wait_window()

    def apply_changes(self):
        new_visible = []
        for key in self.all_columns:
            if key == 'id':
                if key in self.vars and self.vars[key].get() and self.all_columns['id'][1] > 0:
                    new_visible.append(key)
                continue
            if key in self.vars and self.vars[key].get():
                new_visible.append(key)
        self.callback(new_visible);
        self.destroy()

