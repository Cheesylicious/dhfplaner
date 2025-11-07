# gui/dialogs/role_management_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkinter.colorchooser import askcolor
import json  # Wird hier nicht direkt benötigt, aber db_roles verwendet es

from database.db_roles import (
    get_all_roles_details, create_role, delete_role,
    save_roles_details, ALL_ADMIN_TABS
)


# (Stellen Sie sicher, dass db_roles.py (von oben) gespeichert ist)


class RoleManagementDialog(tk.Toplevel):
    """
    Ein Toplevel-Fenster (Dialog) zur Verwaltung von Rollen,
    Hierarchien, Berechtigungen und Farben (INNOVATION Regel 2 & 4).
    """

    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        self.title("Rollenverwaltung")
        self.geometry("900x700")
        self.transient(master)
        self.grab_set()

        self.on_close_callback = on_close_callback

        # Daten-Cache für den Dialog
        self.roles_data = []

        # UI-Komponenten
        self.notebook = ttk.Notebook(self)

        # --- Tab 1: Rollen & Farben (NEU) ---
        self.tab1 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab1, text="Rollen & Farben")
        self._create_roles_tab()

        # --- Tab 2: Hierarchie & Berechtigungen ---
        self.tab2 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab2, text="Hierarchie & Berechtigungen")
        self._create_permissions_tab()

        self.notebook.pack(expand=True, fill="both", pady=5, padx=5)

        # --- Speicher-Button ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", side="bottom", pady=10, padx=10)

        ttk.Label(btn_frame, text="Änderungen werden erst nach Klick auf 'Speichern' aktiv.").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Speichern & Schließen", command=self.save_and_close, style="Accent.TButton").pack(
            side="right", padx=5)
        ttk.Button(btn_frame, text="Abbrechen", command=self.on_dialog_close).pack(side="right", padx=5)

        # Daten laden
        self.load_data()

        # Beim Schließen (X) den Callback ausführen
        self.protocol("WM_DELETE_WINDOW", self.on_dialog_close)

    def on_dialog_close(self):
        """Wird aufgerufen, wenn das Fenster geschlossen wird (z.B. über das 'X' oder Abbrechen)."""
        # (Wir rufen den Callback immer auf, damit die Farben im Hauptfenster neu geladen werden)
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()

    def load_data(self):
        """Lädt die Rollendaten aus der DB in den internen Cache."""
        try:
            self.roles_data = get_all_roles_details()
            # Fülle beide Tabs mit den neuen Daten
            self._populate_roles_tab()
            self._populate_permissions_tab()
        except Exception as e:
            messagebox.showerror("Fehler", f"Rollen konnten nicht geladen werden: {e}", parent=self)
            self.roles_data = []

    # --- Logik für Tab 1: Rollen & Farben ---

    def _create_roles_tab(self):
        main_frame = ttk.Frame(self.tab1)
        main_frame.pack(expand=True, fill="both")

        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # Linke Seite: Liste der Rollen
        list_frame = ttk.Frame(main_frame, padding=5)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        list_frame.grid_rowconfigure(1, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(list_frame, text="Vorhandene Rollen", style="Headline.TLabel").pack(anchor="w", pady=5)

        # --- KORREKTUR (Regel 1): show="headings" -> show="tree" ---
        # (Damit wird die #0-Spalte (Baum-Spalte) angezeigt, in der die Namen stehen)
        self.roles_tree = ttk.Treeview(list_frame, columns=(), show="tree")
        self.roles_tree.heading("#0", text="Rollenname (Vorschau)")
        # --- ENDE KORREKTUR ---

        self.roles_tree.pack(expand=True, fill="both")

        self.roles_tree.bind("<<TreeviewSelect>>", self._on_role_select)

        # Rechte Seite: Aktionen
        action_frame = ttk.Frame(main_frame, padding=5)
        action_frame.grid(row=0, column=1, sticky="nw")

        ttk.Label(action_frame, text="Aktionen", style="Headline.TLabel").pack(anchor="w", pady=5)

        self.new_role_entry = ttk.Entry(action_frame, width=30)
        self.new_role_entry.pack(fill="x", pady=(5, 2))
        ttk.Button(action_frame, text="Neue Rolle erstellen", command=self._create_new_role).pack(fill="x",
                                                                                                  pady=(0, 10))

        ttk.Separator(action_frame, orient="horizontal").pack(fill="x", pady=10)

        # Details für ausgewählte Rolle
        self.details_frame = ttk.Frame(action_frame)
        self.details_frame.pack(fill="x", pady=5)
        self.details_label = ttk.Label(self.details_frame, text="Wählen Sie eine Rolle...", style="Italic.TLabel")
        self.details_label.pack()

        # (Verwende tk.Frame statt ttk.Frame für 'background')
        self.color_frame = tk.Frame(self.details_frame, height=30, width=100, relief="sunken", borderwidth=1)

        self.color_button = ttk.Button(self.details_frame, text="Farbe ändern", command=self._change_role_color,
                                       state="disabled")
        self.delete_button = ttk.Button(self.details_frame, text="Rolle löschen", command=self._delete_selected_role,
                                        state="disabled")

    def _populate_roles_tab(self):
        """Füllt die Treeview im Rollen-Tab."""
        self.roles_tree.delete(*self.roles_tree.get_children())
        for role in self.roles_data:
            role_id = role['id']
            role_name = role['name']
            role_color = role.get('color', '#FFFFFF')

            # Definiere einen Tag für die Farbe (dient als Vorschau)
            tag_name = f"role_{role_id}"
            self.roles_tree.tag_configure(tag_name, background=role_color)

            # Füge Eintrag hinzu (text=... füllt die #0-Spalte)
            self.roles_tree.insert("", "end", iid=role_id, text=f" {role_name}", tags=(tag_name,))

    def _on_role_select(self, event=None):
        """Aktualisiert die Detail-Ansicht, wenn eine Rolle ausgewählt wird."""
        selected_item = self.roles_tree.focus()
        if not selected_item:
            self._show_role_details(None)
            return

        role_id = int(selected_item)
        role = next((r for r in self.roles_data if r['id'] == role_id), None)
        self._show_role_details(role)

    def _show_role_details(self, role):
        """Zeigt die Aktionen für die ausgewählte Rolle an."""
        # Lösche alte Widgets
        for w in [self.details_label, self.color_frame, self.color_button, self.delete_button]:
            w.pack_forget()

        if role:
            self.details_label.configure(text=f"Bearbeite: {role['name']}", style="Bold.TLabel")

            # (tk.Frame)
            self.color_frame.configure(background=role.get('color', '#FFFFFF'))

            self.color_button.configure(state="normal")

            # Standardrollen nicht löschbar machen
            if role['id'] in [1, 2, 3, 4]:
                self.delete_button.configure(state="disabled")
            else:
                self.delete_button.configure(state="normal")

            self.details_label.pack(fill="x")
            self.color_frame.pack(fill="x", pady=5)
            self.color_button.pack(fill="x", pady=5)
            self.delete_button.pack(fill="x", pady=(10, 5))
        else:
            self.details_label.configure(text="Wählen Sie eine Rolle...", style="Italic.TLabel")
            self.color_button.configure(state="disabled")
            self.delete_button.configure(state="disabled")
            self.details_label.pack()

    def _create_new_role(self):
        role_name = self.new_role_entry.get().strip()
        if not role_name:
            messagebox.showwarning("Fehler", "Rollenname darf nicht leer sein.", parent=self)
            return
        if any(r['name'].lower() == role_name.lower() for r in self.roles_data):
            messagebox.showwarning("Fehler", "Eine Rolle mit diesem Namen existiert bereits.", parent=self)
            return

        if create_role(role_name):
            messagebox.showinfo("Erfolg", f"Rolle '{role_name}' erstellt. (Farbe/Rechte in Tabs anpassen)",
                                parent=self)
            self.new_role_entry.delete(0, "end")
            self.load_data()  # Daten neu laden, um IDs/Farben zu haben
        else:
            messagebox.showerror("Fehler", "Rolle konnte nicht erstellt werden (DB-Fehler).", parent=self)

    def _change_role_color(self):
        selected_item = self.roles_tree.focus()
        if not selected_item: return
        role_id = int(selected_item)

        role = next((r for r in self.roles_data if r['id'] == role_id), None)
        if not role: return

        # Öffne Farbwähler (Dies ist der visuelle Dialog)
        color_code = askcolor(title="Farbe wählen", initialcolor=role.get('color', '#FFFFFF'))

        if color_code and color_code[1]:  # (RGB-Tupel, Hex-String)
            new_color_hex = color_code[1]

            # 1. Aktualisiere den lokalen Cache
            role['color'] = new_color_hex

            # 2. Aktualisiere die GUI (Treeview und Vorschau)
            tag_name = f"role_{role_id}"
            self.roles_tree.tag_configure(tag_name, background=new_color_hex)

            # (Workaround - jetzt korrekt für tk.Frame)
            self.color_frame.configure(background=new_color_hex)

            print(f"Farbe für {role['name']} geändert zu {new_color_hex} (im Cache).")
            # HINWEIS: Speichern erfolgt erst beim Klick auf "Speichern & Schließen"

    def _delete_selected_role(self):
        selected_item = self.roles_tree.focus()
        if not selected_item: return
        role_id = int(selected_item)
        role = next((r for r in self.roles_data if r['id'] == role_id), None)
        if not role: return

        if messagebox.askyesno("Löschen",
                               f"Möchten Sie die Rolle '{role['name']}' wirklich löschen?\n\n(Nur möglich, wenn kein Benutzer diese Rolle hat)",
                               parent=self):
            success, msg = delete_role(role_id)
            if success:
                messagebox.showinfo("Erfolg", msg, parent=self)
                self.load_data()  # Daten neu laden
                self._show_role_details(None)
            else:
                messagebox.showerror("Fehler", msg, parent=self)

    # --- Logik für Tab 2: Hierarchie & Berechtigungen ---

    def _create_permissions_tab(self):
        main_frame = ttk.Frame(self.tab2)
        main_frame.pack(expand=True, fill="both")
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # Links: Hierarchie
        h_frame = ttk.Frame(main_frame, padding=5)
        h_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        h_frame.grid_rowconfigure(1, weight=1)

        ttk.Label(h_frame, text="Hierarchie (Wichtigste oben)", style="Headline.TLabel").pack(anchor="w", pady=5)
        self.hierarchy_list = tk.Listbox(h_frame, width=30, selectmode="browse")
        self.hierarchy_list.pack(side="left", fill="y", expand=True)
        self.hierarchy_list.bind("<<ListboxSelect>>", self._on_hierarchy_select)

        btn_h_frame = ttk.Frame(h_frame)
        btn_h_frame.pack(side="left", fill="y", padx=5)
        self.h_up_btn = ttk.Button(btn_h_frame, text="▲ Nach Oben", command=self._move_hierarchy_up, state="disabled")
        self.h_up_btn.pack(pady=2)
        self.h_down_btn = ttk.Button(btn_h_frame, text="▼ Nach Unten", command=self._move_hierarchy_down,
                                     state="disabled")
        self.h_down_btn.pack(pady=2)

        # Rechts: Berechtigungen
        self.p_frame = ttk.Frame(main_frame, padding=5)
        self.p_frame.grid(row=0, column=1, sticky="nsew")

        ttk.Label(self.p_frame, text="Berechtigungen", style="Headline.TLabel").pack(anchor="w", pady=5)

        # Canvas und Scrollbar für Checkboxen
        self.p_canvas = tk.Canvas(self.p_frame, borderwidth=0)
        self.p_scroll_frame = ttk.Frame(self.p_canvas)
        self.p_vsb = ttk.Scrollbar(self.p_frame, orient="vertical", command=self.p_canvas.yview)
        self.p_canvas.configure(yscrollcommand=self.p_vsb.set)

        self.p_vsb.pack(side="right", fill="y")
        self.p_canvas.pack(side="left", fill="both", expand=True)
        self.p_canvas.create_window((4, 4), window=self.p_scroll_frame, anchor="nw")

        self.p_scroll_frame.bind("<Configure>",
                                 lambda e: self.p_canvas.configure(scrollregion=self.p_canvas.bbox("all")))

        # Checkbox-Variablen
        self.perm_vars = {}
        self.perm_checks = {}

        # Erstelle die Checkboxen (einmalig)
        for tab_name in ALL_ADMIN_TABS:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(self.p_scroll_frame, text=tab_name, variable=var, state="disabled",
                                 command=lambda v=var, t=tab_name: self._on_perm_change(t, v))
            cb.pack(anchor="w", padx=5)
            self.perm_vars[tab_name] = var
            self.perm_checks[tab_name] = cb

        # Platzhalter, wenn keine Rolle gewählt ist
        self.p_label = ttk.Label(self.p_scroll_frame, text="Bitte Rolle in Hierarchie-Liste auswählen.",
                                 style="Italic.TLabel")
        self.p_label.pack(pady=20)

    def _populate_permissions_tab(self):
        """Füllt die Hierarchie-Liste (Daten sind bereits in self.roles_data)."""
        self.hierarchy_list.delete(0, "end")
        # Sortiert nach Hierarchie (ist bereits in roles_data)
        for role in self.roles_data:
            self.hierarchy_list.insert("end", role['name'])

    def _on_hierarchy_select(self, event=None):
        """Lädt die Berechtigungen für die links ausgewählte Rolle."""
        try:
            selected_index = self.hierarchy_list.curselection()[0]
        except IndexError:
            self._update_permission_checks(None)
            self.h_up_btn.config(state="disabled")
            self.h_down_btn.config(state="disabled")
            return

        role_name = self.hierarchy_list.get(selected_index)
        role = next((r for r in self.roles_data if r['name'] == role_name), None)
        self._update_permission_checks(role)

        # Buttons (Hoch/Runter) aktivieren
        self.h_up_btn.config(state="normal" if selected_index > 0 else "disabled")
        self.h_down_btn.config(state="normal" if selected_index < (self.hierarchy_list.size() - 1) else "disabled")

    def _update_permission_checks(self, role):
        """Aktualisiert die Checkboxen rechts."""
        if role:
            self.p_label.pack_forget()
            permissions = role.get('permissions', {})
            for tab_name in ALL_ADMIN_TABS:
                is_allowed = permissions.get(tab_name, False)
                self.perm_vars[tab_name].set(is_allowed)
                self.perm_checks[tab_name].config(state="normal")
        else:
            # Keine Rolle ausgewählt
            self.p_label.pack(pady=20)
            for tab_name in ALL_ADMIN_TABS:
                self.perm_vars[tab_name].set(False)
                self.perm_checks[tab_name].config(state="disabled")

    def _on_perm_change(self, tab_name, var):
        """Speichert die geänderte Berechtigung im lokalen Cache."""
        try:
            selected_index = self.hierarchy_list.curselection()[0]
            role = self.roles_data[selected_index]  # Verlässt sich auf Sortierung
            role['permissions'][tab_name] = var.get()
            print(f"Berechtigung {tab_name} für {role['name']} geändert (im Cache).")
        except IndexError:
            print(f"Fehler: Berechtigung {tab_name} geändert, aber keine Rolle ausgewählt.")

    def _move_hierarchy_up(self):
        try:
            idx = self.hierarchy_list.curselection()[0]
            if idx == 0: return

            # Tausche im Cache (self.roles_data)
            self.roles_data[idx], self.roles_data[idx - 1] = self.roles_data[idx - 1], self.roles_data[idx]

            # Fülle UI neu
            self._populate_permissions_tab()
            self.hierarchy_list.selection_set(idx - 1)
            self._on_hierarchy_select()
        except IndexError:
            pass

    def _move_hierarchy_down(self):
        try:
            idx = self.hierarchy_list.curselection()[0]
            if idx == self.hierarchy_list.size() - 1: return

            # Tausche im Cache (self.roles_data)
            self.roles_data[idx], self.roles_data[idx + 1] = self.roles_data[idx + 1], self.roles_data[idx]

            # Fülle UI neu
            self._populate_permissions_tab()
            self.hierarchy_list.selection_set(idx + 1)
            self._on_hierarchy_select()
        except IndexError:
            pass

    # --- Speichern & Schließen ---

    def save_and_close(self):
        """
        Speichert ALLE Daten (Hierarchie, Berechtigungen, Farben)
        aus dem lokalen Cache (self.roles_data) in die DB.
        """

        # 1. Aktualisiere die Hierarchie-Ebene im Cache, falls sie
        #    durch Hoch/Runter verschoben wurde
        for index, role in enumerate(self.roles_data):
            role['hierarchy_level'] = index + 1

        # 2. Rufe die (modifizierte) DB-Funktion auf
        try:
            success, msg = save_roles_details(self.roles_data)
            if success:
                messagebox.showinfo("Erfolg", "Alle Rollen-Einstellungen gespeichert.", parent=self)
                self.on_dialog_close()  # Führt Callback aus und schließt
            else:
                messagebox.showerror("Fehler beim Speichern", msg, parent=self)
        except Exception as e:
            messagebox.showerror("Fehler", f"Speichern fehlgeschlagen: {e}", parent=self)