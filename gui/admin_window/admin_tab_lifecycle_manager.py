# gui/admin_window/admin_tab_lifecycle_manager.py
# NEU: Ausgelagerte GUI-Logik für Laden, Ersetzen und Aktualisieren von Admin-Tabs

import tkinter as tk
from tkinter import ttk, messagebox

# Importiert die Tab-Klassen (wird für die Typprüfung und Initialisierung benötigt)
from ..tabs.shift_plan_tab import ShiftPlanTab
from ..tabs.user_management_tab import UserManagementTab
from ..tabs.dog_management_tab import DogManagementTab
from ..tabs.shift_types_tab import ShiftTypesTab
from ..tabs.requests_tab import RequestsTab
from ..tabs.bug_reports_tab import BugReportsTab
from ..tabs.tasks_tab import TasksTab
from ..tabs.vacation_requests_tab import VacationRequestsTab
from ..tabs.request_lock_tab import RequestLockTab
from ..tabs.user_tab_settings_tab import UserTabSettingsTab
from ..tabs.participation_tab import ParticipationTab
from ..tabs.protokoll_tab import ProtokollTab
from ..tabs.chat_tab import ChatTab
from ..tabs.password_reset_requests_window import PasswordResetRequestsWindow
from ..tabs.settings_tab import SettingsTab


class AdminTabLifecycleManager:
    """
    Diese Klasse verwaltet den gesamten GUI-Lebenszyklus der Admin-Tabs:
    1. Threaded Loading (Lazy Loading)
    2. Synchronous Loading (Dynamic Tabs)
    3. GUI-Refresh (Aktualisierung geladener Tabs)
    """

    def __init__(self, admin_window, notebook, tab_manager_ref):
        self.admin_window = admin_window
        self.notebook = notebook
        self.thread_manager = admin_window.thread_manager

        # Referenzen auf den Haupt-Manager (für Caches und Status)
        self.tab_manager = tab_manager_ref

        # Aliase für die Status-Listen (LifecycleManager verwaltet sie)
        self.tab_frames = self.tab_manager.tab_frames
        self.loaded_tabs = self.tab_manager.loaded_tabs
        self.loading_tabs = self.tab_manager.loading_tabs

    def preload_tab(self, tab_name, tab_index=None, force_select=False):
        """
        Löst das Laden eines Tabs aus, wenn er noch nicht geladen ist.
        (Diese Funktion ist der Einstiegspunkt für das Lazy Loading)
        """
        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
            if not force_select:
                print(f"[Lifecycle] -> Tab '{tab_name}' ist bereits geladen oder wird geladen. Keine Aktion.")
            return

        if tab_name not in self.tab_manager.tab_definitions or self.tab_manager.tab_definitions[tab_name] is None:
            if not force_select:
                print(f"[Lifecycle] -> Keine Definition für Tab '{tab_name}'. Keine Aktion.")
            return

        print(f"[Lifecycle] -> Starte Ladevorgang für {tab_name} (Threaded)")
        TabClass = self.tab_manager.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames.get(tab_name)

        if not placeholder_frame or not placeholder_frame.winfo_exists():
            print(f"[Lifecycle] FEHLER: Platzhalter-Frame für '{tab_name}' nicht gefunden oder bereits zerstört.")
            return

        if tab_index is None:
            try:
                tab_index = self.notebook.index(placeholder_frame)
            except tk.TclError:
                print(f"[Lifecycle] FEHLER: Konnte Index für Platzhalter {tab_name} nicht finden.")
                return

        if force_select:
            try:
                current_widget_at_index = self.notebook.nametowidget(self.notebook.select())
                is_placeholder = (placeholder_frame == current_widget_at_index)
                if is_placeholder:
                    print(f"[Lifecycle] -> Zeige Ladeanzeige in Platzhalter für '{tab_name}'.")
                    for widget in placeholder_frame.winfo_children(): widget.destroy()
                    ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16)).pack(expand=True,
                                                                                                         anchor="center")
                    self.admin_window.update_idletasks()
            except tk.TclError:
                pass

        self.loading_tabs.add(tab_name)

        # Starte den Worker-Thread
        self.thread_manager.start_worker(
            self._load_tab_threaded,  # target_func
            self._check_tab_load_queue,  # on_complete
            tab_name,  # *args[0]
            TabClass,  # *args[1]
            tab_index  # *args[2]
        )

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """
        [LÄUFT IM THREAD]
        Erstellt die Tab-Instanz im Hintergrund.
        """
        try:
            print(f"[Thread-Lifecycle] Lade Tab: {tab_name}...")
            real_tab = None
            admin_window_ref = self.admin_window
            bootloader_app = self.admin_window.app

            # Injektionslogik
            if TabClass.__name__ == "UserManagementTab":
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_user_cache)
            elif TabClass.__name__ == "DogManagementTab":
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_dog_cache)
            elif TabClass.__name__ == "RequestsTab":
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_pending_wishes_cache)
            elif TabClass.__name__ == "VacationRequestsTab":
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_pending_vacations_count)
            elif TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, admin_window_ref)
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook,
                                    self.admin_window.user_data)  # user_data direkt von admin_window holen
            else:
                # Standard-Initialisierung (für die meisten Tabs)
                try:
                    real_tab = TabClass(self.notebook, admin_window_ref)
                except Exception as e1:
                    print(
                        f"[Thread-Lifecycle] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:
                        real_tab = TabClass(self.notebook)
                    except Exception as e2:
                        print(f"[Thread-Lifecycle] FEHLER: {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise

            return (tab_name, real_tab, tab_index)

        except Exception as e:
            print(f"[Thread-Lifecycle] FEHLER beim Laden von Tab '{tab_name}': {e}")
            import traceback
            traceback.print_exc()
            return (tab_name, e, tab_index)

    def _check_tab_load_queue(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback vom ThreadManager, wenn ein Tab geladen ist.
        """
        tab_name_processed = None
        try:
            if error:
                print(f"[GUI-Lifecycle] ThreadManager-Fehler: {error}")
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    tab_name_processed = result[0]
                return

            tab_name, real_tab_or_exception, tab_index = result
            tab_name_processed = tab_name
            print(f"[GUI-Lifecycle] Empfange Ergebnis für: {tab_name}")

            placeholder_frame = self.tab_frames.get(tab_name)
            if not placeholder_frame or not placeholder_frame.winfo_exists():
                print(f"[GUI-Lifecycle] FEHLER: Platzhalter für {tab_name} existiert nicht mehr.")
                return

            # Lade-Label entfernen
            for widget in placeholder_frame.winfo_children():
                if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                    widget.destroy()
                    break

            if isinstance(real_tab_or_exception, Exception):
                e = real_tab_or_exception
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
                print(f"[GUI-Lifecycle] Fehler beim Laden von Tab '{tab_name}' angezeigt.")
            else:
                # Erfolgreich geladen -> Platzhalter ersetzen
                real_tab = real_tab_or_exception
                try:
                    current_tab_index = self.notebook.index(placeholder_frame)
                    self._replace_placeholder(tab_name, real_tab, current_tab_index, placeholder_frame)
                except tk.TclError:
                    print(f"[GUI-Lifecycle] Platzhalter {tab_name} nicht mehr im Notebook. Setze an Ende.")
                    self._replace_placeholder(tab_name, real_tab, 'end', placeholder_frame)

        except Exception as e:
            print(f"[GUI-Lifecycle] Unerwarteter Fehler in _check_tab_load_queue: {e}")
        finally:
            if tab_name_processed and tab_name_processed in self.loading_tabs:
                self.loading_tabs.remove(tab_name_processed)

    def _replace_placeholder(self, tab_name, real_tab, tab_index, placeholder_frame):
        """
        [LÄUFT IM GUI-THREAD]
        Hilfsfunktion, um einen Platzhalter synchron zu ersetzen.
        """
        try:
            is_preloading = False
            try:
                current_selected_index = self.notebook.index("current")
                if current_selected_index != tab_index:
                    is_preloading = True
                    print(f"[Lifecycle P2] Ersetze Platzhalter für '{tab_name}' im Hintergrund.")
            except Exception:
                is_preloading = False

            self.notebook.unbind("<<NotebookTabChanged>>")

            # Nutzt den Cache des Haupt-Managers
            current_count = self.tab_manager.last_tab_counts.get(tab_name, 0)
            tab_text = f"{tab_name} ({current_count})" if current_count > 0 else tab_name

            self.notebook.forget(placeholder_frame)
            self.notebook.insert(tab_index, real_tab, text=tab_text)

            if not is_preloading:
                self.notebook.select(real_tab)

            self.loaded_tabs.add(tab_name)
            self.tab_frames[tab_name] = real_tab  # Status-Listen aktualisieren
            print(f"[Lifecycle] Tab '{tab_name}' erfolgreich eingesetzt.")
        except tk.TclError as e:
            print(f"[Lifecycle] TclError beim Einsetzen von {tab_name}: {e}")
        finally:
            # Bind-Event gehört zum TabManager, nicht zum LifecycleManager
            self.tab_manager.bind_tab_change_event()

    def load_dynamic_tab(self, tab_name, TabClass, *args):
        """
        [LÄUFT IM GUI-THREAD]
        Lädt einen Tab dynamisch (synchron), der nicht in den Haupt-Definitionen ist.
        """

        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                        print(f"[Lifecycle - dyn] Tab '{tab_name}' bereits geladen und gültig. Wechsle...")
                        self.notebook.select(frame)
                        return
                except (tk.TclError, KeyError):
                    print(f"[Lifecycle - dyn] Tab '{tab_name}' war geladen, aber Widget ungültig. Lade neu.")
                    pass
            if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
            if tab_name in self.tab_frames: del self.tab_frames[tab_name]

        if tab_name in self.loading_tabs:
            print(f"[Lifecycle - dyn] WARNUNG: {tab_name} lädt bereits. Breche ab.")
            return

        print(f"[Lifecycle] Lade dynamischen Tab: {tab_name} (im GUI-Thread)")
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
            self.tab_manager.bind_tab_change_event()  # Event wieder an Haupt-Manager binden
        self.admin_window.update_idletasks()

        real_tab = None
        try:
            admin_window_ref = self.admin_window
            if TabClass.__name__ == "UserTabSettingsTab":
                real_tab = TabClass(self.notebook, *args)
            elif TabClass.__name__ in ["RequestLockTab"]:
                real_tab = TabClass(self.notebook, admin_window_ref, *args)
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.admin_window.user_data)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, admin_window_ref)
            else:
                # Standard-Initialisierung (z.B. PasswordResetRequestsWindow)
                real_tab = TabClass(self.notebook)

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
                        self.tab_manager.bind_tab_change_event()

                    self.loaded_tabs.add(tab_name)
                    self.tab_frames[tab_name] = real_tab
                    print(f"[Lifecycle] Dynamischer Tab '{tab_name}' erfolgreich eingesetzt.")
                else:
                    raise Exception("Konnte dyn. Tab-Objekt, Optionen oder Index nicht ermitteln.")
            else:
                raise tk.TclError(f"Platzhalter für dyn. Tab {tab_name} existierte nicht mehr beim Ersetzen.")

        except Exception as e:
            print(f"[Lifecycle] FEHLER beim Laden/Einfügen von dynamischem Tab '{tab_name}': {e}")
            if placeholder_frame and placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
            else:
                messagebox.showerror("Fehler beim Laden", f"Konnte Tab '{tab_name}' nicht laden:\n{e}",
                                     parent=self.admin_window)
        finally:
            if tab_name in self.loading_tabs:
                self.loading_tabs.remove(tab_name)

    def refresh_all_loaded_tabs_from_cache(self):
        """
        [LÄUFT IM GUI-THREAD]
        Wird vom Data Loader aufgerufen, NACHDEM die Caches aktualisiert wurden.
        Aktualisiert nur die GUI der bereits geladenen Tabs.
        """
        loaded_tab_names = list(self.loaded_tabs)
        print(f"[Lifecycle-Refresh] Geladene Tabs für Refresh (aus Cache): {loaded_tab_names}")

        for tab_name in loaded_tab_names:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    parent_is_notebook = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if parent_is_notebook:
                        self._refresh_frame(frame, tab_name)
                except (tk.TclError, KeyError) as e:
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
            else:
                print(
                    f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                if tab_name in self.tab_frames: del self.tab_frames[tab_name]

    def refresh_specific_tab(self, tab_name):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert einen spezifischen Tab, falls er geladen ist.
        """
        print(f"[Lifecycle-Refresh] refresh_specific_tab angefordert für: '{tab_name}'")
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    parent_is_notebook = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if parent_is_notebook:
                        self._refresh_frame(frame, tab_name)
                except (tk.TclError, KeyError) as e:
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
            else:
                print(
                    f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                if tab_name in self.tab_frames: del self.tab_frames[tab_name]
        else:
            print(f"[Lifecycle-Refresh] Tab '{tab_name}' ist nicht geladen, kein Refresh nötig.")

    def _refresh_frame(self, frame, tab_name):
        """
        [LÄUFT IM GUI-THREAD]
        Hilfsfunktion zum Aufrufen der korrekten Refresh-Methode für ein Frame.
        Greift auf den globalen Cache im Bootloader (App) zu.
        """
        refreshed = False
        bootloader_app = self.admin_window.app

        try:
            if tab_name == "Mitarbeiter" and hasattr(frame, 'refresh_data'):
                print(f"[DEBUG] -> rufe refresh_data(global_user_cache) für {tab_name} auf")
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
                frame.refresh_data(bootloader_app.global_pending_vacations_count)
                refreshed = True
            elif hasattr(frame, 'refresh_data'):
                print(f"[DEBUG] -> rufe refresh_data() für {tab_name} auf")
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
        except Exception as e:
            print(f"[FEHLER] _refresh_frame für {tab_name}: {e}")
            refreshed = False

        if not refreshed:
            print(
                f"[WARNUNG] Tab '{tab_name}' hat keine bekannte Refresh-Methode (refresh_data, refresh_plan, load_data).")