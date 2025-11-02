# gui/dialogs/holiday_settings_window.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkcalendar import DateEntry
from datetime import date
from ..holiday_manager import HolidayManager


class HolidaySettingsWindow(tk.Toplevel):
    def __init__(self, master, app, year=None, callback=None):
        super().__init__(master)
        self.app = app
        self.callback = callback
        self.title("Feiertage verwalten")
        self.geometry("600x450")
        self.transient(master)
        self.grab_set()

        self.all_holidays_data = {}
        self.current_year = str(year if year else date.today().year)

        # --- UI Setup ---
        top_frame = ttk.Frame(self, padding=(10, 10))
        top_frame.pack(fill='x')

        ttk.Label(top_frame, text="Jahr auswählen:").pack(side='left', padx=(0, 10))

        # Generiere Jahresliste (z.B. aktuelles Jahr +/- 5 Jahre)
        start_year = date.today().year - 5
        end_year = date.today().year + 5
        year_list = [str(y) for y in range(start_year, end_year + 1)]

        self.year_var = tk.StringVar(value=self.current_year)
        self.year_combo = ttk.Combobox(top_frame, textvariable=self.year_var, values=year_list, state="readonly",
                                       width=10)
        self.year_combo.pack(side='left')
        self.year_combo.bind("<<ComboboxSelected>>", self.on_year_change)

        # Frame für die Liste
        tree_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        tree_frame.pack(expand=True, fill='both')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Treeview für Feiertage
        self.holiday_tree = ttk.Treeview(tree_frame, columns=("date", "name"), show="headings")
        self.holiday_tree.heading("date", text="Datum")
        self.holiday_tree.heading("name", text="Feiertag")
        self.holiday_tree.column("date", width=120, anchor='w')
        self.holiday_tree.column("name", anchor='w')
        self.holiday_tree.grid(row=0, column=0, sticky='nsew')

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.holiday_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.holiday_tree.configure(yscrollcommand=scrollbar.set)

        # Frame für Buttons
        button_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        button_frame.pack(fill='x')

        ttk.Button(button_frame, text="Neu...", command=self.add_holiday).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Bearbeiten...", command=self.edit_holiday).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Löschen", command=self.delete_holiday, style="Delete.TButton").pack(side='left',
                                                                                                           padx=5)

        ttk.Button(button_frame, text="Schließen", command=self.destroy).pack(side='right', padx=5)

        self.load_holidays()
        self.populate_tree()

    def load_holidays(self):
        """Lädt alle Feiertage aus dem Manager."""
        try:
            # Holt alle Feiertage (der Manager kümmert sich ums Generieren, falls nötig)
            self.all_holidays_data = HolidayManager.get_all_holidays()
            if not self.all_holidays_data:
                print("[HolidaySettings] Warnung: get_all_holidays() gab leere Daten zurück.")
                self.all_holidays_data = {}
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Feiertagsdaten:\n{e}", parent=self)
            self.all_holidays_data = {}

    def populate_tree(self):
        """Füllt den Treeview mit den Daten für das ausgewählte Jahr."""
        for item in self.holiday_tree.get_children():
            self.holiday_tree.delete(item)

        try:
            # Lade die Daten für das ausgewählte Jahr
            year_str = self.year_var.get()
            holidays_for_year = self.all_holidays_data.get(year_str, {})

            # Sortiere die Feiertage nach Datum
            # (holiday_date ist der String "YYYY-MM-DD", holiday_name der Name)
            sorted_holidays = sorted(holidays_for_year.items(), key=lambda x: x[0])

            for holiday_date, holiday_name in sorted_holidays:
                # --- KORREKTUR ---
                # holiday_date IST BEREITS der ISO-String (z.B. "2025-10-03").
                # .isoformat() ist hier falsch, da es ein String ist.
                # Wir verwenden den String direkt als IID (Item ID).
                self.holiday_tree.insert("", tk.END, iid=holiday_date,
                                         values=(holiday_date, holiday_name),
                                         tags=('holiday',))
                # --- ENDE KORREKTUR ---

        except Exception as e:
            print(f"Fehler beim Füllen der Feiertagsliste: {e}")
            messagebox.showerror("Fehler", f"Fehler beim Anzeigen der Feiertage:\n{e}", parent=self)

    def on_year_change(self, event=None):
        """Wird aufgerufen, wenn ein neues Jahr ausgewählt wird."""
        new_year = self.year_var.get()

        # Prüfen, ob das Jahr schon im Cache/DB ist. Wenn nicht, generieren.
        if new_year not in self.all_holidays_data:
            print(f"[HolidaySettings] Lade/Generiere Feiertage für {new_year}...")
            # Hole die Daten für das neue Jahr (löst Generierung im Manager aus)
            HolidayManager.get_holidays_for_year(int(new_year))
            # Lade alle Daten neu, da sie sich geändert haben
            self.load_holidays()

        self.populate_tree()

    def add_holiday(self):
        """Öffnet einen Dialog zum Hinzufügen eines neuen Feiertags."""
        self._open_edit_dialog(None)

    def edit_holiday(self):
        """Öffnet einen Dialog zum Bearbeiten des ausgewählten Feiertags."""
        selected_item = self.holiday_tree.focus()
        if not selected_item:
            messagebox.showwarning("Auswahl fehlt", "Bitte wählen Sie einen Feiertag zum Bearbeiten aus.", parent=self)
            return

        # selected_item ist die IID, die wir als Datums-String ("YYYY-MM-DD") festgelegt haben
        date_str = selected_item
        name = self.holiday_tree.item(selected_item, "values")[1]

        self._open_edit_dialog({"date": date_str, "name": name})

    def _open_edit_dialog(self, holiday_data):
        """Der eigentliche Dialog zum Hinzufügen/Bearbeiten."""
        is_edit = holiday_data is not None
        title = "Feiertag bearbeiten" if is_edit else "Feiertag hinzufügen"

        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(expand=True, fill='both')

        ttk.Label(frame, text="Datum:").grid(row=0, column=0, sticky='w', padx=5, pady=5)

        try:
            default_date = date.fromisoformat(holiday_data["date"]) if is_edit else date.today().replace(
                year=int(self.year_var.get()))
        except (TypeError, ValueError):
            default_date = date.today()

        # DateEntry für die Datumsauswahl
        cal = DateEntry(frame, width=12, background='darkblue', foreground='white', borderwidth=2,
                        year=default_date.year, month=default_date.month, day=default_date.day,
                        date_pattern='y-mm-dd')
        cal.grid(row=0, column=1, sticky='w', padx=5, pady=5)
        # Datum kann nicht bearbeitet werden, wenn es ein Edit ist (Schlüsseländerung)
        if is_edit:
            cal.config(state="disabled")

        ttk.Label(frame, text="Name:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        name_var = tk.StringVar(value=holiday_data["name"] if is_edit else "")
        name_entry = ttk.Entry(frame, textvariable=name_var, width=40)
        name_entry.grid(row=1, column=1, sticky='w', padx=5, pady=5)
        name_entry.focus()

        def on_save():
            date_str = cal.get_date().strftime('%Y-%m-%d')
            name = name_var.get().strip()

            if not name:
                messagebox.showwarning("Eingabe fehlt", "Bitte geben Sie einen Namen für den Feiertag ein.",
                                       parent=dialog)
                return

            year_str = date_str.split('-')[0]

            # Stelle sicher, dass das Jahr in der Hauptdatenstruktur existiert
            if year_str not in self.all_holidays_data:
                self.all_holidays_data[year_str] = {}

            # Füge hinzu oder überschreibe
            self.all_holidays_data[year_str][date_str] = name

            # Speichere die *gesamte* Struktur
            if HolidayManager.save_holidays(self.all_holidays_data):
                messagebox.showinfo("Gespeichert", "Feiertage erfolgreich gespeichert.", parent=dialog)
                self.load_holidays()  # Daten neu laden
                self.populate_tree()  # Baum neu füllen
                if self.callback:
                    self.callback()
                dialog.destroy()
            else:
                messagebox.showerror("Fehler", "Feiertage konnten nicht gespeichert werden.", parent=dialog)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(button_frame, text="Speichern", command=on_save).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side='left', padx=5)

    def delete_holiday(self):
        """Löscht den ausgewählten Feiertag."""
        selected_item = self.holiday_tree.focus()
        if not selected_item:
            messagebox.showwarning("Auswahl fehlt", "Bitte wählen Sie einen Feiertag zum Löschen aus.", parent=self)
            return

        date_str = selected_item
        name = self.holiday_tree.item(selected_item, "values")[1]
        year_str = date_str.split('-')[0]

        if not messagebox.askyesno("Löschen bestätigen",
                                   f"Möchten Sie den Feiertag '{name}' ({date_str}) wirklich löschen?",
                                   icon='warning', parent=self):
            return

        # Aus der Datenstruktur löschen
        if year_str in self.all_holidays_data and date_str in self.all_holidays_data[year_str]:
            del self.all_holidays_data[year_str][date_str]

            # Speichern
            if HolidayManager.save_holidays(self.all_holidays_data):
                messagebox.showinfo("Gelöscht", "Feiertag erfolgreich gelöscht.", parent=self)
                self.load_holidays()  # Daten neu laden
                self.populate_tree()  # Baum neu füllen
                if self.callback:
                    self.callback()
            else:
                messagebox.showerror("Fehler", "Änderung konnte nicht gespeichert werden.", parent=self)
        else:
            messagebox.showerror("Fehler", "Feiertag konnte in der Datenstruktur nicht gefunden werden.", parent=self)

    def destroy(self):
        """Callback beim Schließen des Fensters."""
        if self.callback:
            print("[HolidaySettings] Führe Callback beim Schließen aus (z.B. refresh_all_tabs).")
            self.callback()
        super().destroy()