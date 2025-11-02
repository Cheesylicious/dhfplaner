# gui/preloading_manager.py
import threading
import time
from datetime import date, timedelta
from queue import Queue, Empty

from utils.threading_utils import Task, ThreadPool
from gui.shift_plan_data_manager import ShiftPlanDataManager


# --- NEU (Regel 4) ---
# Diese Datei kapselt die Post-Login Pre-Loading-Logik (P1b, P2, P4).


class PreloadingManager:
    """
    Orchestriert das Vorladen von Daten und UI-Tabs im Hintergrund (Post-Login),
    um die wahrgenommene Performance der Anwendung zu maximieren (P1b, P2, P4).
    Läuft in einem eigenen Thread-Pool, um die GUI nicht zu blockieren.
    """

    def __init__(self, app, data_manager: ShiftPlanDataManager, main_window):
        """
        Initialisiert den PreloadingManager.

        Args:
            app (BootLoader): Die Haupt-App-Instanz (für globale Daten).
            data_manager (ShiftPlanDataManager): Der zentrale Daten-Cache (P5).
            main_window (MainAdminWindow oder MainUserWindow): Das Hauptfenster für UI-Operationen.
        """
        self.app = app
        self.data_manager = data_manager
        self.main_window = main_window
        self.is_admin = hasattr(main_window, 'tab_manager')  # Prüfen, ob es sich um das Admin-Fenster handelt

        # Thread-Pool für alle Pre-Loading-Aufgaben
        # Wir nutzen einen Pool mit 1 Worker, um die Ladeaufgaben zu serialisieren
        # und die DB nicht mit parallelen Anfragen zu überlasten (Regel 2).
        self.pool = ThreadPool(max_workers=1, thread_name_prefix="Preloader")
        self.pool.start()

        # Queue für UI-Preloading (P2), wird vom Hauptthread abgearbeitet
        self.ui_preload_queue = Queue()

        # Speichert den *Index* des aktuell ausgewählten Tabs
        self.original_selected_index = 0

    def start_initial_preload(self):
        """
        Startet die initiale Ladekaskade (P1b, P2) nach dem Login.
        P1a und P3 wurden bereits vom BootLoader geladen.
        """
        print("[Preloader] Starte Post-Login Ladekaskade (P1b, P2)...")

        # P1b: Nächsten Dienstplan-Monat vorladen (N+1)
        preloaded_date = self.app.current_display_date
        task_p1 = Task(self._task_preload_next_month_data,
                       current_year=preloaded_date.year,
                       current_month=preloaded_date.month)
        self.pool.add_task(task_p1)

        # P2: UI-Tabs vorladen
        if self.is_admin:
            # (Korrigiert: Speichere Index statt Widget)
            try:
                self.original_selected_index = self.main_window.tab_manager.notebook.index("current")
            except Exception as e:
                print(f"[Preloader] Warnung: Konnte originalen Tab-Index nicht speichern, nutze 0: {e}")
                self.original_selected_index = 0

            # P2: UI-Tabs vorladen (im Admin-Fenster)
            task_p2 = Task(self._task_preload_admin_tabs_ui)
            self.pool.add_task(task_p2)
        else:
            pass

    def trigger_shift_plan_preload(self, new_year, new_month):
        """
        Wird aufgerufen, wenn der Benutzer im Dienstplan blättert (P4).
        Lädt den *darauf* folgenden Monat vor (N+1).
        """
        print(f"[Preloader] P4-Trigger: Blättern zu {new_year}-{new_month}. Lade N+1...")
        task = Task(self._task_preload_next_month_data, current_year=new_year, current_month=new_month)
        self.pool.add_task(task)

    def _get_next_month(self, year, month):
        """Berechnet den nächsten Monat basierend auf einem gegebenen Datum."""
        try:
            next_month_date = date(year, month, 1) + timedelta(days=32)
            return next_month_date.year, next_month_date.month
        except ValueError:
            today = date.today()
            next_month_date = today + timedelta(days=32)
            return next_month_date.year, next_month_date.month

    # --- P1b: Dienstplan-Daten (N+1) ---

    def _task_preload_next_month_data(self, current_year, current_month):
        """
        (Worker-Thread) Lädt die Daten für den Monat NACH dem übergebenen Monat (P1b / P4).
        """
        # FIX (Regel 1): Fängt den kritischen AttributeError ab, falls data_manager noch None ist.
        if not self.data_manager:
            print("[Preloader P1 FEHLER] ShiftPlanDataManager ist nicht initialisiert (None). Breche Dienstplan-Preload ab.")
            return

        try:
            year_to_load, month_to_load = self._get_next_month(current_year, current_month)
            cache_key = (year_to_load, month_to_load)

            if cache_key in self.data_manager.monthly_caches:
                print(
                    f"[Preloader P1] Monat {year_to_load}-{month_to_load} ist bereits im Cache (P5). Überspringe.")
                return

            print(f"[Preloader P1] Lade Dienstplan-Daten (N+1) für {year_to_load}-{month_to_load} vor...")
            self.data_manager.load_and_process_data(year_to_load, month_to_load, force_reload=False)
            print(f"[Preloader P1] Vorladen (N+1) für {year_to_load}-{month_to_load} abgeschlossen.")

        except Exception as e:
            print(f"[Preloader P1 FEHLER] Fehler beim Vorladen des Dienstplans: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(2)

    # --- P2: Admin UI-Tabs ---

    def _task_preload_admin_tabs_ui(self):
        """
        (Worker-Thread) Identifiziert die zu ladenden Admin-Tabs (P2)
        und stellt sie für den GUI-Thread bereit.
        """
        if not self.is_admin:
            return

        try:
            print("[Preloader P2] Starte Vorladen der Admin-Tab-UIs...")
            tab_manager = self.main_window.tab_manager

            tab_list_to_preload = tab_manager.tab_definitions.keys()

            for tab_name in tab_list_to_preload:
                if tab_name not in tab_manager.loaded_tabs:
                    self.ui_preload_queue.put({'task_type': 'create_tab', 'tab_name': tab_name})

            print("[Preloader P2] Alle UI-Tab-Aufgaben in Queue gestellt.")

        except Exception as e:
            print(f"[Preloader P2 FEHLER] Fehler beim Vorbereiten der Tab-UIs: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(1)  # Kurze Pause

    # --- P3: Admin Tab-Daten (ENTFERNT) ---
    # (Wird im boot_loader.py geladen)

    def process_ui_queue(self):
        """
        (GUI-Thread) Verarbeitet Aufgaben aus der UI-Queue (P2).
        MUSS im Haupt-Thread (z.B. über root.after()) aufgerufen werden.
        """
        try:
            # Verarbeite nur eine UI-Aufgabe pro Zyklus, um die GUI nicht zu blockieren
            if not self.ui_preload_queue.empty():
                task = self.ui_preload_queue.get_nowait()
                tab_manager = self.main_window.tab_manager

                if task['task_type'] == 'create_tab':
                    tab_name = task['tab_name']

                    if self.is_admin and tab_name not in tab_manager.loaded_tabs:
                        # --- KORREKTUR (behebt Flimmern) ---
                        # Wir rufen die neue Funktion auf, die *nicht* den Tab wechselt.
                        print(f"[Preloader P2] Lade UI für Tab: {tab_name} (im Hintergrund)")
                        tab_manager.preload_tab(tab_name, force_select=False)
                        # --- ENDE KORREKTUR ---

                self.ui_preload_queue.task_done()

        except Empty:
            pass  # Queue ist leer, alles gut
        except Exception as e:
            print(f"[Preloader GUI FEHLER] Fehler bei der UI-Queue-Verarbeitung: {e}")
            import traceback
            traceback.print_exc()

        # Plant die nächste Prüfung der Queue
        if self.main_window.winfo_exists():
            # Wir rufen den nächsten Zyklus auf
            self.main_window.after(250, self.process_ui_queue)

    def stop(self):
        """Stoppt den Thread-Pool."""
        print("[Preloader] Stoppe Thread-Pool...")
        self.pool.stop()