# gui/dialogs/holiday_settings_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
# os und json sind nicht mehr nötig
from tkcalendar import DateEntry
from gui.holiday_manager import HolidayManager


class EditHolidayDialog(tk.Toplevel):
    def __init__(self, master, year, existing_holidays, holiday_to_edit=None):
        super().__init__(master)
        self.year = year
        self.existing_holidays = existing_holidays
        self.holiday_to_edit = holiday_to_edit
        self.result = None
        is_new = holiday_to_edit is None
        self.title("Neuen Feiertag anlegen" if is_new else "Feiertag bearbeiten")
        self.geometry("400x200")
        self.transient(master)
        self.grab_set()
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)
        ttk.Label(main_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        self.name_var = tk.StringVar()
        name_entry = ttk.Entry(main_frame, textvariable=self.name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(main_frame, text="Datum:").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 10))
        self.date_entry = DateEntry(main_frame, year=self.year, date_pattern='dd.mm.yyyy',
                                    foreground="black", headersforeground="black")
        self.date_entry.grid(row=1, column=1, sticky="ew")
        if not is_new:
            self.name_var.set(holiday_to_edit['name'])
            self.date_entry.set_date(holiday_to_edit['date'])
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_frame.columnconfigure((0, 1), weight=1)
        ttk.Button(button_frame, text="Speichern", command=self.save).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).grid(row=0, column=1, padx=(5, 0), sticky="ew")
        name_entry.focus_set()
        self.bind("<Return>", lambda e: self.save())

    def save(self):
        name = self.name_var.get().strip()
        new_date = self.date_entry.get_date()
        if not name:
            messagebox.showwarning("Eingabe fehlt", "Der Name darf nicht leer sein.", parent=self)
            return
        is_date_taken = new_date in self.existing_holidays and (
                self.holiday_to_edit is None or new_date != self.holiday_to_edit['date'])
        if is_date_taken:
            messagebox.showwarning("Datum belegt",
                                   f"Das Datum {new_date.strftime('%d.%m.%Y')} ist bereits als '{self.existing_holidays[new_date]}' vergeben.",
                                   parent=self)
            return
        self.result = {'name': name, 'date': new_date}
        self.destroy()


class HolidaySettingsWindow(tk.Toplevel):
    def __init__(self, master, year, callback):
        super().__init__(master)
        self.year = year
        self.callback = callback
        self.title(f"Feiertage für {self.year} verwalten")
        self.geometry("550x500")
        self.transient(master)
        self.grab_set()
        self.holidays = HolidayManager.get_holidays_for_year(self.year)
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        columns = ("date", "name")
        self.holiday_tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=15)
        self.holiday_tree.heading("date", text="Datum")
        self.holiday_tree.heading("name", text="Feiertag")
        self.holiday_tree.column("date", width=120, anchor="w")
        self.holiday_tree.column("name", width=300, anchor="w")
        self.holiday_tree.pack(fill="both", expand=True)
        self.holiday_tree.bind("<Double-1>", lambda e: self.edit_holiday())
        self.populate_tree()
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Hinzufügen", command=self.add_holiday).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Bearbeiten", command=self.edit_holiday).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Löschen", command=self.delete_holiday).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Speichern & Schließen", command=self.save_and_close).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right")

    def populate_tree(self):
        for item in self.holiday_tree.get_children():
            self.holiday_tree.delete(item)
        sorted_holidays = sorted(self.holidays.items())
        for holiday_date, name in sorted_holidays:
            self.holiday_tree.insert("", tk.END, iid=holiday_date.isoformat(),
                                     values=(holiday_date.strftime('%d.%m.%Y'), name))

    def add_holiday(self):
        dialog = EditHolidayDialog(self, self.year, self.holidays)
        self.wait_window(dialog)
        if dialog.result:
            self.holidays[dialog.result['date']] = dialog.result['name']
            self.populate_tree()

    def edit_holiday(self):
        selection = self.holiday_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Feiertag zum Bearbeiten aus.", parent=self)
            return
        date_iso = selection[0]
        old_date = date.fromisoformat(date_iso)
        current_name = self.holidays[old_date]
        holiday_to_edit = {'date': old_date, 'name': current_name}
        dialog = EditHolidayDialog(self, self.year, self.holidays, holiday_to_edit)
        self.wait_window(dialog)
        if dialog.result:
            if old_date in self.holidays:
                del self.holidays[old_date]
            self.holidays[dialog.result['date']] = dialog.result['name']
            self.populate_tree()

    def delete_holiday(self):
        selection = self.holiday_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Feiertag zum Löschen aus.", parent=self)
            return
        date_iso = selection[0]
        holiday_date = date.fromisoformat(date_iso)
        if messagebox.askyesno("Bestätigen", f"Möchten Sie '{self.holidays[holiday_date]}' wirklich löschen?",
                               parent=self):
            del self.holidays[holiday_date]
            self.populate_tree()

    def save_and_close(self):
        """Läd alle Feiertage aus der DB, aktualisiert das aktuelle Jahr und speichert alles zurück."""

        # 1. Lade alle vorhandenen Feiertage aus der DB im Rohformat
        all_holidays = HolidayManager.get_holidays_from_db_raw()

        # 2. Füge die Feiertage des aktuellen Jahres hinzu/überschreibe sie (Konvertierung zu ISO-String-Format)
        all_holidays[str(self.year)] = {dt.isoformat(): name for dt, name in self.holidays.items()}

        # 3. Speichere die vollständige Struktur in der DB
        success = HolidayManager.save_holidays(all_holidays)

        if success:
            messagebox.showinfo("Gespeichert", "Die Feiertage wurden erfolgreich gespeichert.", parent=self)
            self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Feiertage konnten nicht gespeichert werden.", parent=self)