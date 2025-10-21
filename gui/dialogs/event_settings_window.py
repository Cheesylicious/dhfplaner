# dialogs/event_settings_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import Calendar, DateEntry
from datetime import datetime
import json

from gui.event_manager import EventManager


# Eigene Klasse für die Datumseingabe mit automatischer Formatierung
class AutoFormatDateEntry(ttk.Frame):
    def __init__(self, master, year_var, add_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self.year_var = year_var
        self.str_var = tk.StringVar()
        self.add_callback = add_callback

        self.entry = ttk.Entry(self, textvariable=self.str_var, width=12)
        self.entry.pack(side="left", fill="x", expand=True)

        self.btn = ttk.Button(self, text="▼", width=2, command=self.open_calendar)
        self.btn.pack(side="left")

        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        if self.add_callback:
            self.entry.bind("<Return>", self._handle_enter_press)

    def _handle_enter_press(self, event=None):
        self._on_focus_out()

        if self.add_callback:
            self.add_callback()

        return "break"

    def _on_key_release(self, event=None):
        if event and event.keysym == 'Return':
            return

        current_text = self.entry.get()
        digits = "".join(filter(str.isdigit, current_text))

        if len(digits) > 4:
            formatted = f"{digits[:2]}.{digits[2:4]}.{digits[4:8]}"
        elif len(digits) > 2:
            formatted = f"{digits[:2]}.{digits[2:4]}"
        else:
            formatted = digits

        cursor_pos = self.entry.index(tk.INSERT)
        self.str_var.set(formatted)
        if len(formatted) > len(current_text):
            self.entry.icursor(cursor_pos + 1)
        else:
            self.entry.icursor(cursor_pos)

    def _on_focus_out(self, event=None):
        current_text = self.entry.get().strip()
        if current_text.endswith('.'):
            current_text = current_text[:-1]

        parts = current_text.split('.')
        if len(parts) == 2 and parts[0] and parts[1]:
            current_year = self.year_var.get()
            formatted = f"{parts[0]}.{parts[1]}.{current_year}"
            self.str_var.set(formatted)

    def get_date(self):
        date_str = self.str_var.get()
        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except ValueError:
            return None

    def set_date(self, date_obj):
        if date_obj:
            self.str_var.set(date_obj.strftime('%d.%m.%Y'))
        else:
            self.str_var.set("")

    def open_calendar(self):
        cal_win = tk.Toplevel(self)
        cal_win.transient(self)
        cal_win.grab_set()

        try:
            current_date = self.get_date() or datetime.now().date()
        except:
            current_date = datetime.now().date()

        cal = Calendar(cal_win, selectmode='day', year=current_date.year, month=current_date.month,
                       day=current_date.day,
                       locale='de_DE')
        cal.pack(pady=10)

        def on_select():
            self.set_date(cal.selection_get())
            cal_win.destroy()

        ttk.Button(cal_win, text="OK", command=on_select).pack(pady=10)


class EventSettingsWindow(tk.Toplevel):
    def __init__(self, master, year, callback):
        super().__init__(master)
        self.callback = callback
        self.transient(master)
        self.grab_set()

        self.year = tk.IntVar(value=year)
        self.title(f"Sondertermine für {self.year.get()}")
        self.geometry("700x600")
        self.minsize(600, 500)

        self.events = EventManager.get_events_for_year(self.year.get())
        self.event_types = ["Quartals Ausbildung", "Schießen"]

        self.setup_ui()
        self.load_events_to_trees()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        year_frame = ttk.Frame(main_frame)
        year_frame.pack(fill="x", pady=5)
        ttk.Button(year_frame, text="<", command=lambda: self.change_year(-1)).pack(side="left")
        self.year_label = ttk.Label(year_frame, text=str(self.year.get()), font=("Segoe UI", 12, "bold"),
                                    anchor="center")
        self.year_label.pack(side="left", expand=True, fill="x")
        ttk.Button(year_frame, text=">", command=lambda: self.change_year(1)).pack(side="right")

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=10)

        self.treeviews = {}
        self.date_entries = {}
        for event_type in self.event_types:
            tab_frame = ttk.Frame(notebook, padding=10)
            notebook.add(tab_frame, text=event_type)
            self.create_event_tab(tab_frame, event_type)

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(10, 0))
        ttk.Button(button_bar, text="Speichern & Schließen", command=self.save_and_close).pack(side="right")
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def create_event_tab(self, parent, event_type):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        tree_frame = ttk.LabelFrame(parent, text="Gespeicherte Termine", padding=10)
        tree_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(tree_frame, columns=("date",), show="headings", selectmode="extended")
        tree.heading("date", text="Datum")
        tree.column("date", anchor="center", width=150)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        tree.bind("<<TreeviewSelect>>", lambda event, et=event_type: self.on_tree_select(event, et))

        self.treeviews[event_type] = tree

        ttk.Button(tree_frame, text="Auswahl löschen", command=lambda: self.remove_event(event_type)).grid(row=1,
                                                                                                           column=0,
                                                                                                           columnspan=2,
                                                                                                           pady=(10, 0),
                                                                                                           sticky="w")

        input_frame = ttk.LabelFrame(parent, text="Termin hinzufügen / bearbeiten", padding=10)
        input_frame.grid(row=1, column=0, sticky="ew")

        ttk.Label(input_frame, text="Datum:").pack(side="left", padx=(0, 5))

        date_entry = AutoFormatDateEntry(input_frame, self.year, add_callback=lambda: self.add_event(event_type))
        date_entry.pack(side="left", padx=5)
        self.date_entries[event_type] = date_entry

        ttk.Button(input_frame, text="Hinzufügen", command=lambda: self.add_event(event_type)).pack(side="left", padx=5)
        ttk.Button(input_frame, text="Auswahl bearbeiten", command=lambda: self.edit_event(event_type)).pack(
            side="left", padx=5)

    def on_tree_select(self, event, event_type):
        tree = self.treeviews[event_type]
        selected_items = tree.selection()
        if len(selected_items) == 1:
            original_date_str = selected_items[0]
            try:
                date_obj = datetime.strptime(original_date_str, '%Y-%m-%d').date()
                self.date_entries[event_type].set_date(date_obj)
            except (ValueError, KeyError):
                pass

    def change_year(self, delta):
        # KORREKTUR: Änderungen vor dem Wechsel speichern
        self._save_current_year_changes()

        new_year = self.year.get() + delta
        self.year.set(new_year)
        self.year_label.config(text=str(new_year))
        self.title(f"Sondertermine für {new_year}")
        self.events = EventManager.get_events_for_year(new_year)
        self.load_events_to_trees()

    def load_events_to_trees(self):
        for tree in self.treeviews.values():
            tree.delete(*tree.get_children())

        sorted_events = sorted(self.events.items())

        for date_str, event_type in sorted_events:
            if event_type in self.treeviews:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                    self.treeviews[event_type].insert("", tk.END, values=(formatted_date,), iid=date_str)
                except ValueError:
                    continue

    def add_event(self, event_type):
        date_entry = self.date_entries[event_type]
        date_obj = date_entry.get_date()
        if not date_obj:
            messagebox.showerror("Ungültiges Datum", "Bitte geben Sie ein gültiges Datum ein.", parent=self)
            return

        if date_obj.year != self.year.get():
            new_year = date_obj.year
            msg = f"Das Datum liegt im Jahr {new_year}. Möchten Sie zu diesem Jahr wechseln und den Termin dort hinzufügen?\n\n(Änderungen für {self.year.get()} werden gespeichert.)"
            if messagebox.askyesno("Jahr wechseln?", msg, parent=self):
                self._save_current_year_changes()
                self.change_year(new_year - self.year.get())
                self.add_event(event_type)
            return

        date_str = date_obj.strftime('%Y-%m-%d')
        if date_str in self.events:
            messagebox.showwarning("Datum existiert",
                                   f"Dieses Datum ist bereits als '{self.events[date_str]}' eingetragen.", parent=self)
            return

        self.events[date_str] = event_type
        self.load_events_to_trees()
        self.date_entries[event_type].set_date(None)

    def edit_event(self, event_type):
        tree = self.treeviews[event_type]
        selected_items = tree.selection()
        if not selected_items or len(selected_items) > 1:
            messagebox.showwarning("Keine/Falsche Auswahl",
                                   "Bitte wählen Sie genau einen Termin zum Bearbeiten aus der Tabelle aus.",
                                   parent=self)
            return

        original_date_str = selected_items[0]
        date_entry = self.date_entries[event_type]
        new_date_obj = date_entry.get_date()
        if not new_date_obj:
            messagebox.showerror("Ungültiges Datum", "Das im Eingabefeld stehende Datum ist ungültig.", parent=self)
            return

        if new_date_obj.year != self.year.get():
            messagebox.showerror("Fehler beim Bearbeiten",
                                 "Das Ändern eines Termins in ein anderes Jahr ist nicht möglich.\n\nBitte löschen Sie den alten Termin und legen Sie ihn im richtigen Jahr neu an.",
                                 parent=self)
            return

        new_date_str = new_date_obj.strftime('%Y-%m-%d')
        if new_date_str != original_date_str and new_date_str in self.events:
            messagebox.showwarning("Datum existiert",
                                   f"Das Zieldatum ist bereits als '{self.events[new_date_str]}' eingetragen.",
                                   parent=self)
            return

        if original_date_str in self.events:
            del self.events[original_date_str]
        self.events[new_date_str] = event_type
        self.load_events_to_trees()
        self.date_entries[event_type].set_date(None)

    def remove_event(self, event_type):
        tree = self.treeviews[event_type]
        selected_items = tree.selection()
        if not selected_items:
            messagebox.showwarning("Keine Auswahl", "Bitte wähle die zu löschenden Termine aus.", parent=self)
            return

        msg = f"Möchtest du {len(selected_items)} Termin(e) wirklich löschen?" if len(
            selected_items) > 1 else "Möchtest du den ausgewählten Termin wirklich löschen?"
        if messagebox.askyesno("Löschen bestätigen", msg, parent=self):
            for item_id in selected_items:
                if item_id in self.events:
                    del self.events[item_id]
            self.load_events_to_trees()
            self.date_entries[event_type].set_date(None)

    def _save_current_year_changes(self):
        all_events_data = EventManager.get_all_events()
        all_events_data[str(self.year.get())] = self.events
        EventManager.save_events(all_events_data)

    def save_and_close(self):
        self._save_current_year_changes()
        messagebox.showinfo("Gespeichert", "Alle Änderungen wurden gespeichert.", parent=self)
        if self.callback:
            self.callback()
        self.destroy()