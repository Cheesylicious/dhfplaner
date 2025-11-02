# gui/column_settings_window.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from .column_manager import ColumnManager


class ColumnSettingsWindow(tk.Toplevel):
    """Fenster zur Verwaltung der Spalten mit überarbeitetem, klarem Layout."""

    def __init__(self, master, admin_window):
        super().__init__(master)
        self.admin_window = admin_window

        self.title("Spalteneinstellungen anpassen")
        self.geometry("600x450")  # Etwas breiter für bessere Übersicht
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        self.config = ColumnManager.load_config()
        self.all_columns = self.config.get('all_columns', {})

        # --- Haupt-Container für die Listen und Pfeil-Buttons ---
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="both", expand=True)

        # --- Linke Seite: Sichtbare Spalten ---
        left_frame = ttk.LabelFrame(top_frame, text="Sichtbare Spalten")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.visible_list = tk.Listbox(left_frame, selectmode="single", exportselection=False)
        self.visible_list.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Mittlere Buttons zum Verschieben ---
        middle_button_frame = ttk.Frame(top_frame)
        middle_button_frame.pack(side="left", fill="y", padx=5)
        ttk.Button(middle_button_frame, text=">>", width=4, command=self.move_to_hidden).pack(pady=5)
        ttk.Button(middle_button_frame, text="<<", width=4, command=self.move_to_visible).pack(pady=5)
        ttk.Button(middle_button_frame, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(pady=(20, 5))
        ttk.Button(middle_button_frame, text="↓ Runter", command=lambda: self.move_item(1)).pack(pady=5)

        # --- Rechte Seite: Ausgeblendete Spalten ---
        right_frame = ttk.LabelFrame(top_frame, text="Ausgeblendete Spalten")
        right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.hidden_list = tk.Listbox(right_frame, selectmode="single", exportselection=False)
        self.hidden_list.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Untere Button-Leiste für Aktionen ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(10, 0))

        # Container für die linken Buttons (+, -)
        left_bottom_frame = ttk.Frame(bottom_frame)
        left_bottom_frame.pack(side="left")
        ttk.Button(left_bottom_frame, text="+ Spalte hinzufügen", command=self.add_new_column).pack(side="left")
        ttk.Button(left_bottom_frame, text="- Spalte löschen", command=self.delete_selected_column).pack(side="left",
                                                                                                         padx=5)

        # Container für die rechten Buttons (Speichern, Abbrechen)
        right_bottom_frame = ttk.Frame(bottom_frame)
        right_bottom_frame.pack(side="right")
        ttk.Button(right_bottom_frame, text="Speichern & Schließen", command=self.save_and_close).pack(side="left")
        ttk.Button(right_bottom_frame, text="Abbrechen", command=self.destroy).pack(side="left", padx=5)

        self.populate_lists()

    def populate_lists(self):
        self.visible_list.delete(0, tk.END)
        self.hidden_list.delete(0, tk.END)
        visible_keys = self.config.get('visible', [])
        for key in visible_keys:
            self.visible_list.insert(tk.END, self.all_columns.get(key, key))
        for key, name in self.all_columns.items():
            if key not in visible_keys:
                self.hidden_list.insert(tk.END, name)

    def add_new_column(self):
        new_name = simpledialog.askstring("Neue Spalte", "Wie soll die neue Spalte heißen?", parent=self)
        if new_name and new_name.strip():
            success, message = ColumnManager.add_column(new_name.strip())
            if success:
                self.config = ColumnManager.load_config()
                self.all_columns = self.config.get('all_columns', {})
                self.populate_lists()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def delete_selected_column(self):
        selected_text, from_list = None, None
        if self.visible_list.curselection():
            selected_text = self.visible_list.get(self.visible_list.curselection()[0])
        elif self.hidden_list.curselection():
            selected_text = self.hidden_list.get(self.hidden_list.curselection()[0])

        if not selected_text:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Spalte zum Löschen aus.", parent=self)
            return

        name_to_key_map = {v: k for k, v in self.all_columns.items()}
        key_to_delete = name_to_key_map.get(selected_text)

        if not key_to_delete:
            messagebox.showerror("Fehler", "Interner Fehler: Spaltenschlüssel nicht gefunden.", parent=self)
            return

        if messagebox.askyesno("Bestätigen", f"Möchten Sie die Spalte '{selected_text}' wirklich endgültig löschen?",
                               parent=self):
            success, message = ColumnManager.delete_column(key_to_delete)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.config = ColumnManager.load_config()
                self.all_columns = self.config.get('all_columns', {})
                self.populate_lists()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def move_to_hidden(self):
        selection = self.visible_list.curselection()
        if not selection: return
        item_text = self.visible_list.get(selection[0])
        name_to_key_map = {v: k for k, v in self.all_columns.items()}
        key = name_to_key_map.get(item_text)
        if key in ColumnManager.CORE_COLUMNS:
            messagebox.showwarning("Aktion nicht erlaubt", f"Die Spalte '{item_text}' kann nicht ausgeblendet werden.",
                                   parent=self)
            return
        self.visible_list.delete(selection[0])
        self.hidden_list.insert(tk.END, item_text)

    def move_to_visible(self):
        selection = self.hidden_list.curselection()
        if not selection: return
        item_text = self.hidden_list.get(selection[0])
        self.hidden_list.delete(selection[0])
        self.visible_list.insert(tk.END, item_text)

    def move_item(self, direction):
        selection = self.visible_list.curselection()
        if not selection: return
        idx = selection[0]
        if not (0 <= idx + direction < self.visible_list.size()): return
        item_text = self.visible_list.get(idx)
        self.visible_list.delete(idx)
        self.visible_list.insert(idx + direction, item_text)
        self.visible_list.selection_set(idx + direction)
        self.visible_list.activate(idx + direction)

    def save_and_close(self):
        visible_display_names = self.visible_list.get(0, tk.END)
        name_to_key_map = {v: k for k, v in self.all_columns.items()}
        visible_keys_in_order = [name_to_key_map[name] for name in visible_display_names]
        ColumnManager.save_config(self.all_columns, visible_keys_in_order)
        messagebox.showinfo("Gespeichert", "Spalteneinstellungen wurden gespeichert.", parent=self)
        self.admin_window.refresh_user_management_tab()
        self.destroy()