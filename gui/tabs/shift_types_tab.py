# gui/tabs/shift_types_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
# KORREKTUR: Cache-Clear Funktionen importieren
from database.db_shifts import (get_all_shift_types, add_shift_type,
                                update_shift_type, delete_shift_type,
                                clear_shift_types_cache, clear_shift_order_cache)
from gui.dialogs.shift_type_dialog import ShiftTypeDialog


class ShiftTypesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        # --- NEU: Dictionary zum Speichern der geladenen Daten ---
        self.shift_types_data = {}
        # ---------------------------------------------------------

        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill='both', padx=10, pady=10)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=5)

        ttk.Button(button_frame, text="Neue Schichtart", command=self.add_new_shift_type).pack(side='left')
        ttk.Button(button_frame, text="Schichtart bearbeiten", command=self.edit_shift_type).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Schichtart löschen", command=self.delete_shift_type).pack(side='left')
        # Optional: Refresh-Button, falls Caching Probleme macht
        # ttk.Button(button_frame, text="Aktualisieren", command=self.load_shift_types).pack(side='right')

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(expand=True, fill='both')

        # --- Treeview Konfiguration ---
        self.tree = ttk.Treeview(tree_frame, columns=(
        'name', 'abbreviation', 'start_time', 'end_time', 'hours', 'color', 'check_understaffing'), show='headings')
        self.tree.heading('name', text='Name')
        self.tree.heading('abbreviation', text='Abkürzung')
        self.tree.heading('start_time', text='Startzeit')
        self.tree.heading('end_time', text='Endzeit')
        self.tree.heading('hours', text='Stunden')
        self.tree.heading('color', text='Farbe')
        self.tree.heading('check_understaffing', text='Prüfen?') # Text gekürzt

        # Spaltenbreiten anpassen
        self.tree.column('name', width=180, stretch=tk.YES)
        self.tree.column('abbreviation', width=80, anchor='center')
        self.tree.column('start_time', width=80, anchor='center')
        self.tree.column('end_time', width=80, anchor='center')
        self.tree.column('hours', width=60, anchor='e') # rechtsbündig
        self.tree.column('color', width=80, anchor='center')
        # KORREKTUR: Spalte 'check_understaffing' zentriert und feste Breite
        self.tree.column('check_understaffing', width=60, anchor='center', stretch=tk.NO)

        # Scrollbar
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side='left', expand=True, fill='both')

        # --- NEU: Klick-Event für Checkboxen ---
        self.tree.bind("<Button-1>", self.on_tree_click)
        # --- ENDE NEU ---

        self.load_shift_types()


    def load_shift_types(self):
        """Lädt Schichtarten aus der DB und zeigt sie im Treeview an."""
        # Treeview leeren
        for i in self.tree.get_children():
            self.tree.delete(i)
        # Lokalen Datenspeicher leeren
        self.shift_types_data.clear()

        try:
            # Daten aus DB holen (nutzt Cache, falls vorhanden)
            shift_types = get_all_shift_types()
            if not shift_types:
                # Optional: Meldung anzeigen, wenn keine Schichtarten gefunden wurden
                # self.tree.insert('', 'end', text="Keine Schichtarten gefunden.")
                return

            # Daten verarbeiten und anzeigen
            for st in shift_types:
                # KORREKTUR: Boolean-Wert (0 oder 1) in Symbol umwandeln
                is_checked_db = st.get('check_for_understaffing', 0) # Default 0 falls fehlt
                check_symbol = "✔" if is_checked_db else "☐"

                # Daten für spätere Referenz speichern (wichtig für Klick-Handler)
                shift_id = st['id']
                self.shift_types_data[str(shift_id)] = st # ID als String-Key verwenden

                # Werte-Tupel für die Zeile erstellen
                values = (
                    st.get('name', ''),
                    st.get('abbreviation', ''),
                    st.get('start_time', '') or '', # Zeige '' statt None
                    st.get('end_time', '') or '',   # Zeige '' statt None
                    st.get('hours', 0.0),
                    st.get('color', '#FFFFFF'),
                    check_symbol # Symbol statt "Ja"/"Nein"
                )
                # Zeile in Treeview einfügen, ID als iid verwenden
                self.tree.insert('', 'end', values=values, iid=shift_id)

        except Exception as e:
             print(f"Fehler in load_shift_types: {e}")
             messagebox.showerror("Ladefehler", f"Konnte Schichtarten nicht laden:\n{e}", parent=self)


    # --- NEU: Klick-Event Handler ---
    def on_tree_click(self, event):
        """Behandelt Klicks auf die Checkbox-Spalte im Treeview."""
        region = self.tree.identify_region(event.x, event.y)
        column_id = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y) # Das ist die iid (Datenbank-ID)

        # Nur reagieren, wenn auf eine Zelle geklickt wurde UND es die Check-Spalte ist
        # '#7' entspricht der 7. Spalte ('check_understaffing')
        if region == 'cell' and item_id and column_id == '#7':
            current_symbol = self.tree.set(item_id, 'check_understaffing')
            new_symbol = "☐" if current_symbol == "✔" else "✔"
            new_value_bool = (new_symbol == "✔") # True wenn neuer Haken gesetzt

            # 1. Symbol im Treeview sofort aktualisieren (visuelles Feedback)
            self.tree.set(item_id, 'check_understaffing', new_symbol)

            # 2. Änderung in der Datenbank speichern
            try:
                # Hole die vollständigen Daten der geklickten Schichtart
                shift_data_to_update = self.shift_types_data.get(str(item_id))
                if not shift_data_to_update:
                    print(f"[FEHLER] Schichtdaten für ID {item_id} nicht im lokalen Speicher gefunden!")
                    messagebox.showerror("Interner Fehler", "Konnte die zugehörigen Schichtdaten nicht finden.", parent=self)
                    # Änderung im Treeview rückgängig machen
                    self.tree.set(item_id, 'check_understaffing', current_symbol)
                    return

                # Erstelle Kopie und aktualisiere nur den geänderten Wert
                updated_data = shift_data_to_update.copy()
                updated_data['check_for_understaffing'] = new_value_bool

                # Konvertiere ID zu Integer für die DB-Funktion
                shift_id_int = int(item_id)

                # Rufe die Update-Funktion der Datenbank auf
                success, message = update_shift_type(shift_id_int, updated_data)

                if success:
                    print(f"Check-Status für Schicht ID {item_id} auf {new_value_bool} geändert.")
                    # Update lokale Daten (optional, aber gut für Konsistenz)
                    self.shift_types_data[str(item_id)]['check_for_understaffing'] = new_value_bool
                    # WICHTIG: Caches leeren, damit andere Teile des Programms die Änderung sehen
                    clear_shift_types_cache()
                    clear_shift_order_cache()
                    # Optional: Benachrichtige andere Tabs (z.B. Schichtplan braucht evtl. Refresh)
                    # self.app.refresh_all_tabs() # Kann langsam sein, evtl. gezielter?
                    self.app.refresh_specific_tab("Schichtplan") # Aktualisiert nur den Schichtplan, falls geladen
                else:
                    # Fehler beim Speichern -> Änderung im Treeview rückgängig machen
                    messagebox.showerror("Speicherfehler", f"Konnte Änderung nicht speichern:\n{message}", parent=self)
                    self.tree.set(item_id, 'check_understaffing', current_symbol)

            except ValueError:
                 messagebox.showerror("Fehler", "Ungültige Schicht-ID.", parent=self)
                 self.tree.set(item_id, 'check_understaffing', current_symbol)
            except Exception as e:
                 messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=self)
                 self.tree.set(item_id, 'check_understaffing', current_symbol)

            # Verhindere, dass der Klick auch die Zeile auswählt etc.
            return "break"
    # --- ENDE NEU ---


    def add_new_shift_type(self):
        """Öffnet den Dialog zum Hinzufügen einer neuen Schichtart."""
        dialog = ShiftTypeDialog(self, self.app, is_new=True) # self.app ist das AdminWindow
        # Warte, bis der Dialog geschlossen wird
        self.wait_window(dialog)
        # Prüfe, ob der Dialog mit OK geschlossen wurde (dialog.result enthält Daten)
        if dialog.result:
            try:
                success, message = add_shift_type(dialog.result)
                if success:
                    # Caches wurden in add_shift_type geleert
                    self.load_shift_types() # Treeview neu laden
                    # App-Cache muss nicht extra geleert werden, da DB-Cache geleert wurde
                    # self.app.load_shift_types() # Veraltet / Nicht nötig
                    self.app.refresh_all_tabs() # Andere Tabs informieren
                else:
                    messagebox.showerror("Fehler beim Hinzufügen", message, parent=self)
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Schichtart nicht hinzufügen:\n{e}", parent=self)


    def edit_shift_type(self):
        """Öffnet den Dialog zum Bearbeiten der ausgewählten Schichtart."""
        selected_items = self.tree.selection() # Gibt eine Liste von IDs zurück
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Bearbeiten aus.", parent=self)
            return
        # Nimm das erste ausgewählte Element (normalerweise nur eins)
        shift_id_str = selected_items[0]

        # Hole die Daten aus unserem lokalen Speicher statt aus dem Treeview
        initial_shift_data = self.shift_types_data.get(shift_id_str)

        if not initial_shift_data:
             messagebox.showerror("Fehler", "Konnte die Daten für die ausgewählte Schicht nicht finden.", parent=self)
             self.load_shift_types() # Lade neu, um Inkonsistenzen zu beheben
             return

        # ID muss im initial_data für den Dialog enthalten sein
        initial_shift_data['id'] = int(shift_id_str) # Stelle sicher, dass ID drin ist

        # Öffne den Dialog mit den initialen Daten
        dialog = ShiftTypeDialog(self, self.app, is_new=False, initial_data=initial_shift_data)
        self.wait_window(dialog)

        # Wenn der Dialog mit OK geschlossen wurde
        if dialog.result:
            try:
                # ID aus den Ergebnisdaten entfernen, da sie separat übergeben wird
                shift_id_to_update = dialog.result.pop('id')
                success, message = update_shift_type(shift_id_to_update, dialog.result)
                if success:
                    # Caches wurden in update_shift_type geleert
                    self.load_shift_types() # Treeview neu laden
                    # self.app.load_shift_types() # Veraltet / Nicht nötig
                    self.app.refresh_all_tabs() # Andere Tabs informieren
                else:
                    messagebox.showerror("Fehler beim Bearbeiten", message, parent=self)
            except KeyError:
                 messagebox.showerror("Fehler", "ID fehlt in den Ergebnisdaten des Dialogs.", parent=self)
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Schichtart nicht bearbeiten:\n{e}", parent=self)


    def delete_shift_type(self):
        """Löscht die ausgewählte Schichtart."""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Löschen aus.", parent=self)
            return
        shift_id_str = selected_items[0]

        # Hole Namen zur Bestätigung
        shift_name = self.shift_types_data.get(shift_id_str, {}).get('name', f"ID {shift_id_str}")

        if messagebox.askyesno("Löschen bestätigen",
                               f"Sind Sie sicher, dass Sie die Schichtart '{shift_name}' löschen möchten?\n"
                               f"Alle Einträge dieser Schicht im Plan bleiben bestehen, können aber Fehler verursachen.",
                               parent=self, icon='warning'):
            try:
                success, message = delete_shift_type(int(shift_id_str))
                if success:
                    # Caches wurden in delete_shift_type geleert
                    self.load_shift_types() # Treeview neu laden
                    # self.app.load_shift_types() # Veraltet / Nicht nötig
                    self.app.refresh_all_tabs() # Andere Tabs informieren
                else:
                    messagebox.showerror("Fehler beim Löschen", message, parent=self)
            except ValueError:
                 messagebox.showerror("Fehler", "Ungültige Schicht-ID.", parent=self)
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Schichtart nicht löschen:\n{e}", parent=self)