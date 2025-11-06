import tkinter as tk
from tkinter import ttk, messagebox
import json

# DB-Funktionen (verwenden jetzt die neuen 'details'-Funktionen)
from database.db_roles import (
    get_all_roles_details, create_role, delete_role,
    save_roles_details, ALL_ADMIN_TABS
)

# Import der Drag-and-Drop-Liste (aus vorherigem Schritt)
from .role_hierarchy_list import RoleHierarchyList

# --- NEU (Zentralisierung): Import aus dem Window Manager (Regel 4) ---
try:
    from gui.window_manager import get_window_options_for_roles
except ImportError:
    print("[FEHLER] window_manager.py nicht gefunden. Verwende Fallback für Fenster-Optionen.")


    # (Regel 1) Fallback, falls Import fehlschlägt
    def get_window_options_for_roles():
        return {
            'Benutzer-Fenster': 'main_user_window',
            'Admin-Fenster': 'main_admin_window',
            'Zuteilungs-Fenster': 'main_zuteilung_window'
        }


# --- ENDE NEU ---


class RoleManagementDialog(tk.Toplevel):
    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        self.title("Rollen- und Berechtigungsverwaltung")
        self.geometry("750x600")  # Größer für mehr Inhalt
        self.transient(master)
        self.grab_set()

        self.on_close_callback = on_close_callback
        self.all_roles_data = []  # Speichert alle Rollen-Dicts
        self.current_selected_role_id = None

        # UI-Variablen für die Checkboxen
        self.permission_vars = {}  # Speichert {tab_name: tk.BooleanVar}

        # --- ANPASSUNG (Schema): Variable für Hauptfenster ---
        # Standardwert ist jetzt der DB-Wert
        self.window_type_var = tk.StringVar(value='main_user_window')

        # Definiert die Anzeigenamen und die DB-Werte (gemäß db_schema.py)
        # --- KORREKTUR (Regel 4): Lädt Optionen jetzt aus zentralem Manager ---
        self.window_type_options = get_window_options_for_roles()
        # --- ENDE KORREKTUR ---

        # --- Styles ---
        style = ttk.Style(self)
        try:
            style.configure("Danger.TButton", foreground="red")
            style.map("Danger.TButton",
                      foreground=[('active', 'white')],
                      background=[('active', 'red')])
        except tk.ToplevelError:
            pass

        # --- Haupt-Layout (PanedWindow für Größenänderung) ---
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill='both', expand=True, padx=10, pady=10)

        # --- Linke Seite: Hierarchie-Liste ---
        left_frame = ttk.Frame(main_pane, padding=5)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        main_pane.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Rollen-Hierarchie (Ziehen zum Sortieren)",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        # Neue Drag-Drop-Liste
        self.hierarchy_list = RoleHierarchyList(left_frame)
        self.hierarchy_list.grid(row=1, column=0, columnspan=2, sticky="nsew")

        # Callback, wenn Auswahl sich ändert -> Lade Berechtigungen rechts
        self.hierarchy_list.bind_selection_changed(self.on_role_selected)

        # Buttons unter der Liste (Erstellen/Löschen)
        list_btn_frame = ttk.Frame(left_frame)
        list_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        list_btn_frame.columnconfigure(0, weight=1)

        self.new_role_entry = ttk.Entry(list_btn_frame)
        self.new_role_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        create_btn = ttk.Button(list_btn_frame, text="Erstellen", width=10, command=self.add_new_role)
        create_btn.grid(row=0, column=1, sticky="e")

        delete_btn = ttk.Button(left_frame, text="Auswahl löschen",
                                style="Danger.TButton", command=self.delete_selected_role)
        delete_btn.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        # --- Rechte Seite: Berechtigungen ---
        self.right_frame = ttk.Labelframe(main_pane, text="Berechtigungen für: [Bitte Rolle wählen]", padding=15)
        self.right_frame.columnconfigure(0, weight=1)
        main_pane.add(self.right_frame, weight=2)

        # --- Frame für Hauptfenster ---
        window_type_frame = ttk.Frame(self.right_frame)
        window_type_frame.pack(fill='x', pady=(0, 15))

        ttk.Label(window_type_frame, text="Fenster nach Login:", font=("Segoe UI", 10, "bold")).pack(side="left",
                                                                                                     padx=(0, 10))

        self.window_type_combo = ttk.Combobox(
            window_type_frame,
            textvariable=self.window_type_var,
            values=list(self.window_type_options.keys()),  # Werte kommen jetzt vom Manager
            state='disabled'  # Startet deaktiviert
        )
        self.window_type_combo.pack(side="left", fill="x", expand=True)
        # Bindet die Änderung an eine neue Funktion
        self.window_type_combo.bind("<<ComboboxSelected>>", self.on_window_type_changed)
        # --- ENDE ---

        ttk.Separator(self.right_frame, orient='horizontal').pack(fill='x', pady=(0, 10))

        # Checkboxen-Container
        self.permissions_frame = ttk.Frame(self.right_frame)
        self.permissions_frame.pack(fill='both', expand=True)

        # Erstelle die Checkboxen (anfangs deaktiviert)
        self.create_permission_checkboxes()
        self.set_permission_widgets_state(tk.DISABLED)

        # --- Untere Button-Leiste (Speichern/Schließen) ---
        bottom_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom_frame.pack(fill='x', side='bottom')

        self.status_label = ttk.Label(bottom_frame, text="")
        self.status_label.pack(side="left", padx=5)

        close_btn = ttk.Button(bottom_frame, text="Schließen", command=self.close_dialog)
        close_btn.pack(side="right")

        save_btn = ttk.Button(bottom_frame, text="Speichern & Schließen", command=self.save_and_close)
        save_btn.pack(side="right", padx=5)

        # --- Initiale Daten laden ---
        self.load_roles()

        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

    def create_permission_checkboxes(self):
        """Erstellt die Checkbox-Widgets für alle Admin-Tabs."""
        num_cols = 2

        # Sortierte Liste für konsistente Anzeige
        sorted_tab_names = sorted(ALL_ADMIN_TABS)

        for i, tab_name in enumerate(sorted_tab_names):
            var = tk.BooleanVar(value=False)
            self.permission_vars[tab_name] = var

            cb = ttk.Checkbutton(self.permissions_frame, text=tab_name, variable=var,
                                 command=self.on_permission_changed)

            row = i // num_cols
            col = i % num_cols
            cb.grid(row=row, column=col, sticky="w", padx=10, pady=5)
            if col == 0:
                self.permissions_frame.columnconfigure(0, weight=1)
            if col == 1:
                self.permissions_frame.columnconfigure(1, weight=1)

    def set_permission_widgets_state(self, state):
        """Aktiviert oder deaktiviert alle Checkboxen UND die Combobox."""
        # 'disabled' oder 'readonly' für die Combobox
        combo_state = 'readonly' if state == tk.NORMAL else 'disabled'
        self.window_type_combo.config(state=combo_state)  # Angepasst

        for child in self.permissions_frame.winfo_children():
            if isinstance(child, ttk.Checkbutton):
                child.config(state=state)

    def load_roles(self):
        """Lädt alle Rollen (inkl. Details) und füllt die Hierarchie-Liste."""
        self.all_roles_data = get_all_roles_details()
        self.hierarchy_list.populate(self.all_roles_data)
        self.clear_permission_display()

    def on_role_selected(self, event=None):
        """
        Wird aufgerufen, wenn eine Rolle in der Hierarchie-Liste ausgewählt wird.
        Lädt die Berechtigungen UND den Fenstertyp dieser Rolle.
        """
        role_data = self.hierarchy_list.get_selected_role_data()

        if not role_data:
            self.clear_permission_display()
            return

        self.current_selected_role_id = role_data['id']
        self.right_frame.config(text=f"Berechtigungen für: {role_data['name']}")

        # --- ANPASSUNG (Schema): Hauptfenster laden ---
        # (Regel 1) Fallback auf 'main_user_window'
        db_window_value = role_data.get('main_window', 'main_user_window')

        # Finde den Anzeigenamen (z.B. 'Admin-Fenster')
        display_name = 'Benutzer-Fenster'  # Fallback

        # (Regel 1): Diese Schleife findet jetzt auch 'Zuteilungs-Fenster'
        # da self.window_type_options vom Manager geladen wird.
        for key, value in self.window_type_options.items():
            if value == db_window_value:
                display_name = key
                break
        self.window_type_var.set(display_name)
        # --- ENDE ANPASSUNG ---

        # 3. Berechtigungen laden
        role_permissions = role_data.get('permissions', {})

        # 4. Checkboxen füllen
        is_master_role = role_data['name'] in ['Admin', 'SuperAdmin']
        for tab_name, var in self.permission_vars.items():
            # Standard: True, wenn die Rolle 'Admin'/'SuperAdmin' ist, sonst False
            var.set(role_permissions.get(tab_name, is_master_role))

        # 5. Checkboxen aktivieren (außer für Master-Rollen)
        if is_master_role:
            # Checkboxen deaktivieren
            for child in self.permissions_frame.winfo_children():
                if isinstance(child, ttk.Checkbutton):
                    child.config(state=tk.DISABLED)
            # Combobox ERLAUBEN (Regel 1: Admins müssen ihr Fenster ändern können)
            self.window_type_combo.config(state='readonly')
            self.status_label.config(text=f"Info: '{role_data['name']}' hat immer alle Tab-Rechte.")
        else:
            self.set_permission_widgets_state(tk.NORMAL)  # Aktiviert alles
            self.status_label.config(text="")

    def _find_role_data_in_cache(self, role_id):
        """Hilfsfunktion: Findet die Rolle im Haupt-Cache."""
        role_data = next((r for r in self.all_roles_data if r['id'] == role_id), None)
        if not role_data:
            list_data = self.hierarchy_list.get_ordered_data()
            role_data = next((r for r in list_data if r['id'] == role_id), None)
        return role_data

    def on_window_type_changed(self, event=None):
        """
        Wird aufgerufen, wenn die Combobox geändert wird.
        Speichert den neuen Wert (z.B. 'main_admin_window') im Daten-Cache (self.all_roles_data).
        """
        if self.current_selected_role_id is None:
            return

        role_data = self._find_role_data_in_cache(self.current_selected_role_id)

        if role_data:
            display_name = self.window_type_var.get()  # z.B. 'Zuteilungs-Fenster'
            # --- ANPASSUNG (Schema): Korrekten DB-Wert und Fallback holen ---
            db_value = self.window_type_options.get(display_name, 'main_user_window')  # z.B. 'main_zuteilung_window'

            # Speichere die Änderung im Haupt-Cache
            role_data['main_window'] = db_value
            print(f"Cache für Rolle ID {role_data['id']} auf main_window='{db_value}' gesetzt.")
            # --- ENDE ANPASSUNG ---

    def on_permission_changed(self):
        """
        Speichert geänderte Checkbox-Werte im Daten-Cache (self.all_roles_data).
        """
        if self.current_selected_role_id is None:
            return

        role_data = self._find_role_data_in_cache(self.current_selected_role_id)

        if role_data:
            if 'permissions' not in role_data:
                role_data['permissions'] = {}
            for tab_name, var in self.permission_vars.items():
                role_data['permissions'][tab_name] = var.get()

    def clear_permission_display(self):
        """Setzt die rechte Seite zurück."""
        self.right_frame.config(text="Berechtigungen für: [Bitte Rolle wählen]")
        self.current_selected_role_id = None

        # (Regel 1) Setzt den Fallback-Wert (erster Wert aus der Liste)
        fallback_display_name = list(self.window_type_options.keys())[0] if self.window_type_options else ""
        self.window_type_var.set(fallback_display_name)

        for var in self.permission_vars.values():
            var.set(False)
        self.set_permission_widgets_state(tk.DISABLED)
        self.status_label.config(text="")

    def add_new_role(self):
        role_name = self.new_role_entry.get()
        if not role_name:
            messagebox.showwarning("Eingabe fehlt", "Bitte einen Rollennamen eingeben.", parent=self)
            return

        # (Regel 1) Wir nutzen die create_role Funktion aus db_roles.py,
        # die automatisch das korrekte Standard-Fenster ('main_user_window') setzt.
        if create_role(role_name):
            messagebox.showinfo("Erfolg", f"Rolle '{role_name}' wurde erstellt.", parent=self)
            self.new_role_entry.delete(0, 'end')
            self.load_roles()  # Liste neu laden
        else:
            messagebox.showerror("Fehler",
                                 f"Rolle '{role_name}' konnte nicht erstellt werden (existiert evtl. schon?).",
                                 parent=self)

    def delete_selected_role(self):
        role_data = self.hierarchy_list.get_selected_role_data()
        if not role_data:
            messagebox.showwarning("Keine Auswahl", "Bitte eine Rolle zum Löschen auswählen.", parent=self)
            return

        role_id = role_data['id']
        role_name = role_data['name']

        # (Regel 1) Wir nutzen die delete_role Funktion aus db_roles.py,
        # die die Prüfung auf Standardrollen (IDs 1-4) und Benutzerzuweisung
        # bereits serverseitig durchführt.

        # Lokale Prüfung (doppelt, aber User-freundlich)
        if role_id in [1, 2, 3, 4]:
            messagebox.showerror("Gesperrt",
                                 "Die Standardrollen (Admin, Mitarbeiter, Gast, SuperAdmin) können nicht gelöscht werden.",
                                 parent=self)
            return

        if not messagebox.askyesno("Bestätigen",
                                   f"Sind Sie sicher, dass Sie die Rolle '{role_name}' löschen wollen?\n\nDies ist nur möglich, wenn kein Benutzer dieser Rolle zugewiesen ist.",
                                   parent=self):
            return

        success, message = delete_role(role_id)
        if success:
            messagebox.showinfo("Erfolg", f"Rolle '{role_name}' wurde gelöscht.", parent=self)
            self.load_roles()  # Liste neu laden
        else:
            messagebox.showerror("Fehler", f"Rolle '{role_name}' konnte nicht gelöscht werden.\n({message})",
                                 parent=self)

    def save_and_close(self):
        """Speichert Hierarchie, Berechtigungen UND Hauptfenster."""

        # 1. Hole die sortierten Daten (aus der Drag-Drop-Liste)
        ordered_list_data = self.hierarchy_list.get_ordered_data()

        # 2. Stelle sicher, dass die Daten in ordered_list_data
        #    die Änderungen aus dem Cache (self.all_roles_data) enthalten
        #    (Das sollte durch on_permission_changed und on_window_type_changed
        #    bereits der Fall sein, da beide Listen auf dieselben Dicts zeigen)

        cache_dict = {r['id']: r for r in self.all_roles_data}
        final_data_to_save = []
        for list_role in ordered_list_data:
            if list_role['id'] in cache_dict:
                # Nimm die Daten aus dem Haupt-Cache (die Änderungen enthalten)
                final_data_to_save.append(cache_dict[list_role['id']])
            else:
                final_data_to_save.append(list_role)

        # 3. Speichere in DB (Regel 1)
        # Wir rufen save_roles_details auf,
        # das 'main_window' speichert.
        success, message = save_roles_details(final_data_to_save)

        if success:
            messagebox.showinfo("Gespeichert", message, parent=self)
            self.close_dialog()  # Ruft auch Callback auf
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def close_dialog(self):
        # (Funktion bleibt unverändert)
        if self.on_close_callback:
            if hasattr(self.on_close_callback, '__name__') and self.on_close_callback.__name__ == 'refresh_data':
                self.on_close_callback()
            else:
                self.on_close_callback()

            try:
                # master -> user_management_tab -> admin_window (self.admin_window)
                admin_window = self.master.admin_window
                if admin_window and hasattr(admin_window, 'tab_manager'):
                    print("Info: Berechtigungen geändert. Tabs werden neu evaluiert.")
                    admin_window.tab_manager.reevaluate_tab_permissions()
            except Exception as e:
                print(f"Warnung: Konnte TabManager nicht über Rechteänderung informieren: {e}")

        self.destroy()