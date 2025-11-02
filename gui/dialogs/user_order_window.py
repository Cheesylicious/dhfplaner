# gui/dialogs/user_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from database.db_users import get_ordered_users_for_schedule, save_user_order


class UserOrderWindow(tk.Toplevel):
    """
    Fenster zur Verwaltung der Benutzerreihenfolge und Sichtbarkeit
    im Schichtplan mittels Treeview und Pfeil-Buttons.
    """

    def __init__(self, master, callback, for_date):
        super().__init__(master)
        self.master = master
        self.callback = callback
        self.for_date = for_date if for_date else datetime.now()  # Fallback

        self.users_data = {}  # Dictionary: item_id -> user_dict
        # self.user_vars = {} # Wird nicht mehr benötigt, Status direkt im Treeview/users_data

        self.title("Mitarbeiter-Sortierung & Sichtbarkeit")
        # Breite angepasst für Buttons und Checkbox
        self.geometry("600x650")  # Etwas breiter und weniger hoch
        self.transient(master)
        self.grab_set()

        self.setup_ui()
        self.load_users()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(1, weight=1)  # Treeview soll expandieren
        main_frame.columnconfigure(0, weight=1)  # Treeview soll expandieren
        main_frame.columnconfigure(1, weight=0)  # Buttons feste Breite

        ttk.Label(main_frame,
                  text="Sortieren (Pfeile) und Sichtbarkeit im Plan festlegen.\n"
                       "Unsichtbare Mitarbeiter erscheinen nicht im Schichtplan.",
                  justify="center").grid(row=0, column=0, columnspan=2, pady=(5, 10))

        # --- Treeview statt Listbox ---
        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=("name", "visible"), show="headings", selectmode="browse")
        self.tree.heading("name", text="Mitarbeiter")
        self.tree.heading("visible", text="Sichtbar", anchor="center")
        self.tree.column("name", width=300, stretch=tk.YES)
        self.tree.column("visible", width=80, stretch=tk.NO, anchor="center")

        # Scrollbar für Treeview
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Binden des Klick-Events auf die 'visible'-Spalte zum Umschalten
        self.tree.bind("<ButtonRelease-1>", self.toggle_visibility_on_click)
        # --- Ende Treeview ---

        # --- Frame für Pfeil-Buttons ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=1, sticky="ns", padx=(5, 0))

        # Buttons zum Verschieben
        ttk.Button(button_frame, text="▲", command=self.move_up, width=3).pack(pady=5, anchor='n')
        ttk.Button(button_frame, text="▼", command=self.move_down, width=3).pack(pady=5, anchor='n')
        # --- Ende Pfeil-Buttons ---

        # --- Untere Button-Leiste (Speichern, Abbrechen) ---
        bottom_btn_frame = ttk.Frame(main_frame)
        bottom_btn_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        bottom_btn_frame.columnconfigure((0, 1), weight=1)

        ttk.Button(bottom_btn_frame, text="Speichern", command=self.save_order, style="Success.TButton").grid(row=0,
                                                                                                              column=0,
                                                                                                              padx=5,
                                                                                                              sticky="ew")
        ttk.Button(bottom_btn_frame, text="Abbrechen", command=self.destroy).grid(row=0, column=1, padx=5, sticky="ew")
        # --- Ende untere Button-Leiste ---

    def load_users(self):
        """Lädt die Benutzerliste in das Treeview."""
        # Alte Einträge löschen
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.users_data.clear()

        try:
            # Benutzer für das spezifische Datum holen (inkl. versteckter)
            users = get_ordered_users_for_schedule(include_hidden=True, for_date=self.for_date)
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Benutzer: {e}", parent=self)
            return

        if not users:
            # Optional: Meldung im Treeview anzeigen oder Label
            self.tree.insert("", "end", values=("Keine Benutzer für diesen Zeitraum.", ""))
            return

        for user in users:
            user_id = user['id']
            name = f"{user['vorname']} {user['name']}"
            is_visible = user.get('is_visible', 1) == 1
            # Sichtbarkeitsstatus als Text (z.B. ✔/☐ oder Ja/Nein)
            visible_text = "✔" if is_visible else "☐"

            # Benutzer zum Treeview hinzufügen
            item_id = self.tree.insert("", "end", values=(name, visible_text))

            # Benutzerdaten speichern (inkl. Sichtbarkeitsstatus)
            self.users_data[item_id] = {'id': user_id, 'name': name, 'is_visible': is_visible}

            # Optional: Ausgegraute Darstellung für unsichtbare
            if not is_visible:
                self.tree.item(item_id, tags=('hidden',))

        # Tag für ausgegraute Schrift konfigurieren
        self.tree.tag_configure('hidden', foreground='grey')

    def toggle_visibility_on_click(self, event):
        """Schaltet die Sichtbarkeit um, wenn auf die 'Sichtbar'-Spalte geklickt wird."""
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column_id = self.tree.identify_column(event.x)
        # Prüfen, ob die Klick-Koordinate in der 'visible'-Spalte war (#2 ist die ID der 2. Spalte)
        if column_id == "#2":
            item_id = self.tree.identify_row(event.y)
            if item_id in self.users_data:
                # Toggle den Status im Speicher
                current_status = self.users_data[item_id]['is_visible']
                new_status = not current_status
                self.users_data[item_id]['is_visible'] = new_status

                # Aktualisiere die Anzeige im Treeview
                visible_text = "✔" if new_status else "☐"
                self.tree.item(item_id, values=(self.users_data[item_id]['name'], visible_text))

                # Aktualisiere den Tag (für Farbe)
                if new_status:
                    self.tree.item(item_id, tags=())  # Entferne 'hidden' Tag
                else:
                    self.tree.item(item_id, tags=('hidden',))  # Füge 'hidden' Tag hinzu

    def move_up(self):
        """Bewegt das ausgewählte Element eine Position nach oben."""
        selected_items = self.tree.selection()
        if not selected_items:
            return  # Nichts ausgewählt

        item_id = selected_items[0]
        current_index = self.tree.index(item_id)

        if current_index > 0:  # Kann nicht nach oben, wenn schon oben
            self.tree.move(item_id, "", current_index - 1)

    def move_down(self):
        """Bewegt das ausgewählte Element eine Position nach unten."""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        item_id = selected_items[0]
        current_index = self.tree.index(item_id)
        total_items = len(self.tree.get_children())

        if current_index < total_items - 1:  # Kann nicht nach unten, wenn schon unten
            self.tree.move(item_id, "", current_index + 1)

    def save_order(self):
        """Speichert die neue Reihenfolge UND den Sichtbarkeitsstatus."""
        ordered_user_info = []

        # Gehe durch die Elemente in der aktuellen Reihenfolge im Treeview
        for item_id in self.tree.get_children():
            if item_id in self.users_data:  # Ignoriere ggf. Info-Zeilen
                user_info = self.users_data[item_id]
                is_visible = user_info['is_visible']

                ordered_user_info.append({
                    'id': user_info['id'],
                    'is_visible': 1 if is_visible else 0
                })
            else:
                print(f"[WARNUNG] Item ID {item_id} nicht in users_data gefunden beim Speichern.")

        # Überprüfen, ob Daten vorhanden sind
        if not ordered_user_info and self.users_data:  # Nur warnen, wenn ursprünglich User da waren
            messagebox.showwarning("Leere Liste", "Keine gültigen Benutzerdaten zum Speichern gefunden.", parent=self)
            return
        elif not ordered_user_info and not self.users_data:
            # Wenn von Anfang an keine User da waren, ist Speichern okay (leere Liste speichern)
            pass

        # Daten an die Datenbankfunktion übergeben
        success, message = save_user_order(ordered_user_info)

        if success:
            messagebox.showinfo("Gespeichert", message, parent=self)
            if self.callback:
                self.callback()  # Ruft den spezifischen oder globalen Reload-Callback auf
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    # --- Drag & Drop Methoden werden entfernt, da Treeview verwendet wird ---
    # def on_press(self, event): ...
    # def on_drag(self, event): ...
    # def on_release(self, event): ...
    # def update_checkbox_order(self): ...
    # def update_listbox_colors(self): ...