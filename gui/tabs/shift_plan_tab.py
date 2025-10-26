# gui/tabs/shift_plan_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta
import calendar
import threading
from collections import defaultdict

# Importiere die Helfer-Module
from database.db_users import get_ordered_users_for_schedule
from gui.request_lock_manager import RequestLockManager
from gui.shift_plan_data_manager import ShiftPlanDataManager
from gui.shift_plan_renderer import ShiftPlanRenderer
from gui.shift_plan_actions import ShiftPlanActionHandler
from database.db_shifts import get_ordered_shift_abbrevs
# Der Import von RejectionReasonDialog (den wir zuletzt korrigiert haben)
from ..dialogs.rejection_reason_dialog import RejectionReasonDialog


class ShiftPlanTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # Helfer-Komponenten initialisieren
        self.data_manager = ShiftPlanDataManager(app)
        self.action_handler = ShiftPlanActionHandler(self, app, self, None)  # Renderer wird später gesetzt
        self.renderer = ShiftPlanRenderer(self, app, self.data_manager, self.action_handler)
        self.action_handler.renderer = self.renderer  # Renderer im ActionHandler setzen

        # Attribute aus Managern holen
        self.grid_widgets = self.renderer.grid_widgets  # Leeres Dict initial
        self.violation_cells = self.data_manager.violation_cells  # Leeres Set initial

        # Cache für Menü-Elemente (wird von ActionHandler verwendet)
        self._menu_item_cache = self._prepare_shift_menu_items()

        # Progressbar und Status-Label sind initial None
        self.progress_frame = None
        self.progress_bar = None
        self.status_label = None

        self.setup_ui()
        # Wichtig: Den Frame für den Renderer setzen *nachdem* setup_ui gelaufen ist
        self.renderer.set_plan_grid_frame(self.plan_grid_frame)

        # Starte den ersten Ladevorgang
        self.build_shift_plan_grid(self.app.current_display_date.year, self.app.current_display_date.month)

    def _prepare_shift_menu_items(self):
        """Berechnet alle Schicht-Menüeinträge, sortiert nach Frequenz, und gibt eine Liste von Tupeln zurück."""
        all_abbrevs = list(self.app.shift_types_data.keys())
        # Stelle sicher, dass der ActionHandler existiert, um die Config zu laden
        menu_config = {}
        if self.action_handler:
            menu_config = self.action_handler._menu_config_cache
        else:
            print("[WARNUNG] ActionHandler nicht bereit für Menü-Vorbereitung.")
            # Fallback: Lade Config direkt (weniger ideal, da doppelt geladen)
            # from database.db_core import load_config_json
            # SHIFT_MENU_CONFIG_KEY = "SHIFT_DISPLAY_CONFIG"
            # menu_config = load_config_json(SHIFT_MENU_CONFIG_KEY) or {}

        shift_frequency = self.app.shift_frequency
        sorted_abbrevs = sorted(all_abbrevs, key=lambda s: shift_frequency.get(s, 0), reverse=True)

        prepared_items = []
        for abbrev in sorted_abbrevs:
            if menu_config.get(abbrev, True):  # Default: True (anzeigen)
                shift_info = self.app.shift_types_data.get(abbrev)
                if shift_info:
                    name = shift_info.get('name', abbrev)
                    count = shift_frequency.get(abbrev, 0)
                    label_text = f"{abbrev} ({name})" + (f"  (Bisher {count}x)" if count > 0 else "")
                    prepared_items.append((abbrev, label_text))
        return prepared_items

    def setup_ui(self):
        # Container für alles
        main_view_container = ttk.Frame(self, padding="10")
        main_view_container.pack(fill="both", expand=True)

        # Navigationsleiste oben
        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(nav_frame, text="< Voriger Monat", command=self.show_previous_month).pack(side="left")
        ttk.Button(nav_frame, text="📄 Drucken", command=self.print_shift_plan).pack(side="left", padx=20)

        # Monatsanzeige (zentriert)
        self.month_label_var = tk.StringVar()
        month_label_frame = ttk.Frame(nav_frame)
        month_label_frame.pack(side="left", expand=True, fill="x")  # Nimmt verfügbaren Platz ein
        ttk.Label(month_label_frame, textvariable=self.month_label_var, font=("Segoe UI", 14, "bold"),
                  anchor="center").pack()
        self.lock_status_label = ttk.Label(month_label_frame, text="", font=("Segoe UI", 10, "italic"), anchor="center")
        self.lock_status_label.pack()

        ttk.Button(nav_frame, text="Nächster Monat >", command=self.show_next_month).pack(side="right")

        # Hauptbereich für das Grid mit Scrollbars
        grid_container_frame = ttk.Frame(main_view_container)
        grid_container_frame.pack(fill="both", expand=True)  # Nimmt restlichen Platz ein

        vsb = ttk.Scrollbar(grid_container_frame, orient="vertical")
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")

        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=vsb.set, xscrollcommand=hsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        vsb.config(command=self.canvas.yview)
        hsb.config(command=self.canvas.xview)

        # Innerer Frame im Canvas, der das eigentliche Grid enthält
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")

        # Frame für das Dienstplan-Grid selbst (wird vom Renderer gefüllt)
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)

        # Konfiguration für Scrollbars und Canvas-Größe
        def _configure_inner_frame(event):
            # Update des inneren Frames, wenn Canvas-Größe sich ändert
            self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event):
            # Update der Scrollregion, wenn innerer Frame sich ändert
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame)
        self.inner_frame.bind('<Configure>', _configure_scrollregion)

        # Fußleiste für Aktionen
        footer_frame = ttk.Frame(main_view_container)
        footer_frame.pack(fill="x", pady=(10, 0))  # Pack am Ende unter das Grid

        # Buttons für Prüfung
        check_frame = ttk.Frame(footer_frame)
        check_frame.pack(side="left")
        ttk.Button(check_frame, text="Schichtplan Prüfen", command=self.check_understaffing).pack(side="left", padx=5)
        ttk.Button(check_frame, text="Leeren", command=self.clear_understaffing_results).pack(side="left", padx=5)

        # Button für Monatssperre
        self.lock_button = ttk.Button(footer_frame, text="", command=self.toggle_month_lock)
        self.lock_button.pack(side="right", padx=5)

        # Frame für Ergebnisse der Prüfung (initial versteckt)
        self.understaffing_result_frame = ttk.Frame(main_view_container, padding="10")
        # .pack() wird erst in check_understaffing() aufgerufen

    def _create_progress_widgets(self):
        """Erstellt das Fortschritts-Frame und seine Widgets neu."""
        # Entferne altes Frame, falls vorhanden
        if self.progress_frame and self.progress_frame.winfo_exists():
            self.progress_frame.destroy()

        self.progress_frame = ttk.Frame(self.plan_grid_frame)  # Erstellt im Grid-Frame
        self.status_label = ttk.Label(self.progress_frame, text="", font=("Segoe UI", 12))
        self.status_label.pack(pady=(20, 5))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=300, mode='determinate')
        self.progress_bar.pack(pady=5)

    def print_shift_plan(self):
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        month_name = self.month_label_var.get()
        # Stelle sicher, dass der Renderer initialisiert ist
        if self.renderer:
            self.renderer.print_shift_plan(year, month, month_name)
        else:
            messagebox.showerror("Fehler", "Druckfunktion nicht bereit.", parent=self)

    def build_shift_plan_grid(self, year, month):
        """Startet den Datenladevorgang in einem separaten Thread und initialisiert den Ladebalken."""
        # --- Schritt 5.4: Benutzer hier NICHT mehr laden ---
        # self.app.current_shift_plan_users = get_ordered_users_for_schedule() # Entfernt
        # --- Ende Schritt 5.4 ---

        # 1. Alte Widgets entfernen
        for widget in self.plan_grid_frame.winfo_children():
            widget.destroy()
        # Wichtig: Auch die Referenzen im Renderer zurücksetzen!
        if self.renderer:
            self.renderer.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}
        self.data_manager.violation_cells.clear()  # Konflikte auch leeren

        # 2. Fortschritts-Widgets erstellen und platzieren
        self._create_progress_widgets()
        # Zentriere das Lade-Frame im plan_grid_frame
        self.progress_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.plan_grid_frame.grid_rowconfigure(0, weight=1)
        self.plan_grid_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar.config(value=0, maximum=100)
        self.status_label.config(text="Daten werden geladen...")
        # Stelle sicher, dass das UI aktualisiert wird, bevor der Thread startet
        self.update_idletasks()

        # Monatslabel setzen
        month_name_german = {"January": "Januar", "February": "Februar", "March": "März", "April": "April",
                             "May": "Mai", "June": "Juni", "July": "Juli", "August": "August",
                             "September": "September", "October": "Oktober", "November": "November",
                             "December": "Dezember"}
        try:
            month_name_en = date(year, month, 1).strftime('%B')
            self.month_label_var.set(f"{month_name_german.get(month_name_en, month_name_en)} {year}")
        except ValueError:
            self.month_label_var.set(f"Ungültiger Monat {month}/{year}")  # Fallback

        self.update_lock_status()  # Sperrstatus aktualisieren

        # Thread starten
        print(f"[ShiftPlanTab] Starte Lade-Thread für {year}-{month}...")
        threading.Thread(target=self._load_data_in_thread, args=(year, month), daemon=True).start()

    def _update_progress(self, step_value, step_text):
        """Sichere Methode zur Aktualisierung des Ladebalkens aus dem Worker-Thread."""
        # Prüfen, ob Widgets noch existieren, bevor auf sie zugegriffen wird
        if self.progress_bar and self.progress_bar.winfo_exists():
            self.after(0, lambda: self.progress_bar.config(value=step_value))
        if self.status_label and self.status_label.winfo_exists():
            self.after(0, lambda: self.status_label.config(text=step_text))

    def _load_data_in_thread(self, year, month):
        """Führt die zeitraubenden DB-Abrufe im Worker-Thread durch."""
        error_message = None  # Variable für Fehlermeldung
        try:
            # Datenmanager lädt die Daten (inkl. voller Konfliktprüfung)
            # Hier wird die Zählung (daily_counts) im DataManager (durch unsere letzte Korrektur)
            # bereits korrekt aus den DB-Schichtdaten neu berechnet.
            self.data_manager.load_and_process_data(year, month, self._update_progress)
            # Nach erfolgreichem Laden: Starte die Render-Funktion im Haupt-Thread
            self.after(1, lambda: self._render_grid(year, month))
        except Exception as e:
            # --- Korrektur 2: Fehlerbehandlung ---
            print(f"FEHLER beim Laden der Daten im Thread: {e}")
            # Speichere die Fehlermeldung für die Übergabe an die GUI
            error_message = f"Fehler beim Laden der Daten:\n{e}"
            # Plane die Anzeige der Fehlermeldung im Hauptthread
            # Wichtig: Übergib die *Nachricht* (error_message), nicht die Exception-Variable 'e' direkt!
            self.after(1, lambda msg=error_message: messagebox.showerror("Fehler", msg, parent=self))
            # Aktualisiere auch das Statuslabel im Hauptthread
            self.after(1, lambda: self.status_label.config(
                text="Laden fehlgeschlagen!") if self.status_label and self.status_label.winfo_exists() else None)
            # --- Ende Korrektur 2 ---

    def _render_grid(self, year, month):
        """
        Rendert das Grid im Haupt-Thread, nachdem die Daten geladen wurden.
        """
        # Stelle sicher, dass der Renderer existiert
        if not self.renderer:
            print("[FEHLER] Renderer nicht initialisiert in _render_grid.")
            if self.status_label and self.status_label.winfo_exists():
                self.status_label.config(text="Fehler: UI-Komponente fehlt.")
            return

        # Fortschritt aktualisieren (im Hauptthread)
        if self.progress_bar and self.progress_bar.winfo_exists():
            self.progress_bar.config(value=100)
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.config(text="Zeichne Gitter...")
        self.update_idletasks()  # UI aktualisieren lassen

        # Starte den Render-Vorgang (Chunked)
        # Die data_ready=True Flag signalisiert dem Renderer, die gecachten Daten vom DM zu nutzen
        self.renderer.build_shift_plan_grid(year, month, data_ready=True)

    def _finalize_ui_after_render(self):
        """
        Wird vom Renderer aufgerufen, wenn der Zeichenprozess beendet ist.
        Entfernt den Ladebalken und passt die Scrollregion an.
        """
        # Ladebalken entfernen
        if self.progress_frame and self.progress_frame.winfo_exists():
            self.progress_frame.grid_forget()  # grid_forget statt destroy, um Neupositionierung zu ermöglichen
            # Konfiguration der Grid-Zeilen/-Spalten zurücksetzen
            if self.plan_grid_frame.winfo_exists():
                self.plan_grid_frame.grid_rowconfigure(0, weight=0)
                self.plan_grid_frame.grid_columnconfigure(0, weight=0)

        # Scrollregion anpassen
        if self.inner_frame.winfo_exists() and self.canvas.winfo_exists():
            self.inner_frame.update_idletasks()
            self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def refresh_plan(self):
        """
        Öffentliche Methode zum schnellen Aktualisieren des Plans nach einer Aktion
        (z.B. Schichtänderung). Nutzt inkrementelles Update für Konflikte.
        Läuft synchron im GUI-Thread.

        HINWEIS: Diese Funktion wird aktuell (glaube ich) nicht mehr genutzt,
        da wir gezielte Updates (wie _trigger_targeted_update) verwenden.
        Falls sie doch genutzt wird, ist sie jetzt problematisch, da sie
        load_and_process_data aufruft und die Live-Daten überschreibt.

        Wir lassen sie vorerst unverändert, da der Bug in check_understaffing liegt.
        """
        print("[ShiftPlanTab] Starte synchronen Refresh...")
        year, month = self.app.current_display_date.year, self.app.current_display_date.month

        try:
            print("   -> Lade Daten synchron für Refresh (inkl. voller Konfliktprüfung)...")
            self.data_manager.load_and_process_data(year, month)
            print("   -> Daten für Refresh geladen.")

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Aktualisieren der Plandaten: {e}", parent=self)
            return

        if self.renderer:
            print("   -> Zeichne Grid neu für Refresh...")
            self.renderer.build_shift_plan_grid(year, month, data_ready=True)
            print("   -> Grid für Refresh neu gezeichnet.")
        else:
            print("[FEHLER] Renderer nicht verfügbar für Refresh.")

    def _finalize_ui_after_render_sync(self):
        """
        Finalisierung für den synchronen Refresh (passt nur Scrollregion an).
        Wird jetzt direkt vom Renderer am Ende von build_shift_plan_grid aufgerufen.
        """
        if self.inner_frame.winfo_exists() and self.canvas.winfo_exists():
            self.inner_frame.update_idletasks()
            self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def show_previous_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        self.app.current_display_date = last_day_of_previous_month  # Gehe zum letzten Tag des Vormonats
        new_year, new_month = self.app.current_display_date.year, self.app.current_display_date.month
        # Setze auf den Ersten des neuen Monats für Konsistenz
        self.app.current_display_date = self.app.current_display_date.replace(day=1)

        # Feiertage/Events nur bei Jahreswechsel neu laden
        if current_date.year != new_year:
            self.app._load_holidays_for_year(new_year)
            self.app._load_events_for_year(new_year)

        # Starte asynchrones Laden für den neuen Monat
        self.build_shift_plan_grid(new_year, new_month)

    def show_next_month(self):
        self.clear_understaffing_results()
        current_date = self.app.current_display_date
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        first_day_of_next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        self.app.current_display_date = first_day_of_next_month
        new_year, new_month = self.app.current_display_date.year, self.app.current_display_date.month

        # Feiertage/Events nur bei Jahreswechsel neu laden
        if current_date.year != new_year:
            self.app._load_holidays_for_year(new_year)
            self.app._load_events_for_year(new_year)

        # Starte asynchrones Laden für den neuen Monat
        self.build_shift_plan_grid(new_year, new_month)

    def check_understaffing(self):
        self.clear_understaffing_results()
        year, month = self.app.current_display_date.year, self.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]

        # --- KORREKTUR START (BUG 2) ---
        # Das Neuladen der Daten überschreibt die inkrementellen Änderungen (z.B. das Löschen von "T."),
        # die nur im Arbeitsspeicher (im DataManager) vorhanden sind, bevor die Prüfung läuft.
        # Wir müssen *direkt* die Daten verwenden, die der DataManager *jetzt* hat.

        # ENTFERNT:
        # try:
        #      print("[Check Understaffing] Lade Daten synchron...")
        #      self.data_manager.load_and_process_data(year, month)
        #      print("[Check Understaffing] Daten geladen.")
        # except Exception as e:
        #      messagebox.showerror("Fehler", f"Fehler beim Laden der Daten für die Prüfung: {e}", parent=self)
        #      return
        print("[Check Understaffing] Verwende aktuelle Live-Daten aus dem DataManager...")
        # --- KORREKTUR ENDE ---

        # Greife direkt auf die (hoffentlich) aktuellen Zählungen im DataManager zu
        daily_counts = self.data_manager.daily_counts
        shifts_to_check_data = get_ordered_shift_abbrevs(include_hidden=False)  # Holt die sortierte Liste
        shifts_to_check = [item['abbreviation'] for item in shifts_to_check_data if
                           item.get('check_for_understaffing')]  # Filtere nach Flag

        understaffing_found = False
        self.understaffing_result_frame.pack(fill="x", pady=5, before=self.lock_button.master)  # Zeige Frame an

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            date_str = current_date.strftime('%Y-%m-%d')
            min_staffing = self.data_manager.get_min_staffing_for_date(current_date)

            for shift in shifts_to_check:
                min_req = min_staffing.get(shift)
                if min_req is not None and min_req > 0:  # Nur prüfen, wenn > 0 gefordert
                    # Hole die aktuelle Zählung aus dem Live-Cache
                    count = daily_counts.get(date_str, {}).get(shift, 0)
                    if count < min_req:
                        understaffing_found = True
                        shift_name = self.app.shift_types_data.get(shift, {}).get('name', shift)
                        ttk.Label(self.understaffing_result_frame,
                                  text=f"Unterbesetzung am {current_date.strftime('%d.%m.%Y')}: Schicht '{shift_name}' ({shift}) - {count} von {min_req} anwesend.",
                                  foreground="red", font=("Segoe UI", 10)).pack(anchor="w")  # Kleinere Schrift

        if not understaffing_found:
            ttk.Label(self.understaffing_result_frame, text="Keine Unterbesetzungen gefunden.",
                      foreground="green", font=("Segoe UI", 10, "bold")).pack(anchor="w")

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
            if lock_key in locks: del locks[lock_key]
        else:
            locks[lock_key] = True

        if RequestLockManager.save_locks(locks):
            self.update_lock_status()  # UI sofort aktualisieren
            # Benachrichtige andere Tabs (falls nötig und implementiert)
            if hasattr(self.app, 'refresh_antragssperre_views'):
                self.app.refresh_antragssperre_views()
        else:
            messagebox.showerror("Fehler", "Der Status konnte nicht gespeichert werden.", parent=self)