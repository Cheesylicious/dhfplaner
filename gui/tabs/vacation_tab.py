# gui/tabs/vacation_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
from datetime import datetime, date, timedelta

# --- Datenbankfunktionen importieren ---
from database.db_requests import add_vacation_request, get_requests_by_user, cancel_vacation_request_by_user
from database.db_users import get_user_by_id
# ---

from ..request_lock_manager import RequestLockManager

class VacationTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.user_data = app.user_data
        self.selected_request_db_id = None # Speichert die DB-ID des ausgewählten Antrags
        # NEU: Mapping von Treeview Item ID zu Datenbank ID
        self.item_id_to_db_id = {}

        self.setup_ui()
        self.load_data_and_update_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill='both')

        info_frame = ttk.LabelFrame(main_frame, text="Meine Urlaubstage", padding="10")
        info_frame.pack(fill='x', pady=5)
        self.vacation_days_label = ttk.Label(info_frame, text="", font=('Segoe UI', 10))
        self.vacation_days_label.pack()

        request_frame = ttk.LabelFrame(main_frame, text="Neuer Urlaubsantrag", padding="10")
        request_frame.pack(fill='x', pady=10)

        ttk.Label(request_frame, text="Von:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.start_date_entry = DateEntry(request_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd.mm.yyyy')
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(request_frame, text="Bis:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.end_date_entry = DateEntry(request_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='dd.mm.yyyy')
        self.end_date_entry.grid(row=0, column=3, padx=5, pady=5)

        submit_button = ttk.Button(request_frame, text="Antrag stellen", command=self.submit_request)
        submit_button.grid(row=0, column=4, padx=10, pady=5)

        history_frame = ttk.LabelFrame(main_frame, text="Meine Anträge", padding="10")
        history_frame.pack(expand=True, fill='both')

        # --- Treeview Spalten bleiben gleich (nur 4 sichtbare) ---
        self.tree = ttk.Treeview(history_frame, columns=('start_date', 'end_date', 'days', 'status'), show='headings')
        self.tree.heading('start_date', text='Von')
        self.tree.heading('end_date', text='Bis')
        self.tree.heading('days', text='Tage')
        self.tree.heading('status', text='Status')
        self.tree.column('start_date', width=100, anchor='w')
        self.tree.column('end_date', width=100, anchor='w')
        self.tree.column('days', width=60, anchor='center')
        self.tree.column('status', width=100, anchor='w')
        self.tree.tag_configure('Ausstehend', background='#FFF3CD')
        self.tree.tag_configure('Genehmigt', background='#D4EDDA')
        self.tree.tag_configure('Abgelehnt', background='#F8D7DA')
        self.tree.tag_configure('Storniert', background='#E0B0FF', foreground='gray50')
        # ---

        self.tree.pack(side='left', expand=True, fill='both')

        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(main_frame, padding="5 0")
        button_frame.pack(fill='x')
        self.cancel_button = ttk.Button(button_frame, text="Ausgewählten Antrag stornieren", command=self.cancel_selected_request, state='disabled')
        self.cancel_button.pack(side='left', padx=10)

        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

    def on_tree_select(self, event):
        """Wird aufgerufen, wenn ein Eintrag im Treeview ausgewählt wird."""
        selected_item_iid = self.tree.focus() # Holt die *interne* ID des Treeview Eintrags
        if not selected_item_iid:
            self.selected_request_db_id = None
            self.cancel_button.config(state='disabled')
            return

        # --- KORREKTUR: DB ID über das Mapping holen ---
        self.selected_request_db_id = self.item_id_to_db_id.get(selected_item_iid)
        # --- ENDE KORREKTUR ---

        if self.selected_request_db_id is not None:
            # Hole die *sichtbaren* Werte für die Statusprüfung
            item_values = self.tree.item(selected_item_iid, 'values')
            try:
                # --- KORREKTUR: Status ist jetzt an Index 3 der sichtbaren Werte ---
                status = item_values[3]
                if status == 'Ausstehend':
                    self.cancel_button.config(state='normal')
                else:
                    self.cancel_button.config(state='disabled')
                # --- ENDE KORREKTUR ---
            except IndexError:
                # Sollte nicht passieren, wenn 4 Werte eingefügt wurden
                print(f"[FEHLER] Unerwartete Anzahl von Werten für Item {selected_item_iid}: {item_values}")
                self.selected_request_db_id = None
                self.cancel_button.config(state='disabled')
        else:
            # Kein Mapping gefunden (sollte auch nicht passieren)
            print(f"[FEHLER] Keine DB ID für Treeview Item {selected_item_iid} gefunden.")
            self.cancel_button.config(state='disabled')


    def _calculate_workdays(self, start_date_obj, end_date_obj):
        # ... (unverändert) ...
        if start_date_obj > end_date_obj: return 0
        workdays = 0
        current_date = start_date_obj
        one_day = timedelta(days=1)
        while current_date <= end_date_obj:
            weekday = current_date.weekday()
            if weekday != 6 and not self.app.is_holiday(current_date):
                workdays += 1
            current_date += one_day
        return workdays

    def load_data_and_update_ui(self):
        """Lädt alle Anträge, berechnet Summen und aktualisiert Kopfzeile UND Liste."""
        user = get_user_by_id(self.user_data['id'])
        base_total_days = 0
        if user:
            self.user_data['urlaub_gesamt'] = user.get('urlaub_gesamt', 0)
            self.user_data['urlaub_rest'] = user.get('urlaub_rest', 0)
            base_total_days = self.user_data['urlaub_gesamt']

        # --- KORREKTUR: Mapping leeren ---
        self.item_id_to_db_id.clear()
        # ---
        for i in self.tree.get_children():
            self.tree.delete(i)

        total_pending_days = 0
        total_approved_days = 0
        requests = get_requests_by_user(self.user_data['id'])

        for req in requests:
            db_id = req['id']
            start_date_str_db = req.get('start_date')
            end_date_str_db = req.get('end_date')
            status = req.get('status', 'Unbekannt')

            start_date_obj, end_date_obj = None, None
            start_date_str_display, end_date_str_display = "ungültig", "ungültig"
            days_count = 0

            try:
                if isinstance(start_date_str_db, date): start_date_obj = start_date_str_db
                elif isinstance(start_date_str_db, str): start_date_obj = datetime.strptime(start_date_str_db, '%Y-%m-%d').date()

                if isinstance(end_date_str_db, date): end_date_obj = end_date_str_db
                elif isinstance(end_date_str_db, str): end_date_obj = datetime.strptime(end_date_str_db, '%Y-%m-%d').date()

                if start_date_obj and end_date_obj:
                     start_date_str_display = start_date_obj.strftime('%d.%m.%Y')
                     end_date_str_display = end_date_obj.strftime('%d.%m.%Y')
                     days_count = self._calculate_workdays(start_date_obj, end_date_obj)

                     if status == 'Ausstehend': total_pending_days += days_count
                     elif status == 'Genehmigt': total_approved_days += days_count

            except (ValueError, TypeError) as e:
                print(f"Fehler beim Verarbeiten von Datumsangaben für Request ID {db_id}: {e}")

            # --- KORREKTUR: Nur 4 sichtbare Werte einfügen und Mapping speichern ---
            # Füge nur die Daten ein, die den Spalten in 'columns' entsprechen
            item_values_tuple = (
                start_date_str_display,
                end_date_str_display,
                days_count,
                status
            )
            # Füge den Eintrag hinzu und erhalte die interne Treeview Item ID (iid)
            item_iid = self.tree.insert('', 'end', values=item_values_tuple, tags=(status,))
            # Speichere das Mapping von interner ID zu Datenbank ID
            self.item_id_to_db_id[item_iid] = db_id
            # --- ENDE KORREKTUR ---

        current_rest_days = base_total_days - total_approved_days - total_pending_days
        label_text = (
            f"Gesamtanspruch: {base_total_days} Tage | "
            f"Genehmigt: {total_approved_days} Tage | "
            f"Ausstehend: {total_pending_days} Tage | "
            f"Verfügbar: {current_rest_days} Tage"
        )
        self.vacation_days_label.config(text=label_text)

        self.selected_request_db_id = None
        self.cancel_button.config(state='disabled')
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(selection)


    def submit_request(self):
        # ... (unverändert zur vorherigen Version) ...
        start_date = self.start_date_entry.get_date()
        end_date = self.end_date_entry.get_date()
        if start_date > end_date:
            messagebox.showwarning("Ungültiges Datum", "Das Startdatum darf nicht nach dem Enddatum liegen.", parent=self)
            return
        months_to_check = set()
        temp_date = start_date
        while temp_date <= end_date:
            months_to_check.add((temp_date.year, temp_date.month))
            next_month_year = temp_date.year
            next_month = temp_date.month + 1
            if next_month > 12:
                next_month = 1
                next_month_year += 1
            try:
                temp_date = date(next_month_year, next_month, 1)
            except ValueError:
                 print(f"Fehler bei Monatsberechnung in submit_request: {next_month_year}-{next_month}")
                 break
        for year, month in months_to_check:
            if RequestLockManager.is_month_locked(year, month):
                try:
                    month_name_dt = date(year, month, 1)
                    import locale
                    try:
                        locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
                    except locale.Error:
                         try:
                              locale.setlocale(locale.LC_TIME, 'German_Germany.1252')
                         except locale.Error:
                               print("Warnung: Deutsche locale konnte nicht gesetzt werden.")
                               german_months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
                               month_name = german_months[month-1]
                    if 'month_name' not in locals():
                         month_name = month_name_dt.strftime("%B")
                except ImportError:
                     german_months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
                     month_name = german_months[month-1]
                except ValueError:
                    month_name = f"Monat {month}"
                messagebox.showwarning("Anträge gesperrt", f"Der Monat {month_name} {year} ist für Anträge gesperrt.", parent=self)
                return
        if add_vacation_request(self.user_data['id'], start_date, end_date):
            messagebox.showinfo("Erfolg", "Urlaubsantrag wurde erfolgreich gestellt.", parent=self)
            self.load_data_and_update_ui()
        else:
            messagebox.showerror("Fehler", "Der Urlaubsantrag konnte nicht gestellt werden.", parent=self)


    def cancel_selected_request(self):
        # --- KORREKTUR: Prüft jetzt self.selected_request_db_id ---
        if self.selected_request_db_id is None:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie zuerst einen ausstehenden Antrag aus der Liste aus.", parent=self)
            return

        if messagebox.askyesno("Bestätigen", "Möchten Sie den ausgewählten Urlaubsantrag wirklich stornieren?", parent=self):
            # Übergibt die korrekte DB ID
            success, message = cancel_vacation_request_by_user(self.selected_request_db_id, self.user_data['id'])
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_data_and_update_ui()
            else:
                messagebox.showerror("Fehler", message, parent=self)
        # --- ENDE KORREKTUR ---

    def refresh_data(self):
        self.load_data_and_update_ui()