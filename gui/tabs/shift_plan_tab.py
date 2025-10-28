# gui/tabs/shift_plan_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date, timedelta, datetime, time  # time importiert
import calendar
import threading
from collections import defaultdict
import math

# Importiere die Helfer-Module
from database.db_users import get_ordered_users_for_schedule
from gui.request_lock_manager import RequestLockManager
from gui.shift_plan_data_manager import ShiftPlanDataManager
from gui.shift_plan_renderer import ShiftPlanRenderer
from gui.shift_plan_actions import ShiftPlanActionHandler
from database.db_shifts import get_ordered_shift_abbrevs, \
    delete_all_shifts_for_month  # delete_all_shifts_for_month muss für abwärtskompatibilität bleiben, wird aber nicht direkt hier aufgerufen
from ..dialogs.rejection_reason_dialog import RejectionReasonDialog
from ..dialogs.generator_settings_window import \
    GeneratorSettingsWindow  # Import des Generator-Einstellungsfensters
# --- Import des Generators ---
from gui.shift_plan_generator import ShiftPlanGenerator


class ShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        # Erstellt die DataManager Instanz, die später übergeben wird
        self.data_manager = ShiftPlanDataManager(app)
        self.action_handler = ShiftPlanActionHandler(self, app, self, None)
        self.renderer = ShiftPlanRenderer(self, app, self.data_manager, self.action_handler)
        self.action_handler.renderer = self.renderer
        self.grid_widgets = self.renderer.grid_widgets
        self.violation_cells = self.data_manager.violation_cells
        self._menu_item_cache = self._prepare_shift_menu_items()
        self.progress_frame = None
        self.progress_bar = None
        self.status_label = None
        self.generate_24h_var = tk.BooleanVar(value=False)
        self.setup_ui()
        self.renderer.set_plan_grid_frame(self.plan_grid_frame)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def _prepare_shift_menu_items(self):
        # (unverändert)
        all_abbrevs = list(self.app.shift_types_data.keys())
        menu_config = {}
        if self.action_handler:
            menu_config = self.action_handler._menu_config_cache
        else:
            print("[WARNUNG] ActionHandler nicht bereit für Menü-Vorbereitung.")
        shift_frequency = self.app.shift_frequency
        sorted_abbrevs = sorted(all_abbrevs, key=lambda s: shift_frequency.get(s, 0), reverse=True)
        prepared_items = []
        for abbrev in sorted_abbrevs:
            if menu_config.get(abbrev, True):
                shift_info = self.app.shift_types_data.get(abbrev)
                if shift_info:
                    name = shift_info.get('name', abbrev);
                    count = shift_frequency.get(abbrev, 0)
                    label_text = f"{abbrev} ({name})" + (f"  (Bisher {count}x)" if count > 0 else "")
                    prepared_items.append((abbrev, label_text))
        return prepared_items

    def setup_ui(self):
        # (angepasst: month_label wird klickbar gemacht)
        main_view_container = ttk.Frame(self, padding="10");
        main_view_container.pack(fill="both", expand=True)
        nav_frame = ttk.Frame(main_view_container);
        nav_frame.pack(fill="x", pady=(0, 10))
        left_nav_frame = ttk.Frame(nav_frame);
        left_nav_frame.pack(side="left")
        ttk.Button(left_nav_frame, text="< Voriger Monat", command=self.show_previous_month).pack(side="left")
        ttk.Button(left_nav_frame, text="📄 Drucken", command=self.print_shift_plan).pack(side="left", padx=(20, 5))
        ttk.Button(left_nav_frame, text="Schichtplan Löschen !!!", command=self._on_delete_month).pack(side="left",
                                                                                                       padx=5)
        ttk.Separator(left_nav_frame, orient='vertical').pack(side='left', fill='y', padx=(10, 5))

        # Schichtplan generieren Button
        ttk.Button(left_nav_frame, text="Schichtplan generieren", command=self._on_generate_plan).pack(side="left",
                                                                                                       padx=5)

        # Planungsassistent-Einstellungen Button
        ttk.Button(left_nav_frame, text="Planungsassistent-Einstellungen", command=self._open_generator_settings).pack(
            side="left", padx=5)

        # 24er Checkbox (besteht weiterhin an dieser Stelle)
        ttk.Checkbutton(left_nav_frame, text="24er?", variable=self.generate_24h_var, state="disabled").pack(
            side="left")

        self.month_label_var = tk.StringVar()
        month_label_frame = ttk.Frame(nav_frame);
        month_label_frame.pack(side="left", expand=True, fill="x")

        # --- ANPASSUNG: Monatslabel klickbar machen ---
        self.month_label = ttk.Label(month_label_frame, textvariable=self.month_label_var,
                                     font=("Segoe UI", 14, "bold"),
                                     anchor="center", cursor="hand2")  # cursor="hand2" als visueller Hinweis
        self.month_label.pack()
        # Bindet den Linksklick an die neue Methode zur Monatsauswahl
        self.month_label.bind("<Button-1>", self._on_month_label_click)
        # ---------------------------------------------

        self.lock_status_label = ttk.Label(month_label_frame, text="", font=("Segoe UI", 10, "italic"),
                                           anchor="center");
        self.lock_status_label.pack()
        ttk.Button(nav_frame, text="Nächster Monat >", command=self.show_next_month).pack(side="right")
        grid_container_frame = ttk.Frame(main_view_container);
        grid_container_frame.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(grid_container_frame, orient="vertical");
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal");
        hsb.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=vsb.set, xscrollcommand=hsb.set,
                                highlightthickness=0);
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self.canvas.yview);
        hsb.config(command=self.canvas.xview)
        self.inner_frame = ttk.Frame(self.canvas);
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")
        self.plan_grid_frame = ttk.Frame(self.inner_frame);
        self.plan_grid_frame.pack(fill="both", expand=True)

        def _configure_inner_frame(event): self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event): self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame);
        self.inner_frame.bind('<Configure>', _configure_scrollregion)
        footer_frame = ttk.Frame(main_view_container);
        footer_frame.pack(fill="x", pady=(10, 0))
        check_frame = ttk.Frame(footer_frame);
        check_frame.pack(side="left")
        ttk.Button(check_frame, text="Schichtplan Prüfen", command=self.check_understaffing).pack(side="left", padx=5)
        ttk.Button(check_frame, text="Leeren", command=self.clear_understaffing_results).pack(side="left", padx=5)
        self.lock_button = ttk.Button(footer_frame, text="", command=self.toggle_month_lock);
        self.lock_button.pack(side="right", padx=5)
        self.understaffing_result_frame = ttk.Frame(main_view_container, padding="10")

    # --- KORREKTUR: DataManager an den Dialog übergeben ---
    def _open_generator_settings(self):
        """Öffnet das Dialogfenster für die Planungsassistent-Einstellungen (Generator)."""
        # Übergibt self.app, self (als parent) UND die Instanz des DataManagers
        GeneratorSettingsWindow(self.app, self, self.data_manager)

    # --- ENDE KORREKTUR ---

    def _on_month_label_click(self, event):
        """Behandelt den Klick auf das Monatslabel, um einen Dialog zur Auswahl des Monats zu öffnen."""
        self._show_month_chooser_dialog()

    def _show_month_chooser_dialog(self):
        """Zeigt einen Toplevel-Dialog zur schnellen Auswahl eines Monats an."""
        dialog = tk.Toplevel(self)
        dialog.title("Monatsauswahl")
        # Macht das Hauptfenster zum Parent, um den Fokus zu kontrollieren
        # self.master.master ist wahrscheinlich die Hauptanwendung (Admin/UserWindow)
        dialog.transient(self.master.master)
        dialog.grab_set()  # Modalität erzwingen
        dialog.focus_set()

        # Aktuelles Datum holen
        current_date = self.app.current_display_date
        current_year = current_date.year
        current_month = current_date.month

        # Monatsnamen in deutscher Reihenfolge
        month_names_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                          "August", "September", "Oktober", "November", "Dezember"]

        # Jahre: Von 5 Jahre in der Vergangenheit bis 5 Jahre in der Zukunft (innovativ: keine unnötigen Abfragen)
        start_year = date.today().year - 5
        end_year = date.today().year + 5
        years = [str(y) for y in range(start_year, end_year + 1)]

        # Variabeln für die Auswahl
        selected_month_var = tk.StringVar(value=month_names_de[current_month - 1])
        selected_year_var = tk.StringVar(value=str(current_year))

        # Monat-Combobox
        ttk.Label(dialog, text="Monat auswählen:").pack(padx=10, pady=(10, 0))
        month_combo = ttk.Combobox(dialog, textvariable=selected_month_var, values=month_names_de, state="readonly",
                                   width=15)
        month_combo.pack(padx=10, pady=(0, 10))

        # Jahr-Combobox
        ttk.Label(dialog, text="Jahr auswählen:").pack(padx=10, pady=(10, 0))
        year_combo = ttk.Combobox(dialog, textvariable=selected_year_var, values=years, state="readonly", width=15)
        year_combo.pack(padx=10, pady=(0, 10))

        def on_ok():
            """Verarbeitet die Auswahl und wechselt zum gewählten Monat."""
            try:
                # Monatsindex (0-11) + 1 für den tatsächlichen Monat (1-12)
                new_month_index = month_names_de.index(selected_month_var.get())
                new_month = new_month_index + 1
                new_year = int(selected_year_var.get())

                # Setze das neue Anzeigedatum
                # Wir stellen sicher, dass das Datum immer der 1. des Monats ist.
                new_date = date(new_year, new_month, 1)

                # Wenn sich das Datum geändert hat
                if new_date.year != current_date.year or new_date.month != current_date.month:
                    self.app.current_display_date = new_date

                    # Prüfe, ob das Jahr gewechselt hat, um Feiertage etc. neu zu laden
                    if current_year != new_year:
                        if hasattr(self.app, '_load_holidays_for_year'): self.app._load_holidays_for_year(new_year)
                        if hasattr(self.app, '_load_events_for_year'): self.app._load_events_for_year(new_year)

                    # Lade das Gitter für den neuen Monat
                    self.build_shift_plan_grid(new_year, new_month)

                dialog.destroy()

            except ValueError:
                messagebox.showerror("Fehler", "Ungültige Monats- oder Jahresauswahl.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=dialog)

        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=10, pady=10)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=5)
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side="left", padx=5)

        # Zentrieren des Dialogs
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        # Versuche, das Hauptfenster zu finden
        main_window = self.master.master if self.master and self.master.master else self
        x = main_window.winfo_x() + (main_window.winfo_width() // 2) - (width // 2)
        y = main_window.winfo_y() + (main_window.winfo_height() // 2) - (height // 2)
        dialog.geometry(f'+{x}+{y}')

        dialog.wait_window()

    def _create_progress_widgets(self):
        # (unverändert)
        if self.progress_frame and self.progress_frame.winfo_exists(): self.progress_frame.destroy()
        self.progress_frame = ttk.Frame(self.plan_grid_frame)
        self.status_label = ttk.Label(self.progress_frame, text="", font=("Segoe UI", 12));
        self.status_label.pack(pady=(20, 5))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=300, mode='determinate');
        self.progress_bar.pack(pady=5)

    def print_shift_plan(self):
        # (unverändert)
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        month_name = self.month_label_var.get()
        if self.renderer:
            self.renderer.print_shift_plan(year, month, month_name)
        else:
            messagebox.showerror("Fehler", "Druckfunktion nicht bereit.", parent=self)

    def _on_delete_month(self):
        """
        Löscht den Schichtplan nach doppelter Bestätigung.
        DELEGIERUNG: Leitet den Löschvorgang an den ActionHandler weiter,
        der die korrekten Argumente (inkl. user_id) an die DB-Funktion übergibt.
        """
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        month_str = self.month_label_var.get()

        # Die erste Warnung wird durch den ActionHandler überschrieben,
        # da dieser die Details der selektiven Löschung kennt. Hier nur die erste Hürde:
        msg1 = f"Möchten Sie wirklich **ALLE** planbaren Schichteinträge für\n\n{month_str}\n\nlöschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden!"
        if not messagebox.askyesno("WARNUNG: Schichtplan löschen", msg1, icon='warning', parent=self):
            return

        prompt = f"Um den Löschvorgang für {month_str} zu bestätigen, geben Sie bitte 'LÖSCHEN' in das Feld ein und klicken Sie OK."
        confirmation_text = simpledialog.askstring("Endgültige Bestätigung", prompt, parent=self)

        if confirmation_text != "LÖSCHEN":
            messagebox.showinfo("Abgebrochen",
                                "Eingabe war ungültig. Der Löschvorgang wurde abgebrochen.",
                                parent=self)
            return

        # KORRIGIERTER AUFRUF: Delegation an den ActionHandler
        try:
            # Der ActionHandler übernimmt nun die Verantwortung für den Aufruf von
            # delete_all_shifts_for_month(year, month, current_user_id) und die UI-Aktualisierung
            self.action_handler.delete_shift_plan_by_admin(year, month)

            # Hinweis: Die build_shift_plan_grid(year, month) im Erfolgsfall wird vom ActionHandler
            # ausgelöst, um Konsistenz zu wahren.

        except Exception as e:
            messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}",
                                 parent=self);
            import traceback;
            traceback.print_exc()

    # --- Generierungsfunktionen ---
    def _on_generate_plan(self):
        """Startet den Generierungsvorgang für den Schichtplan."""
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        month_str = self.month_label_var.get()

        if RequestLockManager.is_month_locked(year, month):
            messagebox.showwarning("Gesperrt",
                                   f"Der Monat {month_str} ist für Anträge gesperrt.\nEine automatische Generierung ist nicht möglich, bitte erst entsperren.",
                                   parent=self)
            return

        msg = (f"Dies generiert automatisch 'T.', 'N.' und '6' Dienste für {month_str}.\n\n"
               "Bestehende Einträge (auch Urlaub, Wunschfrei etc.) werden NICHT überschrieben.\n"
               "Hundekonflikte, Urlaube, Ruhezeiten und Mindestbesetzung werden berücksichtigt.\n\n"
               "Fortfahren?")
        if not messagebox.askyesno("Schichtplan generieren", msg, parent=self): return

        # UI für Ladebalken vorbereiten
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        if self.renderer: self.renderer.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
        # self.data_manager.violation_cells.clear() # Nicht hier löschen, passiert im DM beim Laden

        self._create_progress_widgets()
        self.progress_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.plan_grid_frame.grid_rowconfigure(0, weight=1);
        self.plan_grid_frame.grid_columnconfigure(0, weight=1)
        self.progress_bar.config(value=0, maximum=100);
        self.status_label.config(text="Starte Generierung...")
        self.update_idletasks()

        # Daten für den Generator sammeln
        try:
            vacation_requests = self.data_manager.processed_vacations
            wunschfrei_requests = self.data_manager.wunschfrei_data
            current_shifts = self.data_manager.shift_schedule_data
            live_shifts_data = {uid: day_data.copy() for uid, day_data in current_shifts.items()}

            first_day_of_target_month = date(year, month, 1)
            date_for_user_filter = datetime.combine(first_day_of_target_month, time(0, 0, 0))
            all_users = get_ordered_users_for_schedule(for_date=date_for_user_filter)

            if not all_users:
                messagebox.showerror("Fehler", f"Keine aktiven Benutzer für die Planung im {month_str} gefunden.",
                                     parent=self)
                if self.progress_frame and self.progress_frame.winfo_exists(): self.progress_frame.grid_forget()
                return
            user_data_map = {user['id']: user for user in all_users}

            holidays_in_month = set()
            if hasattr(self.app, 'holiday_manager'):
                year_holidays = self.app.holiday_manager.holidays.get(year, {})
                for date_str, holiday_name in year_holidays.items():
                    try:
                        h_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        if h_date.year == year and h_date.month == month: holidays_in_month.add(h_date)
                    except ValueError:
                        print(f"[WARNUNG] Ungültiges Feiertagsdatum ignoriert: {date_str}")

        except AttributeError as ae:
            messagebox.showerror("Fehler",
                                 f"Benötigte Plandaten nicht gefunden:\n{ae}\nBitte warten Sie, bis der Plan vollständig geladen ist, oder laden Sie ihn neu.",
                                 parent=self)
            if self.progress_frame and self.progress_frame.winfo_exists(): self.progress_frame.grid_forget()
            return
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Vorbereiten der Generierung:\n{e}", parent=self)
            if self.progress_frame and self.progress_frame.winfo_exists(): self.progress_frame.grid_forget()
            return

        # Generator Instanz erstellen
        generator = ShiftPlanGenerator(
            app=self.app,  # Übergib die Hauptanwendung für Zugriff auf globale Daten wie shift_types
            data_manager=self.data_manager,  # Übergib den DataManager für Zugriff auf Vormonat etc.
            year=year,
            month=month,
            all_users=all_users,
            user_data_map=user_data_map,
            vacation_requests=vacation_requests,
            wunschfrei_requests=wunschfrei_requests,
            live_shifts_data=live_shifts_data,  # Kopie der aktuellen Schichten
            holidays_in_month=holidays_in_month,
            progress_callback=self._safe_update_progress,  # Sicherer Callback für UI-Updates
            completion_callback=self._on_generation_complete  # Callback für das Ende
        )

        # Generator in einem neuen Thread starten
        threading.Thread(target=generator.run_generation, daemon=True).start()

    def _safe_update_progress(self, value, text):
        """ Stellt sicher, dass UI-Updates im Hauptthread erfolgen. """
        self.after(0, lambda v=value, t=text: self._update_progress(v, t))

    def _on_generation_complete(self, success, save_count, error_message):
        """ Callback, der nach Abschluss des Generator-Threads aufgerufen wird. """
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month

        # Ladebalken entfernen
        if self.progress_frame and self.progress_frame.winfo_exists():
            self.progress_frame.grid_forget()
            if self.plan_grid_frame.winfo_exists():
                self.plan_grid_frame.grid_rowconfigure(0, weight=0)
                self.plan_grid_frame.grid_columnconfigure(0, weight=0)

        if success:
            messagebox.showinfo("Erfolg",
                                f"Plan-Generierung abgeschlossen.\n{save_count} Dienste wurden eingetragen.",
                                parent=self)
            # Lade den Plan komplett neu, um alle Änderungen anzuzeigen
            self.build_shift_plan_grid(year, month)
        else:
            messagebox.showerror("Fehler bei Generierung", error_message, parent=self)
            # Lade den Plan trotzdem neu, um Konsistenz zu wahren.
            self.build_shift_plan_grid(year, month)

    def build_shift_plan_grid(self, year, month):
        # (unverändert)
        for widget in self.plan_grid_frame.winfo_children(): widget.destroy()
        if self.renderer: self.renderer.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
        self._create_progress_widgets()
        self.progress_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.plan_grid_frame.grid_rowconfigure(0, weight=1);
        self.plan_grid_frame.grid_columnconfigure(0, weight=1)
        self.progress_bar.config(value=0, maximum=100);
        self.status_label.config(text="Daten werden geladen...")
        self.update_idletasks()
        month_name_german = {"January": "Januar", "February": "Februar", "March": "März", "April": "April",
                             "May": "Mai", "June": "Juni", "July": "Juli", "August": "August", "September": "September",
                             "October": "Oktober", "November": "November", "December": "Dezember"}
        try:
            month_name_en = date(year, month, 1).strftime('%B');
            self.month_label_var.set(
                f"{month_name_german.get(month_name_en, month_name_en)} {year}")
        except ValueError:
            self.month_label_var.set(f"Ungültiger Monat {month}/{year}")
        self.update_lock_status()
        print(f"[ShiftPlanTab] Starte Lade-Thread für {year}-{month}...")
        threading.Thread(target=self._load_data_in_thread, args=(year, month), daemon=True).start()

    def _update_progress(self, step_value, step_text):
        # (unverändert)
        if self.progress_bar and self.progress_bar.winfo_exists(): self.progress_bar.config(value=step_value)
        if self.status_label and self.status_label.winfo_exists(): self.status_label.config(text=step_text)

    def _load_data_in_thread(self, year, month):
        # (unverändert)
        error_message = None
        try:
            self.data_manager.load_and_process_data(year, month, self._safe_update_progress)
            self.after(1, lambda: self._render_grid(year, month))
        except Exception as e:
            print(f"FEHLER beim Laden der Daten im Thread: {e}")
            error_message = f"Fehler beim Laden der Daten:\n{e}"
            self.after(1, lambda msg=error_message: messagebox.showerror("Fehler", msg, parent=self))
            self.after(1, lambda: self.status_label.config(
                text="Laden fehlgeschlagen!") if self.status_label and self.status_label.winfo_exists() else None)

    def _render_grid(self, year, month):
        # (unverändert)
        if not self.renderer: print("[FEHLER] Renderer nicht initialisiert in _render_grid."); return
        if self.progress_bar and self.progress_bar.winfo_exists(): self.progress_bar.config(value=100)
        if self.status_label and self.status_label.winfo_exists(): self.status_label.config(text="Zeichne Gitter...")
        self.update_idletasks()
        self.renderer.build_shift_plan_grid(year, month, data_ready=True)

    def _finalize_ui_after_render(self):
        # (unverändert)
        if self.progress_frame and self.progress_frame.winfo_exists():
            self.progress_frame.grid_forget()
            if self.plan_grid_frame.winfo_exists():
                self.plan_grid_frame.grid_rowconfigure(0, weight=0);
                self.plan_grid_frame.grid_columnconfigure(0, weight=0)
        if self.inner_frame.winfo_exists() and self.canvas.winfo_exists():
            self.inner_frame.update_idletasks();
            self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def refresh_plan(self):
        # (unverändert)
        print("[ShiftPlanTab] Starte synchronen Refresh...")
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        try:
            print("   -> Lade Daten synchron für Refresh...");
            self.data_manager.load_and_process_data(year,
                                                    month);
            print(
                "   -> Daten für Refresh geladen.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Aktualisieren der Plandaten: {e}", parent=self);
            return
        if self.renderer:
            print("   -> Zeichne Grid neu für Refresh...");
            self.renderer.build_shift_plan_grid(year, month,
                                                data_ready=True);
            print(
                "   -> Grid für Refresh neu gezeichnet.")
        else:
            print("[FEHLER] Renderer nicht verfügbar für Refresh.")

    def _finalize_ui_after_render_sync(self):
        # (unverändert)
        if self.inner_frame.winfo_exists() and self.canvas.winfo_exists():
            self.inner_frame.update_idletasks();
            self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def show_previous_month(self):
        # (unverändert)
        self.clear_understaffing_results()
        current_date = self.app.current_display_date;
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        self.app.current_display_date = last_day_of_previous_month
        new_year, new_month = self.app.current_display_date.year, self.app.current_display_date.month
        self.app.current_display_date = self.app.current_display_date.replace(day=1)
        if current_date.year != new_year:
            if hasattr(self.app, '_load_holidays_for_year'): self.app._load_holidays_for_year(new_year)
            if hasattr(self.app, '_load_events_for_year'): self.app._load_events_for_year(new_year)
        self.build_shift_plan_grid(new_year, new_month)

    def show_next_month(self):
        # (unverändert)
        self.clear_understaffing_results()
        current_date = self.app.current_display_date;
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        first_day_of_next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        self.app.current_display_date = first_day_of_next_month
        new_year, new_month = self.app.current_display_date.year, self.app.current_display_date.month
        if current_date.year != new_year:
            if hasattr(self.app, '_load_holidays_for_year'): self.app._load_holidays_for_year(new_year)
            if hasattr(self.app, '_load_events_for_year'): self.app._load_events_for_year(new_year)
        self.build_shift_plan_grid(new_year, new_month)

    def check_understaffing(self):
        # (unverändert)
        self.clear_understaffing_results()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        print("[Check Understaffing] Verwende aktuelle Live-Daten aus dem DataManager...")
        try:
            daily_counts = self.data_manager.daily_counts
        except AttributeError:
            messagebox.showerror("Fehler",
                                 "Tageszählungen (daily_counts) nicht im DataManager gefunden.\nBitte warten Sie, bis der Plan geladen ist.",
                                 parent=self);
            return
        shifts_to_check_data = get_ordered_shift_abbrevs(include_hidden=False)
        shifts_to_check = [item['abbreviation'] for item in shifts_to_check_data if item.get('check_for_understaffing')]
        understaffing_found = False
        self.understaffing_result_frame.pack(fill="x", pady=5, before=self.lock_button.master)
        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day);
            date_str = current_date.strftime('%Y-%m-%d')
            min_staffing = self.data_manager.get_min_staffing_for_date(current_date)
            for shift in shifts_to_check:
                min_req = min_staffing.get(shift)
                if min_req is not None and min_req > 0:
                    count = daily_counts.get(date_str, {}).get(shift, 0)
                    if count < min_req:
                        understaffing_found = True
                        shift_name = self.app.shift_types_data.get(shift, {}).get('name', shift)
                        ttk.Label(self.understaffing_result_frame,
                                  text=f"Unterbesetzung am {current_date.strftime('%d.%m.%Y')}: Schicht '{shift_name}' ({shift}) - {count} von {min_req} anwesend.",
                                  foreground="red", font=("Segoe UI", 10)).pack(anchor="w")
        if not understaffing_found: ttk.Label(self.understaffing_result_frame, text="Keine Unterbesetzungen gefunden.",
                                              foreground="green", font=("Segoe UI", 10, "bold")).pack(anchor="w")

    def clear_understaffing_results(self):
        # (unverändert)
        self.understaffing_result_frame.pack_forget()
        for widget in self.understaffing_result_frame.winfo_children(): widget.destroy()

    def update_lock_status(self):
        # (unverändert)
        year = self.app.current_display_date.year;
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)
        s = ttk.Style();
        s.configure("Lock.TButton", background="red", foreground="white", font=('Segoe UI', 9, 'bold'));
        s.map("Lock.TButton", background=[('active', '#CC0000')]);
        s.configure("Unlock.TButton", background="green", foreground="white", font=('Segoe UI', 9, 'bold'));
        s.map("Unlock.TButton", background=[('active', '#006400')])
        if is_locked:
            self.lock_status_label.config(text="(Für Anträge gesperrt)", foreground="red");
            self.lock_button.config(
                text="Monat entsperren", style="Unlock.TButton")
        else:
            self.lock_status_label.config(text="");
            self.lock_button.config(text="Monat für Anträge sperren",
                                    style="Lock.TButton")

    def toggle_month_lock(self):
        # (unverändert)
        year = self.app.current_display_date.year;
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)
        locks = RequestLockManager.load_locks();
        lock_key = f"{year}-{month:02d}"
        if is_locked:
            if lock_key in locks: del locks[lock_key]
        else:
            locks[lock_key] = True
        if RequestLockManager.save_locks(locks):
            self.update_lock_status()
            if hasattr(self.app, 'refresh_antragssperre_views'): self.app.refresh_antragssperre_views()
        else:
            messagebox.showerror("Fehler", "Der Status konnte nicht gespeichert werden.", parent=self)