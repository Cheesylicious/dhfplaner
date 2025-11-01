# gui/admin_window/admin_tab_manager.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from queue import Queue, Empty

# --- TAB-KLASSEN IMPORTIEREN ---
from ..tabs.shift_plan_tab import ShiftPlanTab
from ..tabs.user_management_tab import UserManagementTab
from ..tabs.dog_management_tab import DogManagementTab
from ..tabs.shift_types_tab import ShiftTypesTab
from ..tabs.requests_tab import RequestsTab
# --- KORREKTUR: Import für LogTab auskommentiert (behebt ModuleNotFoundError) ---
# (Da die Datei log_tab.py in Ihrem Setup Probleme macht)
# from ..tabs.log_tab import LogTab
# --- ENDE KORREKTUR ---
from ..tabs.bug_reports_tab import BugReportsTab
from ..tabs.tasks_tab import TasksTab  # <-- HINZUGEFÜGT
from ..tabs.vacation_requests_tab import VacationRequestsTab
from ..tabs.request_lock_tab import RequestLockTab
from ..tabs.user_tab_settings_tab import UserTabSettingsTab
from ..tabs.participation_tab import ParticipationTab
from ..tabs.protokoll_tab import ProtokollTab
from ..tabs.chat_tab import ChatTab
from ..tabs.password_reset_requests_window import PasswordResetRequestsWindow
from ..tabs.settings_tab import SettingsTab


# --- KORREKTUR: DB-IMPORTE FÜR TAB-TITEL SIND NICHT MEHR NÖTIG (Regel 2) ---
# (Wir nutzen jetzt die globalen Caches aus dem Bootloader)
# from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
# from database.db_reports import get_open_bug_reports_count

# --- NEU: Import für Task-Zähler (wird für Bootloader-Cache benötigt) ---
try:
    from database.db_tasks import get_open_tasks_count
except ImportError:
    print("[WARNUNG] db_tasks.get_open_tasks_count nicht gefunden. Tab-Titel für Aufgaben wird nicht aktualisiert.")
    def get_open_tasks_count(): return 0
# --- ENDE NEU ---


class AdminTabManager:
    def __init__(self, admin_window, notebook):
        """
        Manager für das Lazy Loading und die Verwaltung der Notebook-Tabs.

        :param admin_window: Die Instanz von MainAdminWindow.
        :param notebook: Die Instanz von ttk.Notebook.
        """
        self.admin_window = admin_window
        self.notebook = notebook
        self.user_data = admin_window.user_data

        # --- LAZY LOADING SETUP ---
        self.tab_definitions = {
            "Schichtplan": ShiftPlanTab,
            "Chat": ChatTab,
            "Teilnahmen": ParticipationTab,
            "Mitarbeiter": UserManagementTab,
            "Diensthunde": DogManagementTab,
            "Schichtarten": ShiftTypesTab,
            "Wunschanfragen": RequestsTab,
            "Urlaubsanträge": VacationRequestsTab,
            "Bug-Reports": BugReportsTab,
            "Aufgaben": TasksTab,  # <-- HINZUGEFÜGT
            # --- KORREKTUR: LogTab aus den Definitionen entfernt ---
            # "Logs": LogTab,
            # --- ENDE KORREKTUR ---
            "Protokoll": ProtokollTab,
            "Wartung": SettingsTab,
            "Dummy": None
        }

        self.tab_frames = {}  # Speichert Referenzen auf die Tab-Widgets (Platzhalter oder echt)
        self.loaded_tabs = set()  # Namen der Tabs, die bereits geladen wurden

        # --- Threading für Tabs ---
        self.loading_tabs = set()
        self.tab_load_queue = Queue()
        self.tab_load_checker_running = False

    def setup_lazy_tabs(self):
        """Erstellt die Platzhalter-Tabs im Notebook."""
        print("[DEBUG] AdminTabManager.setup_lazy_tabs: Erstelle Platzhalter...")
        i = 0
        for tab_name, TabClass in self.tab_definitions.items():
            placeholder_frame = ttk.Frame(self.notebook, padding=20)
            self.notebook.add(placeholder_frame, text=tab_name)
            self.tab_frames[tab_name] = placeholder_frame  # Speichert initial den Platzhalter
            if TabClass is None:
                try:
                    self.notebook.tab(i, state='disabled')
                    print(f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' (Index {i}) deaktiviert.")
                except tk.TclError as e:
                    print(f"[FEHLER] setup_lazy_tabs: Konnte Tab '{tab_name}' nicht deaktivieren: {e}")
            i += 1

        # --- KORREKTUR: update_tab_titles() aufrufen, NACHDEM Platzhalter erstellt wurden ---
        self.update_tab_titles()  # Aktualisiert Titel basierend auf globalem Cache
        # --- ENDE KORREKTUR ---

    def on_tab_changed(self, event):
        """Startet den Lade-Thread für den ausgewählten Tab, falls noch nicht geladen."""
        try:
            selected_tab_id = self.notebook.select()
            if not selected_tab_id: return
            tab_index = self.notebook.index(selected_tab_id)
            current_widget_at_index = self.notebook.nametowidget(selected_tab_id)

            tab_info = self.notebook.tab(tab_index)
            if not tab_info: return
            tab_name_with_count = tab_info.get("text", "")
            tab_name = tab_name_with_count.split(" (")[0]  # Basisname

            print(f"[GUI-Admin] on_tab_changed: Zu Tab '{tab_name}' gewechselt.")

            # --- KORREKTUR: Verwende die globalen Caches, wenn der Tab geladen wird (Regel 2) ---
            # (Stellt sicher, dass die Tabs beim Laden die vorgeladenen Daten nutzen)
            bootloader_app = self.admin_window.app

            # (Diese Logik setzt voraus, dass die Tabs einen __init__(master, app, optional_data=None) akzeptieren)

            # WICHTIG: Wir laden diese Tabs jetzt im THREAD (siehe _load_tab_threaded)
            # damit die UI nicht blockiert, falls der Konstruktor der Tabs doch Arbeit verrichtet.

            # --- ENDE KORREKTUR ---

            if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
                print(f"[GUI-Admin] -> Tab '{tab_name}' ist bereits geladen oder wird geladen. Keine Aktion.")
                return

            if tab_name not in self.tab_definitions or self.tab_definitions[tab_name] is None:
                print(f"[GUI-Admin] -> Keine Definition für Tab '{tab_name}'. Keine Aktion.")
                return

            print(f"[GUI-Admin] -> Starte Ladevorgang für {tab_name} (Threaded)")
            TabClass = self.tab_definitions[tab_name]
            placeholder_frame = self.tab_frames.get(tab_name)

            if not placeholder_frame or not placeholder_frame.winfo_exists():
                print(f"[GUI-Admin] FEHLER: Platzhalter-Frame für '{tab_name}' nicht gefunden oder bereits zerstört.")
                return

            is_placeholder = (placeholder_frame == current_widget_at_index)
            if is_placeholder:
                print(f"[GUI-Admin] -> Zeige Ladeanzeige in Platzhalter für '{tab_name}'.")
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16)).pack(expand=True,
                                                                                                     anchor="center")
                self.admin_window.update_idletasks()

            self.loading_tabs.add(tab_name)

            threading.Thread(
                target=self._load_tab_threaded,
                args=(tab_name, TabClass, tab_index),
                daemon=True
            ).start()

            if not self.tab_load_checker_running:
                print("[GUI-Checker-Admin] Starte Checker-Loop.")
                self.tab_load_checker_running = True
                self.admin_window.after(50, self._check_tab_load_queue)

        except (tk.TclError, IndexError) as e:
            print(f"[GUI-Admin] Fehler beim Ermitteln des Tabs in on_tab_changed: {e}")
        except Exception as e:
            print(f"[GUI-Admin] Unerwarteter Fehler in on_tab_changed: {e}")

    def _replace_placeholder(self, tab_name, real_tab, tab_index, placeholder_frame):
        """Hilfsfunktion, um einen Platzhalter synchron zu ersetzen."""
        try:
            self.notebook.unbind("<<NotebookTabChanged>>")
            tab_options = self.notebook.tab(placeholder_frame)
            self.notebook.forget(placeholder_frame)
            self.notebook.insert(tab_index, real_tab, **tab_options)
            self.notebook.select(real_tab)
            self.loaded_tabs.add(tab_name)
            self.tab_frames[tab_name] = real_tab
            print(f"[GUI-Admin] Tab '{tab_name}' (aus Cache) erfolgreich eingesetzt.")
        except tk.TclError as e:
            print(f"[GUI-Admin] TclError beim Einsetzen von {tab_name}: {e}")
        finally:
            self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """Lädt einen Tab im Hintergrund-Thread."""
        try:
            print(f"[Thread-Admin] Lade Tab: {tab_name}...")
            real_tab = None
            # Übergib self.admin_window (MainAdminWindow) als 'admin_window'
            admin_window_ref = self.admin_window

            # --- NEU: Datenübergabe an Tabs, die es unterstützen (Regel 2) ---
            bootloader_app = self.admin_window.app

            # (Wir nehmen an, dass die Konstruktoren (master, app, optional_data=None) akzeptieren)
            # (Falls nicht, müssen die Konstruktoren der Tabs angepasst werden)
            if TabClass.__name__ == "UserManagementTab":
                print("[Thread-Admin] Injiziere global_user_cache in UserManagementTab...")
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_user_cache)
            elif TabClass.__name__ == "DogManagementTab":
                print("[Thread-Admin] Injiziere global_dog_cache in DogManagementTab...")
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_dog_cache)
            elif TabClass.__name__ == "RequestsTab":
                print("[Thread-Admin] Injiziere global_pending_wishes_cache in RequestsTab...")
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_pending_wishes_cache)
            elif TabClass.__name__ == "VacationRequestsTab":
                print("[Thread-Admin] Injiziere global_pending_vacations_count in VacationRequestsTab...")
                # KORREKTUR: Übergibt den ZÄHLER (wie im Bootloader definiert)
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_pending_vacations_count)
            # --- ENDE NEU ---

            elif TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, admin_window_ref)
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.user_data)
            else:
                try:
                    # Die meisten Tabs erwarten (master, admin_window)
                    # TasksTab fällt hier hinein und wird korrekt initialisiert.
                    real_tab = TabClass(self.notebook, admin_window_ref)
                except Exception as e1:
                    print(
                        f"[Thread-Admin] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:
                        # Fallback für Tabs, die nur (master) erwarten (z.B. alte Tabs)
                        real_tab = TabClass(self.notebook)
                    except Exception as e2:
                        print(f"[Thread-Admin] FEHLER: {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise

            self.tab_load_queue.put((tab_name, real_tab, tab_index))
            print(f"[Thread-Admin] Tab '{tab_name}' fertig geladen.")
        except Exception as e:
            print(f"[Thread-Admin] FEHLER beim Laden von Tab '{tab_name}': {e}")
            import traceback
            traceback.print_exc()
            self.tab_load_queue.put((tab_name, e, tab_index))

    def _check_tab_load_queue(self):
        """Prüft die Queue und fügt geladene Tabs im GUI-Thread ein."""
        tab_name_processed = None
        try:
            result = self.tab_load_queue.get_nowait()
            tab_name, real_tab_or_exception, tab_index = result
            tab_name_processed = tab_name

            print(f"[GUI-Checker-Admin] Empfange Ergebnis für: {tab_name}")

            placeholder_frame = self.tab_frames.get(tab_name)
            if not placeholder_frame or not placeholder_frame.winfo_exists():
                print(f"[GUI-Checker-Admin] FEHLER: Platzhalter für {tab_name} existiert nicht mehr.")
                return

            for widget in placeholder_frame.winfo_children():
                if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                    widget.destroy()
                    break

            if isinstance(real_tab_or_exception, Exception):
                e = real_tab_or_exception
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
                print(f"[GUI-Checker-Admin] Fehler beim Laden von Tab '{tab_name}' angezeigt.")
            else:
                real_tab = real_tab_or_exception
                self._replace_placeholder(tab_name, real_tab, tab_index, placeholder_frame)

        except Empty:
            pass
        except Exception as e:
            print(f"[GUI-Checker-Admin] Unerwarteter Fehler in _check_tab_load_queue: {e}")
        finally:
            if tab_name_processed and tab_name_processed in self.loading_tabs:
                self.loading_tabs.remove(tab_name_processed)

            if not self.tab_load_queue.empty() or self.loading_tabs:
                self.admin_window.after(100, self._check_tab_load_queue)
            else:
                self.tab_load_checker_running = False
                print("[GUI-Checker-Admin] Keine Tabs mehr in Queue oder am Laden. Checker pausiert.")

    def _load_tab_directly(self, tab_name, tab_index):
        """(Wird nicht mehr direkt verwendet, bleibt als Fallback)"""
        # (Implementierung von früher hier...)
        pass

    def update_single_tab_text(self, tab_name, new_text):
        """Aktualisiert den Text eines Tabs anhand seines Basisnamens."""
        widget_ref = self.tab_frames.get(tab_name)
        if widget_ref and widget_ref.winfo_exists():
            try:
                # Prüfe, ob das Widget (Platzhalter ODER echter Tab) ein Kind des Notebooks ist
                if self.notebook.nametowidget(widget_ref.winfo_parent()) == self.notebook:
                    self.notebook.tab(widget_ref, text=new_text)
                else:
                    print(f"[DEBUG] update_single_tab_text: Frame für {tab_name} ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name}: {e}")

    def update_tab_titles(self):
        """
        Aktualisiert die Titel von Tabs, die Zähler anzeigen.
        NUTZT JETZT DIE VORGELADENEN CACHES VOM BOOTLOADER.
        """
        print("[DEBUG] AdminTabManager.update_tab_titles (nutzt globalen Cache)...")
        try:
            # Greife auf den Bootloader (app) über das AdminFenster zu
            bootloader_app = self.admin_window.app

            # 1. Wunschanfragen (nutzt Cache)
            pending_wunsch_count = len(bootloader_app.global_pending_wishes_cache)
            tab_text_wunsch = "Wunschanfragen" + (f" ({pending_wunsch_count})" if pending_wunsch_count > 0 else "")
            self.update_single_tab_text("Wunschanfragen", tab_text_wunsch)

            # 2. Urlaubsanträge (nutzt Cache)
            # KORREKTUR: Verwendet die Variable _count aus dem Bootloader
            pending_urlaub_count = bootloader_app.global_pending_vacations_count
            tab_text_urlaub = "Urlaubsanträge" + (f" ({pending_urlaub_count})" if pending_urlaub_count > 0 else "")
            self.update_single_tab_text("Urlaubsanträge", tab_text_urlaub)

            # 3. Bug-Reports (nutzt Cache)
            open_bug_count = bootloader_app.global_open_bugs_count
            tab_text_bugs = "Bug-Reports" + (f" ({open_bug_count})" if open_bug_count > 0 else "")
            self.update_single_tab_text("Bug-Reports", tab_text_bugs)

            # 4. Aufgaben (nutzt Cache, falls vorhanden)
            if hasattr(bootloader_app, 'global_open_tasks_count'):
                open_tasks_count = bootloader_app.global_open_tasks_count
                tab_text_tasks = "Aufgaben" + (f" ({open_tasks_count})" if open_tasks_count > 0 else "")
                self.update_single_tab_text("Aufgaben", tab_text_tasks)

        except AttributeError as e:
            print(
                f"[FEHLER] Konnte nicht auf globalen Cache im Bootloader zugreifen: {e} (Möglicherweise noch nicht initialisiert?)")
        except Exception as e:
            print(f"[FEHLER] Konnte Tab-Titel nicht aktualisieren: {e}")
            self.update_single_tab_text("Wunschanfragen", "Wunschanfragen (?)")
            self.update_single_tab_text("Urlaubsanträge", "Urlaubsanträge (?)")
            self.update_single_tab_text("Bug-Reports", "Bug-Reports (?)")
            self.update_single_tab_text("Aufgaben", "Aufgaben (?)")  # <-- HINZUGEFÜGT

    def switch_to_tab(self, tab_name):
        """Wechselt zum Tab mit dem gegebenen Namen (Basisname ohne Zähler)."""
        widget_ref = self.tab_frames.get(tab_name)
        if widget_ref and widget_ref.winfo_exists():
            try:
                if self.notebook.nametowidget(widget_ref.winfo_parent()) == self.notebook:
                    print(f"[DEBUG] switch_to_tab: Wechsle zu Tab '{tab_name}'...")
                    self.notebook.select(widget_ref)
                else:
                    print(f"[DEBUG] switch_to_tab: Frame für '{tab_name}' ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                print(f"[DEBUG] switch_to_tab: Fehler beim Auswählen von '{tab_name}': {e}")
        else:
            print(f"[DEBUG] switch_to_tab: Tab/Frame '{tab_name}' nicht gefunden oder zerstört.")

    def _load_dynamic_tab(self, tab_name, TabClass, *args):
        """Lädt einen Tab dynamisch (synchron), der nicht in den Haupt-Definitionen ist."""
        # 1. Prüfen, ob Tab schon geladen und gültig ist
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                        print(f"[GUI - dyn] Tab '{tab_name}' bereits geladen und gültig. Wechsle...")
                        self.notebook.select(frame)
                        return
                except (tk.TclError, KeyError):
                    print(f"[GUI - dyn] Tab '{tab_name}' war geladen, aber Widget ungültig. Lade neu.")
                    pass
            if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
            if tab_name in self.tab_frames: del self.tab_frames[tab_name]

        if tab_name in self.loading_tabs:
            print(f"[GUI - dyn] WARNUNG: {tab_name} lädt bereits. Breche ab.")
            return

        # 3. Ladevorgang starten (synchron)
        print(f"[LazyLoad] Lade dynamischen Tab: {tab_name} (im GUI-Thread)")
        self.loading_tabs.add(tab_name)

        placeholder_frame = ttk.Frame(self.notebook, padding=20)
        loading_label = ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16))
        loading_label.pack(expand=True, anchor="center")
        tab_index = -1
        try:
            self.notebook.unbind("<<NotebookTabChanged>>")
            self.notebook.add(placeholder_frame, text=tab_name)
            self.notebook.select(placeholder_frame)
            tab_index = self.notebook.index(placeholder_frame)
        finally:
            self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.admin_window.update_idletasks()

        real_tab = None
        try:
            admin_window_ref = self.admin_window

            if TabClass.__name__ == "UserTabSettingsTab":
                real_tab = TabClass(self.notebook, *args)
            elif TabClass.__name__ in ["RequestLockTab", "PasswordResetRequestsWindow"]:
                real_tab = TabClass(self.notebook, admin_window_ref, *args)  # Übergib admin_window
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.user_data)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, admin_window_ref)
            else:
                print(f"[WARNUNG] _load_dynamic_tab: Unbekannter Typ {TabClass.__name__}, versuche mit (master).")
                try:
                    real_tab = TabClass(self.notebook)  # Fallback 1
                except TypeError:
                    print(f"[FEHLER] _load_dynamic_tab: {TabClass.__name__} konnte nicht initialisiert werden.")
                    raise

            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)
                if real_tab and tab_options and tab_index != -1:
                    try:
                        self.notebook.unbind("<<NotebookTabChanged>>")
                        self.notebook.forget(placeholder_frame)
                        self.notebook.insert(tab_index if tab_index < self.notebook.index('end') else 'end', real_tab,
                                             **tab_options)
                        self.notebook.select(real_tab)
                    finally:
                        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

                    self.loaded_tabs.add(tab_name)
                    self.tab_frames[tab_name] = real_tab
                    print(f"[GUI] Dynamischer Tab '{tab_name}' erfolgreich eingesetzt.")
                else:
                    raise Exception("Konnte dyn. Tab-Objekt, Optionen oder Index nicht ermitteln.")
            else:
                raise tk.TclError(f"Platzhalter für dyn. Tab {tab_name} existierte nicht mehr beim Ersetzen.")

        except Exception as e:
            print(f"[GUI] FEHLER beim Laden/Einfügen von dynamischem Tab '{tab_name}': {e}")
            if placeholder_frame and placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
            else:
                print(
                    f"[GUI] FEHLER: Platzhalter für {tab_name} existierte nicht mehr bei Fehlerbehandlung (dyn. Tab).")
                messagebox.showerror("Fehler beim Laden", f"Konnte Tab '{tab_name}' nicht laden:\n{e}",
                                     parent=self.admin_window)
        finally:
            if tab_name in self.loading_tabs:
                self.loading_tabs.remove(tab_name)

    # --- Refresh-Funktionen ---

    def refresh_all_tabs(self):
        """Lädt alle Basisdaten neu und aktualisiert alle BEREITS GELADENEN Tabs."""
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs...")

        # 1. Daten neu laden (über den DataManager)
        # HINWEIS: Wir müssen die globalen Caches im Bootloader aktualisieren
        bootloader_app = self.admin_window.app
        try:
            print("[DEBUG] Aktualisiere globale Caches im Bootloader...")
            # --- KORREKTUR: DB-Funktionen direkt aufrufen (wie im Bootloader) ---
            from database.db_users import get_all_users
            from database.db_dogs import get_all_dogs
            from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
            from database.db_reports import get_open_bug_reports_count
            # HINWEIS: get_open_tasks_count wird bereits oben global importiert (Regel 1)

            bootloader_app.global_user_cache = get_all_users()
            bootloader_app.global_dog_cache = get_all_dogs()
            bootloader_app.global_pending_wishes_cache = get_pending_wunschfrei_requests()
            bootloader_app.global_pending_vacations_count = get_pending_vacation_requests_count()  # KORRIGIERT
            bootloader_app.global_open_bugs_count = get_open_bug_reports_count()
            bootloader_app.global_open_tasks_count = get_open_tasks_count()  # <-- HINZUGEFÜGT
            print("[DEBUG] Globale Caches aktualisiert.")
        except Exception as e:
            print(f"[FEHLER] beim Aktualisieren der globalen Caches: {e}")
            # (Fahre trotzdem fort, um die Tabs zu aktualisieren)

        # 2. Tab-Titel aktualisieren (jetzt mit den neuen Cache-Daten)
        self.update_tab_titles()

        # 3. Geladene Tabs aktualisieren
        loaded_tab_names = list(self.loaded_tabs)
        print(f"[DEBUG] Geladene Tabs für Refresh: {loaded_tab_names}")

        for tab_name in loaded_tab_names:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    parent_is_notebook = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if parent_is_notebook:
                        self._refresh_frame(frame, tab_name)
                except (tk.TclError, KeyError) as e:
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
                except Exception as e:
                    print(f"[FEHLER] Unerwarteter Fehler beim Refresh von Tab '{tab_name}': {e}")
            else:
                print(
                    f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                if tab_name in self.tab_frames: del self.tab_frames[tab_name]

        # Header etc. aktualisieren (über NotificationManager)
        if hasattr(self.admin_window, 'notification_manager'):
            self.admin_window.notification_manager.check_for_updates()
        print("[DEBUG] Refresh aller geladenen Tabs abgeschlossen.")

    def refresh_shift_plan(self):
        """Aktualisiert nur den Schichtplan-Tab (falls geladen)."""
        self.refresh_specific_tab("Schichtplan")

    def refresh_specific_tab(self, tab_name):
        """Aktualisiert einen spezifischen Tab, falls er geladen ist."""
        print(f"[DEBUG] refresh_specific_tab angefordert für: '{tab_name}'")
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    parent_is_notebook = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if parent_is_notebook:
                        self._refresh_frame(frame, tab_name)
                except (tk.TclError, KeyError) as e:
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
                except Exception as e:
                    print(f"[FEHLER] Unerwarteter Fehler während des Refresh von Tab '{tab_name}': {e}")
            else:
                print(
                    f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                if tab_name in self.tab_frames: del self.tab_frames[tab_name]
        else:
            print(f"[DEBUG] Tab '{tab_name}' ist nicht geladen, kein Refresh nötig.")

    def _refresh_frame(self, frame, tab_name):
        """Hilfsfunktion zum Aufrufen der korrekten Refresh-Methode für ein Frame."""
        refreshed = False

        # --- KORREKTUR: Spezifische Datenübergabe für vorgeladene Tabs ---
        bootloader_app = self.admin_window.app
        if tab_name == "Mitarbeiter" and hasattr(frame, 'refresh_data'):
            print(f"[DEBUG] -> rufe refresh_data(global_user_cache) für {tab_name} auf")
            # Annahme: refresh_data() in UserManagementTab kann optional Daten annehmen
            frame.refresh_data(bootloader_app.global_user_cache)
            refreshed = True
        elif tab_name == "Diensthunde" and hasattr(frame, 'refresh_data'):
            print(f"[DEBUG] -> rufe refresh_data(global_dog_cache) für {tab_name} auf")
            frame.refresh_data(bootloader_app.global_dog_cache)
            refreshed = True
        elif tab_name == "Wunschanfragen" and hasattr(frame, 'refresh_data'):
            print(f"[DEBUG] -> rufe refresh_data(global_pending_wishes_cache) für {tab_name} auf")
            frame.refresh_data(bootloader_app.global_pending_wishes_cache)
            refreshed = True
        elif tab_name == "Urlaubsanträge" and hasattr(frame, 'refresh_data'):
            print(f"[DEBUG] -> rufe refresh_data(global_pending_vacations_count) für {tab_name} auf")
            frame.refresh_data(bootloader_app.global_pending_vacations_count)  # Übergibt den Zähler
            refreshed = True
        # --- ENDE KORREKTUR ---

        elif hasattr(frame, 'refresh_data'):
            print(f"[DEBUG] -> rufe refresh_data() für {tab_name} auf")
            # TasksTab fällt hier hinein und ruft sein eigenes refresh_data() ohne Argumente auf.
            frame.refresh_data()
            refreshed = True
        elif hasattr(frame, 'refresh_plan'):
            print(f"[DEBUG] -> rufe refresh_plan() für {tab_name} auf")
            frame.refresh_plan()
            refreshed = True
        elif hasattr(frame, 'load_data'):
            print(f"[DEBUG] -> rufe load_data() für {tab_name} auf")
            frame.load_data()
            refreshed = True

        if not refreshed:
            print(
                f"[WARNUNG] Tab '{tab_name}' hat keine bekannte Refresh-Methode (refresh_data, refresh_plan, load_data).")

    def refresh_antragssperre_views(self):
        """ Aktualisiert Ansichten, die von der Antragssperre betroffen sind. """
        print("[DEBUG] refresh_antragssperre_views aufgerufen.")

        # 1. Schichtplan-Tab
        if "Schichtplan" in self.loaded_tabs:
            plan_tab = self.tab_frames.get("Schichtplan")
            if plan_tab and plan_tab.winfo_exists() and hasattr(plan_tab, 'update_lock_status'):
                try:
                    print("[DEBUG] -> Aktualisiere Sperrstatus im Schichtplan-Tab.")
                    plan_tab.update_lock_status()
                except Exception as e:
                    print(f"[FEHLER] bei plan_tab.update_lock_status: {e}")

        # 2. Antragssperre-Tab
        if "Antragssperre" in self.loaded_tabs:
            lock_tab = self.tab_frames.get("Antragssperre")
            if lock_tab and lock_tab.winfo_exists() and hasattr(lock_tab, 'load_locks_for_year'):
                try:
                    print("[DEBUG] -> Lade Sperren neu im Antragssperre-Tab.")
                    lock_tab.load_locks_for_year()
                except Exception as e:
                    print(f"[FEHLER] bei lock_tab.load_locks_for_year: {e}")