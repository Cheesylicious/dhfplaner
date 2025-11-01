# gui/admin_window/admin_tab_data_loader.py
# NEU: Ausgelagerte Logik zum Laden von Tab-Daten (Titel-Zähler, Global Cache Refresh)

# DB-Importe für Zähler und Caches
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count
from database.db_users import get_all_users
from database.db_dogs import get_all_dogs
from database.db_admin import get_pending_password_resets_count

try:
    from database.db_tasks import get_open_tasks_count
except ImportError:
    print("[WARNUNG] db_tasks nicht gefunden (AdminTabDataLoader).")


    def get_open_tasks_count():
        return 0


class AdminTabDataLoader:
    """
    Diese Klasse bündelt die gesamte THREADED-Datenlade-Logik
    für den AdminTabManager.
    """

    def __init__(self, admin_window, tab_manager, thread_manager):
        self.admin_window = admin_window
        self.tab_manager = tab_manager  # Um Callbacks (UI-Updates) auszuführen
        self.thread_manager = thread_manager
        self.bootloader_app = admin_window.app

    # --- 1. Logik für Tab-Titel-Zähler ---

    def start_fetch_tab_title_counts(self):
        """Startet den Thread zum Holen der Tab-Zähler."""
        print("[AdminTabDataLoader] Starte Thread: Lade Tab-Titel-Zähler...")
        self.thread_manager.start_worker(
            self._fetch_tab_title_counts_thread,
            self._on_fetch_tab_title_counts_complete
        )

    def _fetch_tab_title_counts_thread(self):
        """
        [LÄUFT IM THREAD]
        Holt alle Zähler für die Tab-Titel aus der DB.
        """
        counts = {}
        try:
            counts["Wunschanfragen"] = len(get_pending_wunschfrei_requests())
            counts["Urlaubsanträge"] = get_pending_vacation_requests_count()
            counts["Bug-Reports"] = get_open_bug_reports_count()
            counts["Mitarbeiter"] = 0  # Platzhalter, Zähler fehlt in DB-Funktionen
            counts["Passwort-Resets"] = get_pending_password_resets_count()  # Für Header
            counts["Aufgaben"] = get_open_tasks_count()
            return counts
        except Exception as e:
            print(f"[FEHLER] _fetch_tab_title_counts_thread: {e}")
            return e

    def _on_fetch_tab_title_counts_complete(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback für Tab-Zähler.
        """
        if error:
            print(f"[FEHLER] _on_fetch_tab_title_counts_complete (Manager Error): {error}")
            return

        # Delegiert das UI-Update zurück an den TabManager
        print("[AdminTabDataLoader] Empfange Tab-Titel-Zähler. Aktualisiere UI...")
        self.tab_manager.update_tab_titles_ui(result)

    # --- 2. Logik für Global Cache Refresh (Alle Tabs aktualisieren) ---

    def start_refresh_all_tabs(self):
        """Startet das Neuladen der globalen Caches in einem Thread."""
        print("[AdminTabDataLoader] Starte Thread: Global Cache Refresh...")
        self.thread_manager.start_worker(
            self._fetch_global_caches_thread,
            self._on_global_caches_refreshed_ui
        )

    def _fetch_global_caches_thread(self):
        """
        [LÄUFT IM THREAD]
        Holt alle Daten für die globalen Caches (blockierend).
        """
        print("[Thread-AdminData] Aktualisiere globale Caches im Bootloader...")
        try:
            caches = {}
            caches['user_cache'] = get_all_users()
            caches['dog_cache'] = get_all_dogs()
            caches['pending_wishes_cache'] = get_pending_wunschfrei_requests()
            caches['pending_vacations_count'] = get_pending_vacation_requests_count()
            caches['open_bugs_count'] = get_open_bug_reports_count()
            caches['open_tasks_count'] = get_open_tasks_count()
            return caches
        except Exception as e:
            print(f"[FEHLER] beim Aktualisieren der globalen Caches (Thread): {e}")
            return e

    def _on_global_caches_refreshed_ui(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback, wenn die Caches neu geladen wurden.
        """
        if not self.admin_window.winfo_exists():
            return

        if error:
            print(f"[FEHLER] _on_global_caches_refreshed_ui (Manager Error): {error}")
            return
        if isinstance(result, Exception):
            print(f"[FEHLER] _on_global_caches_refreshed_ui (von Thread): {result}")
            return

        caches = result
        try:
            # 1. Caches im Bootloader (App) aktualisieren
            self.bootloader_app.global_user_cache = caches.get('user_cache', [])
            self.bootloader_app.global_dog_cache = caches.get('dog_cache', [])
            self.bootloader_app.global_pending_wishes_cache = caches.get('pending_wishes_cache', [])
            self.bootloader_app.global_pending_vacations_count = caches.get('pending_vacations_count', 0)
            self.bootloader_app.global_open_bugs_count = caches.get('open_bugs_count', 0)
            self.bootloader_app.global_open_tasks_count = caches.get('open_tasks_count', 0)
            print("[DEBUG] Globale Caches aktualisiert (via AdminTabDataLoader).")

            # 2. Tab-Titel (Counts) im TabManager aktualisieren
            counts_for_titles = {
                "Wunschanfragen": len(self.bootloader_app.global_pending_wishes_cache),
                "Urlaubsanträge": self.bootloader_app.global_pending_vacations_count,
                "Bug-Reports": self.bootloader_app.global_open_bugs_count,
                "Aufgaben": self.bootloader_app.global_open_tasks_count,
                "Mitarbeiter": 0  # Zähler fehlt
            }
            self.tab_manager.update_tab_titles_ui(counts_for_titles)

            # 3. Geladene Tabs im TabManager aktualisieren (Refresh)
            # (Der TabManager wird angewiesen, seine geladenen Tabs zu aktualisieren)
            self.tab_manager.refresh_all_loaded_tabs_from_cache()

            # 4. Header etc. aktualisieren (über NotificationManager)
            if hasattr(self.admin_window, 'notification_manager'):
                self.admin_window.notification_manager.check_for_updates_threaded()

            print("[DEBUG] Refresh aller geladenen Tabs abgeschlossen (initiiert von AdminTabDataLoader).")

        except Exception as e:
            print(f"[FEHLER] beim Anwenden der globalen Caches (AdminTabDataLoader): {e}")