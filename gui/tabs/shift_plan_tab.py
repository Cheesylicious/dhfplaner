# gui/tabs/shift_plan_tab.py
# REFRACTORED (Regel 4): Dient als Orchestrator.
# - UI-Erstellung in ShiftPlanUISetup ausgelagert.
# - Event-Handler (Callbacks) in ShiftPlanEvents ausgelagert.
# - Behält die Lade-Logik (Threading) und Status-Updates.
#
# KORRIGIERT (Regel 1) - DRITTE RUNDE:
# Die entscheidende Property 'user_shift_totals' hinzugefügt.
# Das Fehlen dieser Property hat dazu geführt, dass der
# ActionUpdateHandler die Ist-Stunden beim Hinzufügen
# einer Schicht genullt hat (Cache-Problem).
#
# --- INNOVATION (Regel 2): Latenz in 'refresh_plan' behoben ---
# Die Methode 'refresh_plan' wurde so geändert, dass sie nicht mehr
# synchron die Daten lädt, sondern den Cache invalidiert und
# den asynchronen Ladevorgang 'build_shift_plan_grid(data_ready=False)'
# anstößt. Dies verhindert das Einfrieren der UI, wenn andere Tabs
# ein Neuladen anfordern.

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta, datetime
import calendar
import threading

# Importiere die Helfer-Module
from gui.request_lock_manager import RequestLockManager
from gui.shift_plan_data_manager import ShiftPlanDataManager
from gui.shift_plan_renderer import ShiftPlanRenderer
from gui.shift_plan_actions import ShiftPlanActionHandler
from database.db_shifts import get_ordered_shift_abbrevs

# --- NEUE IMPORTE (Refactoring Regel 4) ---
from .tab_components.shift_plan_ui_setup import ShiftPlanUISetup
from .tab_components.shift_plan_events import ShiftPlanEvents


# --- ENDE NEUE IMPORTE ---


class ShiftPlanTab(ttk.Frame):
    """
    Haupt-Frame des Dienstplan-Tabs.
    Dient als Orchestrator für:
    - ShiftPlanUISetup (Erstellt die Widgets)
    - ShiftPlanEvents (Verarbeitet Button-Klicks und Tastatur-Eingaben)
    - ShiftPlanDataManager (Lädt und verwaltet Daten)
    - ShiftPlanRenderer (Zeichnet das Gitter)
    - ShiftPlanActionHandler (Verarbeitet Kontextmenü-Aktionen)

    Diese Klasse steuert hauptsächlich den Daten-Lade-Prozess (inkl. Threading)
    und die Aktualisierung des UI-Status (z.B. Ladebalken).
    """

    def __init__(self, master, app):  # 'app' ist MainAdminWindow/MainUserWindow
        super().__init__(master)
        self.app = app  # app ist MainAdminWindow/MainUserWindow

        # --- 1. Bootloader und DataManager initialisieren ---
        bootloader_app = self.app.app
        self.data_manager = self._init_data_manager(bootloader_app)

        # --- 2. ActionHandler und Renderer initialisieren (Korrektur-Sequenz) ---
        self.action_handler = ShiftPlanActionHandler(self, app, self.data_manager, None)
        self.renderer = ShiftPlanRenderer(self, bootloader_app, self.data_manager, self.action_handler)
        self.action_handler.set_renderer_and_init_helpers(self.renderer)

        # --- 3. UI- und Event-Handler initialisieren (Refactoring Regel 4) ---
        # (self.ui und self.events sind NEU)
        self.ui = ShiftPlanUISetup(self, app)
        self.events = ShiftPlanEvents(self)

        # --- 4. Tastatur-Shortcuts (Map verbleibt hier, wird von Events genutzt) ---
        self.shortcut_map = {
            't': 'T.',
            'n': 'N.',
            '6': '6',
            'f': '',  # 'f' für FREI
            'x': 'X',
            'u': 'U',
            's': 'S',
            'q': 'QA',
        }
        # (Leertaste 'space' wird direkt in ShiftPlanEvents behandelt)

        # --- 5. UI-Setup durchführen ---
        # Wir übergeben die Event-Handler-Instanz an den UI-Builder,
        # damit die Buttons/Bindings korrekt zugewiesen werden.
        self.ui.setup_ui(self.events)

        # --- 6. Renderer das Ziel-Frame zuweisen ---
        # (Das plan_grid_frame wurde von self.ui.setup_ui() erstellt)
        self.renderer.set_plan_grid_frame(self.ui.plan_grid_frame)

        # --- 7. Initialen Ladevorgang starten ---
        # (Logik zur Vermeidung der Race Condition P1a/P1b bleibt)
        current_app_date = self.app.current_display_date
        print(
            f"[ShiftPlanTab] Erzwinge Neuladen (data_ready=False) für {current_app_date.year}-{current_app_date.month}, um Race Condition (P1b) zu vermeiden.")
        self.build_shift_plan_grid(current_app_date.year, current_app_date.month, data_ready=False)

    def _init_data_manager(self, bootloader_app):
        """Initialisiert den DataManager oder übernimmt ihn vom Bootloader."""
        if hasattr(bootloader_app, 'data_manager') and bootloader_app.data_manager is not None:
            print("[ShiftPlanTab] Übernehme vorgeladenen DataManager vom Bootloader.")
            data_manager = bootloader_app.data_manager
            # WICHTIG: App-Referenz im DM auf das FENSTER (MainAdminWindow) aktualisieren
            data_manager.app = self.app
        else:
            print("[ShiftPlanTab] WARNUNG: Kein vorgeladener DataManager gefunden. Erstelle neuen.")
            data_manager = ShiftPlanDataManager(self.app)  # Fallback
        return data_manager

    # --- Lade- und Status-Logik (verbleibt im Orchestrator) ---

    def build_shift_plan_grid(self, year, month, data_ready=False):
        """
        Orchestriert das Leeren, Laden und Neuzeichnen des Dienstplans.
        Wird von Callbacks in ShiftPlanEvents aufgerufen.
        """
        month_name_german = {"January": "Januar", "February": "Februar", "March": "März", "April": "April",
                             "May": "Mai", "June": "Juni", "July": "Juli", "August": "August", "September": "September",
                             "October": "Oktober", "November": "November", "December": "Dezember"}
        try:
            month_name_en = date(year, month, 1).strftime('%B')
            self.ui.month_label_var.set(
                f"{month_name_german.get(month_name_en, month_name_en)} {year}")
        except ValueError:
            self.ui.month_label_var.set(f"Ungültiger Monat {month}/{year}")

        self.update_lock_status()

        # Altes Gitter leeren
        for widget in self.ui.plan_grid_frame.winfo_children():
            widget.destroy()
        if self.renderer:
            self.renderer.grid_widgets = {'cells': {}, 'user_totals': {}, 'daily_counts': {}}

        if data_ready:
            # Fall 1: Daten sind bereits geladen (z.B. durch Preloader)
            print(f"[ShiftPlanTab] Starte sofortiges Rendering für {year}-{month} (data_ready=True).")
            # Stelle sicher, dass der Ladebalken weg ist (falls er noch da war)
            self.hide_progress_widgets()
            self._render_grid(year, month)
        else:
            # Fall 2: Daten müssen aktiv geladen werden (Standard)
            # (Zeigt Ladebalken an)
            self.show_progress_widgets(text="Daten werden geladen...")

            print(f"[ShiftPlanTab] Starte Lade-Thread für {year}-{month} (data_ready=False)...")
            threading.Thread(target=self._load_data_in_thread, args=(year, month), daemon=True).start()

    def _load_data_in_thread(self, year, month):
        """Worker-Thread zum Laden der Daten (Regel 2: Latenz vermeiden)."""
        error_message = None
        try:
            # _safe_update_progress wird als Callback für den Ladebalken übergeben
            success = self.data_manager.load_and_process_data(year, month, self._safe_update_progress)
            if success:
                # Zurück zum UI-Thread, um das Gitter zu zeichnen
                self.after(1, lambda: self._render_grid(year, month))
            else:
                raise Exception("load_and_process_data hat 'False' zurückgegeben.")
        except Exception as e:
            print(f"FEHLER beim Laden der Daten im Thread: {e}")
            error_message = f"Fehler beim Laden der Daten:\n{e}"
            self.after(1, lambda msg=error_message: messagebox.showerror("Fehler", msg, parent=self))
            self.after(1, lambda: self.ui.status_label.config(
                text="Laden fehlgeschlagen!") if self.ui.status_label and self.ui.status_label.winfo_exists() else None)

    def _render_grid(self, year, month):
        """Rendert das Gitter, nachdem die Daten geladen wurden."""
        if not self.renderer:
            print("[FEHLER] Renderer nicht initialisiert in _render_grid.")
            return

        # Status auf "Zeichnen" aktualisieren
        self._safe_update_progress(100, "Zeichne Gitter...")
        self.update_idletasks()

        # Starte den eigentlichen Zeichenvorgang im Renderer
        # HINWEIS: Wir übergeben 'is_sync_refresh=False' (oder nichts),
        # damit der Renderer die Standard-Methode '_finalize_ui_after_render' aufruft.
        self.renderer.build_shift_plan_grid(year, month, data_ready=True)

        # Hinweis: self.renderer.build_shift_plan_grid ruft jetzt
        # self._finalize_ui_after_render (HIER) auf, wenn es fertig ist.

    def _finalize_ui_after_render(self):
        """
        Wird vom Renderer aufgerufen, NACHDEM das Gitter gezeichnet wurde.
        Versteckt den Ladebalken und konfiguriert die Scrollregion.
        """
        self.hide_progress_widgets()

        if self.ui.inner_frame.winfo_exists() and self.ui.canvas.winfo_exists():
            self.ui.inner_frame.update_idletasks()
            self.ui.canvas.config(scrollregion=self.ui.canvas.bbox("all"))

    # --- UI-Status (Ladebalken & Sperren) ---

    def show_progress_widgets(self, text="Starte Vorgang..."):
        """Zeigt die Lade-Widgets an (aufgerufen von Events oder build_grid)."""
        # (Wir rufen die UI-Methode auf, um die Widgets zu erstellen/neu zu erstellen)
        self.ui._create_progress_widgets()

        # Mache das Progress-Frame sichtbar
        self.ui.progress_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.ui.plan_grid_frame.grid_rowconfigure(0, weight=1)
        self.ui.plan_grid_frame.grid_columnconfigure(0, weight=1)
        self.ui.progress_bar.config(value=0, maximum=100)
        self.ui.status_label.config(text=text)
        self.update_idletasks()

    def hide_progress_widgets(self):
        """Versteckt die Lade-Widgets (aufgerufen nach dem Rendern)."""
        if self.ui.progress_frame and self.ui.progress_frame.winfo_exists():
            self.ui.progress_frame.grid_forget()
            if self.ui.plan_grid_frame.winfo_exists():
                self.ui.plan_grid_frame.grid_rowconfigure(0, weight=0)
                self.ui.plan_grid_frame.grid_columnconfigure(0, weight=0)

    def _safe_update_progress(self, value, text):
        """Thread-sichere Methode zur Aktualisierung des Ladebalkens."""
        self.after(0, lambda v=value, t=text: self._update_progress(v, t))

    def _update_progress(self, step_value, step_text):
        """Aktualisiert die Lade-Widgets im UI-Thread."""
        if self.ui.progress_bar and self.ui.progress_bar.winfo_exists():
            self.ui.progress_bar.config(value=step_value)
        if self.ui.status_label and self.ui.status_label.winfo_exists():
            self.ui.status_label.config(text=step_text)

    def update_lock_status(self):
        """Aktualisiert die UI-Anzeige für die Monatssperre."""
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)
        s = ttk.Style()
        s.configure("Lock.TButton", background="red", foreground="white", font=('Segoe UI', 9, 'bold'))
        s.map("Lock.TButton", background=[('active', '#CC0000')])
        s.configure("Unlock.TButton", background="green", foreground="white", font=('Segoe UI', 9, 'bold'))
        s.map("Unlock.TButton", background=[('active', '#006400')])

        if is_locked:
            self.ui.lock_status_label.config(text="(Für Anträge gesperrt)", foreground="red")
            self.ui.lock_button.config(
                text="Monat entsperren", style="Unlock.TButton")
        else:
            self.ui.lock_status_label.config(text="")
            self.ui.lock_button.config(text="Monat für Anträge sperren",
                                       style="Lock.TButton")

    # --- Callback vom Generator (wird von ShiftPlanEvents aufgerufen) ---

    def _on_generation_complete(self, success, save_count, error_message):
        """
        Callback, der ausgeführt wird, nachdem der Generator-Thread
        abgeschlossen ist.
        """
        year = self.app.current_display_date.year
        month = self.app.current_display_date.month

        # Ladebalken ausblenden
        self.hide_progress_widgets()

        # --- KORREKTUR (Problem 2): P5-Cache invalidieren ---
        if hasattr(self, 'data_manager') and hasattr(self.data_manager, 'invalidate_month_cache'):
            print(f"[ShiftPlanTab] Invalidiere DM-Cache für {year}-{month} nach Generierung.")
            self.data_manager.invalidate_month_cache(year, month)
        else:
            print("[WARNUNG] DataManager oder invalidate_month_cache nicht gefunden. Cache nicht invalidiert.")
        # --- ENDE KORREKTUR ---

        if success:
            messagebox.showinfo("Erfolg",
                                f"Plan-Generierung abgeschlossen.\n{save_count} Dienste wurden eingetragen.",
                                parent=self)
        else:
            messagebox.showerror("Fehler bei Generierung", error_message, parent=self)

        # Plan in jedem Fall neu laden, um Ergebnisse (oder Fehlerzustand) anzuzeigen
        # (Startet den asynchronen Lader mit Ladebalken)
        self.build_shift_plan_grid(year, month, data_ready=False)

    # --- KORRIGIERT (Regel 2): Asynchrones Refresh ---

    def refresh_plan(self):
        """
        Erzwingt ein ASYNCHRONES Neuladen und Neuzeichnen der Daten.
        (Wird oft von anderen Tabs aufgerufen, wenn sich Daten ändern)

        INNOVATION (Regel 2):
        Lädt nicht mehr synchron, sondern invalidiert den Cache und
        ruft den Standard-Ladevorgang 'build_shift_plan_grid' auf,
        der den Ladebalken anzeigt und im Hintergrund lädt.
        """
        print("[ShiftPlanTab] Starte asynchronen Refresh (von extern getriggert)...")
        year, month = self.app.current_display_date.year, self.app.current_display_date.month

        # 1. P5-Cache invalidieren (WICHTIG!)
        # Stellt sicher, dass die Daten WIRKLICH neu von der DB geladen werden.
        if hasattr(self, 'data_manager') and hasattr(self.data_manager, 'invalidate_month_cache'):
            print(f"   -> Invalidiere DM-Cache für {year}-{month} für Refresh.")
            self.data_manager.invalidate_month_cache(year, month)
        else:
            print("   -> [WARNUNG] DataManager oder invalidate_month_cache nicht gefunden. Cache nicht invalidiert.")

        # 2. Standard-Ladevorgang (asynchron) aufrufen
        # 'data_ready=False' erzwingt das Neuladen im Thread und zeigt den Ladebalken.
        print("   -> Rufe build_shift_plan_grid(data_ready=False) auf.")
        self.build_shift_plan_grid(year, month, data_ready=False)

        print("[ShiftPlanTab] Asynchroner Refresh-Auftrag gestartet.")

    # --- ENTFERNT (Regel 4): Nicht mehr benötigt ---
    # def _finalize_ui_after_render_sync(self):
    # (Diese Methode wurde nur vom alten, synchronen refresh_plan verwendet.
    # Der neue asynchrone Refresh nutzt den Standard-Pfad, der
    # '_finalize_ui_after_render' aufruft, um den Ladebalken zu verstecken.)
    # --- ENDE ENTFERNT ---

    # --- NEU: Kompatibilitäts-Properties (Fix für Regel 1) ---
    # Diese fangen alte Zugriffe (z.B. self.inner_frame) ab und
    # leiten sie an das neue UI-Objekt (self.ui.inner_frame) weiter.
    # Dies repariert externen Code (wie ActionUpdateHandler),
    # der durch das Refactoring gebrochen wurde.

    # --- 1. UI-Elemente ---
    @property
    def inner_frame(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.inner_frame weiter."""
        return self.ui.inner_frame

    @property
    def canvas(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.canvas weiter."""
        return self.ui.canvas

    @property
    def plan_grid_frame(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.plan_grid_frame weiter."""
        return self.ui.plan_grid_frame

    @property
    def month_label_var(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.month_label_var weiter."""
        return self.ui.month_label_var

    @property
    def lock_status_label(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.lock_status_label weiter."""
        return self.ui.lock_status_label

    @property
    def lock_button(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.lock_button weiter."""
        return self.ui.lock_button

    @property
    def understaffing_result_frame(self):
        """Kompatibilitäts-Property: Leitet zu self.ui.understaffing_result_frame weiter."""
        return self.ui.understaffing_result_frame

    # --- 2. Daten-Elemente (WICHTIG FÜR STUNDENBERECHNUNG) ---
    @property
    def grid_widgets(self):
        """
        Kompatibilitäts-Property: Leitet zu self.renderer.grid_widgets weiter.
        (Wichtig für ActionUpdateHandler -> Aktualisierung der Summen-Labels)
        """
        return self.renderer.grid_widgets

    @property
    def user_data_map(self):
        """
        Kompatibilitäts-Property: Leitet zu self.data_manager.user_data_map weiter.
        (Wichtig für Stundenberechnung - Soll-Stunden)
        """
        return self.data_manager.user_data_map

    # --- HINZUGEFÜGT: Fix für das "Stunden-Nullen"-Problem ---
    @property
    def user_shift_totals(self):
        """
        Kompatibilitäts-Property: Leitet zu self.data_manager.user_shift_totals weiter.
        (Wichtig für Stundenberechnung - Ist-Stunden-Basis)
        """
        return self.data_manager.user_shift_totals

    # --- ENDE FIX ---

    @property
    def shift_types_data(self):
        """
        Kompatibilitäts-Property: Leitet zu self.app.app.shift_types_data weiter.
        (Wichtig für Stundenberechnung - Schicht-Stundenwerte)
        """
        return self.app.app.shift_types_data

    @property
    def shift_frequency(self):
        """
        Kompatibilitäts-Property: Leitet zu self.app.shift_frequency weiter.
        (Wichtig für Menü-Erstellung im ActionHandler)
        """
        return self.app.shift_frequency

    # --- ENDE Kompatibilitäts-Properties ---