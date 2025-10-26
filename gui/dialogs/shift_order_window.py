# gui/dialogs/shift_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
# KORREKTUR: save_shift_order erwartet jetzt nur 3 Werte pro Tupel
from database.db_shifts import get_ordered_shift_abbrevs, save_shift_order, clear_shift_order_cache


class ShiftOrderWindow(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        # KORREKTUR: Titel angepasst
        self.title("Schicht-Reihenfolge & Sichtbarkeit anpassen")
        self.geometry("500x600") # Breite reduziert
        self.transient(master)
        self.grab_set()

        self.main_frame = ttk.Frame(self, padding=10)
        self.main_frame.pack(fill='both', expand=True)

        # KORREKTUR: Beschreibung angepasst
        ttk.Label(self.main_frame,
                  text="Ziehen Sie die Schichten in die gewünschte Reihenfolge.\n"
                       "Deaktivieren Sie 'Sichtbar', um eine Schicht im Plan auszublenden.").pack(pady=5)

        # Container für Treeview und Scrollbar
        tree_container = ttk.Frame(self.main_frame)
        tree_container.pack(fill='both', expand=True, pady=10)

        # --- KORREKTUR: Spalte 'Check' entfernt ---
        self.tree = ttk.Treeview(tree_container, columns=('Visible',), show='tree headings') # Nur noch 'Visible'
        self.tree.heading('#0', text='Schichtart (Name - Abkürzung)')
        self.tree.heading('Visible', text='Sichtbar?')
        # self.tree.heading('Check', text='Prüfen?') # Entfernt

        self.tree.column('#0', width=300, stretch=tk.YES)
        self.tree.column('Visible', width=80, anchor='center')
        # self.tree.column('Check', width=80, anchor='center') # Entfernt

        # Scrollbar hinzufügen
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(fill='both', expand=True)
        # --- ENDE KORREKTUR ---

        # Daten laden
        self.load_shifts()

        # Drag & Drop Bindings
        self.tree.bind("<ButtonPress-1>", self.on_press)
        self.tree.bind("<B1-Motion>", self.on_drag)
        self.tree.bind("<ButtonRelease-1>", self.on_release)
        # KORREKTUR: Nur noch Klick auf Sichtbar-Checkbox behandeln
        self.tree.bind("<Button-1>", self.on_tree_click, add='+')

        self.drag_start_item = None
        self.drag_start_y = 0

        btn_frame = ttk.Frame(self.main_frame)
        btn_frame.pack(fill='x', pady=10)

        save_btn = ttk.Button(btn_frame, text="Speichern", command=self.save)
        save_btn.pack(side='right', padx=5)

        cancel_btn = ttk.Button(btn_frame, text="Abbrechen", command=self.destroy)
        cancel_btn.pack(side='right')

    def load_shifts(self):
        # Lösche alte Einträge
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Lade Schichten inkl. versteckter
        # get_ordered_shift_abbrevs liefert jetzt den 'check_for_understaffing'-Wert aus shift_types
        self.shifts_data = get_ordered_shift_abbrevs(include_hidden=True)
        self.shift_map = {shift['abbreviation']: shift for shift in self.shifts_data}

        # Füge Elemente zum Treeview hinzu
        for i, shift in enumerate(self.shifts_data):
            abbrev = shift['abbreviation']
            name = shift.get('name', abbrev)
            display_name = f"{name} - {abbrev}"
            # 'is_visible' kommt weiterhin aus shift_order (oder Default 1)
            is_visible = shift.get('is_visible', 1)
            # 'check_staffing' wird hier nicht mehr benötigt

            # Füge Item ein, speichere Abkürzung in 'tags'
            item_id = self.tree.insert('', tk.END, text=display_name, tags=(abbrev,))

            # Setze Checkbox-Wert für Sichtbarkeit
            self.tree.set(item_id, 'Visible', "✔" if is_visible else "☐")
            # Setzen für 'Check' entfällt

    # KORREKTUR: Klick-Handler angepasst (nur noch für Spalte 'Visible')
    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        column_id = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)

        if region == 'cell' and item_id:
            # Spaltenindex: #1 ist 'Visible'
            if column_id == '#1': # Sichtbar-Spalte
                current_value = self.tree.set(item_id, 'Visible')
                new_value = "☐" if current_value == "✔" else "✔"
                self.tree.set(item_id, 'Visible', new_value)
            # Klick auf andere Spalten oder den Namen wird ignoriert

    # --- Drag & Drop Methoden (on_press, on_drag, on_release) bleiben unverändert ---
    def on_press(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == 'tree':
            self.drag_start_item = self.tree.identify_row(event.y)
            self.drag_start_y = event.y
            if self.drag_start_item:
                 self.tree.selection_set(self.drag_start_item)
        else:
             self.drag_start_item = None

    def on_drag(self, event):
        if not self.drag_start_item: return
        item_over = self.tree.identify_row(event.y)
        if item_over and item_over != self.drag_start_item:
             self.tree.move(self.drag_start_item, self.tree.parent(item_over), self.tree.index(item_over))
             self.drag_start_y = event.y

    def on_release(self, event):
        self.drag_start_item = None
    # --- Ende Drag & Drop ---


    def save(self):
        new_order_data = []
        for i, item_id in enumerate(self.tree.get_children()):
            abbrev_tuple = self.tree.item(item_id, 'tags')
            if not abbrev_tuple: continue
            abbrev = abbrev_tuple[0]

            is_visible_text = self.tree.set(item_id, 'Visible')
            # 'check_staffing_text' wird nicht mehr ausgelesen

            is_visible = 1 if is_visible_text == "✔" else 0
            # 'check_staffing' wird nicht mehr gespeichert

            # --- KORREKTUR: Tupel hat nur noch 3 Elemente ---
            # (abbreviation, sort_order, is_visible)
            new_order_data.append((abbrev, i, is_visible))
            # --- ENDE KORREKTUR ---

        # Speichere die neue Reihenfolge und Sichtbarkeit in der DB
        # Die Funktion save_shift_order erwartet jetzt nur noch 3 Werte
        success, message = save_shift_order(new_order_data)
        if success:
            clear_shift_order_cache()
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", f"Reihenfolge konnte nicht gespeichert werden:\n{message}", parent=self)