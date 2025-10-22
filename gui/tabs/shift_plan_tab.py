# gui/tabs/shift_plan_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta
import calendar
import threading
from collections import defaultdict  # Import hinzugefügt

# Importiere die neuen Helfer-Module
from database.db_users import get_ordered_users_for_schedule
from gui.request_lock_manager import RequestLockManager
from gui.shift_plan_data_manager import ShiftPlanDataManager
from gui.shift_plan_renderer import ShiftPlanRenderer
from gui.shift_plan_actions import ShiftPlanActionHandler
from database.db_shifts import get_ordered_shift_abbrevs  # Import hinzugefügt


class ShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # --- Initialisierung der Helfer-Komponenten (Trennung von Sorgen) ---
        self.data_manager = ShiftPlanDataManager(app)
        self.action_handler = ShiftPlanActionHandler(self, app, self, None)
        self.renderer = ShiftPlanRenderer(self, app, self.data_manager, self.action_handler)
        self.action_handler.renderer = self.renderer

        # Attribute zeigen auf die zentralen Speicherorte in den Managern
        self.grid_widgets = self.renderer.grid_widgets
        self.violation_cells = self.data_manager.violation_cells

        # Speichere die Benutzerreihenfolge auf App-Ebene
        self.app.current_shift_plan_users = get_ordered_users_for_schedule()

        # NEU: Cache für die Menü-Elemente
        self._menu_item_cache = self._prepare_shift_menu_items()

        # NEU: Progressbar und Status-Label sind initial None
        self.progress_frame = None
        self.progress_bar = None
        self.status_label = None

        self.setup_ui()
        self.renderer.set_plan_grid_frame(self.plan_grid_frame)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    # NEUE METHODE: Berechnet alle Menü-Einträge und ihre Labels einmalig beim Start
    def _prepare_shift_menu_items(self):
        """Berechnet alle Schicht-Menüeinträge, sortiert nach Frequenz, und gibt eine Liste von Tupeln zurück."""
        # Wichtig: get_ordered_shift_abbrevs wird hier nur einmalig beim App-Start aufgerufen.
        all_abbrevs = list(self.app.shift_types_data.keys())
        menu_config = self.action_handler._menu_config_cache
        shift_frequency = self.app.shift_frequency

        # Sortiere nach der gecachten Häufigkeit
        sorted_abbrevs = sorted(all_abbrevs, key=lambda s: shift_frequency.get(s, 0), reverse=True)

        prepared_items = []

        for abbrev in sorted_abbrevs:
            if menu_config.get(abbrev, True):
                name = self.app.shift_types_data[abbrev].get('name', abbrev)
                count = shift_frequency.get(abbrev, 0)
                label_text = f"{abbrev} ({name})" + (f"  (Bisher {count}x)" if count > 0 else "")
                prepared_items.append((abbrev, label_text))

        return prepared_items

    def setup_ui(self):
        main_view_container = ttk.Frame(self, padding="10")
        main_view_container.pack(fill="both", expand=True)
        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(nav_frame, text="< Voriger Monat", command=self.show_previous_month).pack(side="left")

        # Drucken delegiert an Renderer
        ttk.Button(nav_frame, text="📄 Drucken", command=self.print_shift_plan).pack(side="left", padx=20)

        self.month_label_var = tk.StringVar()
        month_label_frame = ttk.Frame(nav_frame)
        month_label_frame.pack(side="left", expand=True, fill="x")

        ttk.Label(month_label_frame, textvariable=self.month_label_var, font=("Segoe UI", 14, "bold"),
                  anchor="center").pack()
        self.lock_status_label = ttk.Label(month_label_frame, text="", font=("Segoe UI", 10, "italic"), anchor="center")
        self.lock_status_label.pack()

        ttk.Button(nav_frame, text="Nächster Monat >", command=self.show_next_month).pack(side="right")

        grid_container_frame = ttk.Frame(main_view_container)
        grid_container_frame.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(grid_container_frame, orient="vertical")
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=vsb.set, xscrollcommand=hsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self.canvas.yview)
        hsb.config(command=self.canvas.xview)
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")

        def _configure_inner_frame(event):
            self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame)
        self.inner_frame.bind('<Configure>', _configure_scrollregion)
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)

        footer_frame = ttk.Frame(main_view_container)
        footer_frame.pack(fill="x", pady=10)

        check_frame = ttk.Frame(footer_frame)
        check_frame.pack(side="left")

        ttk.Button(check_frame, text="Schichtplan Prüfen", command=self.check_understaffing).pack(side="left", padx=5)
        ttk.Button(check_frame, text="Leeren", command=self.clear_understaffing_results).pack(side="left", padx=5)

        self.lock_button = ttk.Button(footer_frame, text="", command=self.toggle_month_lock)
        self.lock_button.pack(side="right", padx=5)

        self.understaffing_result_frame = ttk.Frame(main_view_container, padding="10")

    def _create_progress_widgets(self):
        """Erstellt das Fortschritts-Frame und seine Widgets neu."""
        self.progress_frame = ttk.Frame(self.plan_grid_frame)
        self.status_label = ttk.Label(self.progress_frame, text="", font=("Segoe UI", 12))
        self.status_label.pack(pady=(20, 5))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=300, mode='determinate')
        self.progress_bar.pack(pady=5)

    def print_shift_plan(self):
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        month_name = self.month_label_var.get()
        self.renderer.print_shift_plan(year, month, month_name)

    # --- Core Build/Refresh Logic ---
    def build_shift_plan_grid(self, year, month):
        """Startet den Datenladevorgang in einem separaten Thread und initialisiert den Ladebalken."""
        self.app.current_shift_plan_users = get_ordered_users_for_schedule()

        # 1. Entferne ALLE alten Widgets, um den TclError zu vermeiden.
        for widget in self.plan_grid_frame.winfo_children():
            widget.destroy()

        # 2. Erstelle das Fortschritts-Frame NEU
        self._create_progress_widgets()

        # 3. Platziere den Ladebalken mit grid()
        self.progress_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.plan_grid_frame.grid_rowconfigure(0, weight=1)
        self.plan_grid_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar.config(value=0, maximum=100)
        self.status_label.config(text="Daten werden geladen...")

        month_name_german = {"January": "Januar", "February": "Februar", "March": "März", "April": "April",
                             "May": "Mai", "June": "Juni", "July": "Juli", "August": "August",
                             "September": "September", "October": "Oktober", "November": "November",
                             "December": "Dezember"}
        month_name_en = date(year, month, 1).strftime('%B')
        self.month_label_var.set(f"{month_name_german.get(month_name_en, month_name_en)} {year}")

        self.update_lock_status()

        # Thread starten
        threading.Thread(target=self._load_data_in_thread, args=(year, month), daemon=True).start()

    def _update_progress(self, step_value, step_text):
        """Sichere Methode zur Aktualisierung des Ladebalkens aus dem Worker-Thread."""
        self.after(0, lambda: self.progress_bar.config(value=step_value))
        self.after(0, lambda: self.status_label.config(text=step_text))

    def _load_data_in_thread(self, year, month):
        """Führt die zeitraubenden DB-Abrufe im Worker-Thread durch."""
        try:
            # Datenmanager lädt die Daten und ruft den Callback auf (bis 95%)
            self.data_manager.load_and_process_data(year, month, self._update_progress)

            # Nach erfolgreichem Laden: Starte die Render-Funktion im Haupt-Thread
            self.after(1, lambda: self._render_grid(year, month))
        except Exception as e:
            print(f"Fehler beim Laden der Daten im Thread: {e}")
            self.after(1, lambda: messagebox.showerror("Fehler", f"Fehler beim Laden der Daten: {e}", parent=self))
            self.after(1_0, lambda: self.status_label.config(text="Laden fehlgeschlagen. Siehe Konsole für Details."))

    def _render_grid(self, year, month):
        """
        Rendert das Grid im Haupt-Thread.
        """
        # 1. Sofortiges Update auf 100% und Statuswechsel im Haupt-Thread, um Feedback zu geben.
        #    Wir prüfen, ob die Widgets noch existieren, falls der User schon weitergeklickt hat.
        if self.progress_bar and self.progress_bar.winfo_exists():
            self.progress_bar.config(value=100)
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.config(text="Zeichne Gitter: Letzter Schritt (1-2s Verzögerung möglich)...")

        # 2. Starte den blockierenden Render-Vorgang (Chunking-Start)
        self.after(1, lambda: self.renderer.build_shift_plan_grid(year, month, data_ready=True))

    def _finalize_ui_after_render(self):
        """
        Wird vom Renderer aufgerufen, wenn der Zeichenprozess beendet ist.
        Führt das finale UI-Cleanup durch.
        """

        # --- KORREKTUR (Bugfix für Race Condition) ---
        # Prüfen, ob das progress_frame noch existiert, bevor wir
        # versuchen, es zu entfernen. Es könnte durch einen
        # schnellen Klick (z.B. refresh) bereits zerstört worden sein.
        if self.progress_frame and self.progress_frame.winfo_exists():
            self.progress_frame.grid_forget()
        # --- ENDE KORREKTUR ---

        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def refresh_plan(self):
        """Öffentliche Methode zum Aktualisieren des Plans, z.B. nach einer Aktion (synchroner, schneller Refresh)."""
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        self.app.current_shift_plan_users = get_ordered_users_for_schedule()

        # Lade Daten synchron, um den Cache des DM zu aktualisieren
        self.data_manager.load_and_process_data(year, month)

        # Rendern (Synchron)
        for widget in self.plan_grid_frame.winfo_children():
            widget.destroy()

        # Erstelle das Fortschritts-Frame NEU (wird gleich wieder zerstört, aber ist sicherer)
        # self._create_progress_widgets() # Nehmen wir raus, da es beim schnellen Refresh flackert

        self.renderer.build_shift_plan_grid(year, month, data_ready=True)

        # Finalisierung für den synchronen Aufruf (da Renderer hier nicht _finalize_ui_after_render aufruft)
        self._finalize_ui_after_render_sync()

    def _finalize_ui_after_render_sync(self):
        """
        Eine spezielle Version von _finalize für den synchronen Refresh,
        die *nicht* versucht, den (nicht existierenden) Ladebalken zu entfernen.
        """
        self.inner_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def show_previous_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        self.app.current_display_date = last_day_of_previous_month.replace(day=1)
        if current_date.year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(self.app.current_display_date.year)
            self.app._load_events_for_year(self.app.current_display_date.year)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def show_next_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        first_day_of_next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        self.app.current_display_date = first_day_of_next_month
        if current_date.year != self.app.current_display_date.year:
            self.app._load_holidays_for_year(self.app.current_display_date.year)
            self.app._load_events_for_year(self.app.current_display_date.year)
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def check_understaffing(self):
        self.clear_understaffing_results()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]

        # Synchrone Datenladung für die Prüfung
        self.data_manager.load_and_process_data(year, month)
        daily_counts = self.data_manager.daily_counts

        # --- KORREKTUR: Verwende self.app.shift_types_data statt self.app.get_ordered_shift_abbrevs ---
        # get_ordered_shift_abbrevs gibt eine LISTE von Dictionaries zurück,
        # aber wir müssen auf die DATEN zugreifen, die im shift_types_data Dictionary gespeichert sind.

        shifts_to_check = []
        for abbrev, shift_data in self.app.shift_types_data.items():
            if shift_data.get('check_for_understaffing'):
                shifts_to_check.append(abbrev)
        # --- ENDE KORREKTUR ---

        understaffing_found = False

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            date_str = current_date.strftime('%Y-%m-%d')
            min_staffing = self.data_manager.get_min_staffing_for_date(current_date)

            for shift in shifts_to_check:
                min_req = min_staffing.get(shift)
                if min_req is not None:
                    count = daily_counts.get(date_str, {}).get(shift, 0)
                    if count < min_req:
                        understaffing_found = True
                        shift_name = self.app.shift_types_data.get(shift, {}).get('name', shift)
                        ttk.Label(self.understaffing_result_frame,
                                  text=f"Unterbesetzung am {current_date.strftime('%d.%m.%Y')}: Schicht '{shift_name}' ({shift}) - {count} von {min_req} Mitarbeitern anwesend.",
                                  foreground="red", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        if not understaffing_found:
            ttk.Label(self.understaffing_result_frame, text="Keine Unterbesetzungen gefunden.",
                      foreground="green", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        self.understaffing_result_frame.pack(fill="x", pady=5)

    def clear_understaffing_results(self):
        self.understaffing_result_frame.pack_forget()
        for widget in self.understaffing_result_frame.winfo_children():
            widget.destroy()

    def update_lock_status(self):
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)

        s = ttk.Style()
        s.configure("Lock.TButton", background="red", foreground="white", font=('Segoe UI', 9, 'bold'))
        s.map("Lock.TButton", background=[('active', '#CC0000')])
        s.configure("Unlock.TButton", background="green", foreground="white", font=('Segoe UI', 9, 'bold'))
        s.map("Unlock.TButton", background=[('active', '#006400')])

        if is_locked:
            self.lock_status_label.config(text="(Für Anträge gesperrt)", foreground="red")
            self.lock_button.config(text="Monat entsperren", style="Unlock.TButton")
        else:
            self.lock_status_label.config(text="")
            self.lock_button.config(text="Monat für Anträge sperren", style="Lock.TButton")

    def toggle_month_lock(self):
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)

        locks = RequestLockManager.load_locks()
        lock_key = f"{year}-{month:02d}"

        if is_locked:
            if lock_key in locks:
                del locks[lock_key]
        else:
            locks[lock_key] = True

        if RequestLockManager.save_locks(locks):
            self.app.refresh_antragssperre_views()
        else:
            messagebox.showerror("Fehler", "Der Status konnte nicht gespeichert werden.", parent=self)