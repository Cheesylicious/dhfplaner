# gui/admin_window/admin_tab_manager.py
# BEREINIGTE VERSION: Dient als Controller.
# GUI-Logik (Lifecycle) und Daten-Logik (DataLoader) sind ausgelagert.

import tkinter as tk
from tkinter import ttk, messagebox

# --- TAB-KLASSEN IMPORTIEREN ---
# (Wird für die tab_definitions benötigt)
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

# --- NEU: Import der ausgelagerten Manager ---
from .admin_tab_data_loader import AdminTabDataLoader
from .admin_tab_lifecycle_manager import AdminTabLifecycleManager


class AdminTabManager:
    def __init__(self, admin_window, notebook):
        """
        Manager für das Lazy Loading und die Verwaltung der Notebook-Tabs.
        Diese Klasse dient als Haupt-Controller und delegiert die Arbeit.
        """
        self.admin_window = admin_window
        self.notebook = notebook
        self.user_data = admin_window.user_data
        self.thread_manager = self.admin_window.thread_manager

        # --- Status-Variablen (Shared State) ---
        # Diese werden von den Sub-Managern (mit)verwaltet
        self.tab_frames = {}
        self.loaded_tabs = set()
        self.loading_tabs = set()
        self.last_tab_counts = {}  # Cache für Zählerstände

        # --- Definitionen (Bleiben hier) ---
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
            "Aufgaben": TasksTab,
            # "Logs": LogTab, # Auskommentiert
            "Protokoll": ProtokollTab,
            "Wartung": SettingsTab,
            "Dummy": None
        }

        # --- NEU: Sub-Manager instanziieren ---
        self.data_loader = AdminTabDataLoader(admin_window, self, self.thread_manager)
        self.lifecycle_manager = AdminTabLifecycleManager(admin_window, notebook, self)

    def setup_lazy_tabs(self):
        """Erstellt die Platzhalter-Tabs im Notebook."""
        print("[DEBUG] AdminTabManager.setup_lazy_tabs: Erstelle Platzhalter...")
        i = 0
        for tab_name, TabClass in self.tab_definitions.items():
            placeholder_frame = ttk.Frame(self.notebook, padding=20)
            self.notebook.add(placeholder_frame, text=tab_name)
            self.tab_frames[tab_name] = placeholder_frame
            if TabClass is None:
                try:
                    self.notebook.tab(i, state='disabled')
                    print(f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' (Index {i}) deaktiviert.")
                except tk.TclError as e:
                    print(f"[FEHLER] setup_lazy_tabs: Konnte Tab '{tab_name}' nicht deaktivieren: {e}")
            i += 1

    def bind_tab_change_event(self):
        """ (Wird vom LifecycleManager aufgerufen) Bindet das Notebook-Event. """
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, event):
        """Startet den Lade-Thread für den ausgewählten Tab, falls noch nicht geladen."""
        try:
            selected_tab_id = self.notebook.select()
            if not selected_tab_id: return
            tab_index = self.notebook.index(selected_tab_id)

            tab_info = self.notebook.tab(tab_index)
            if not tab_info: return
            tab_name_with_count = tab_info.get("text", "")
            tab_name = tab_name_with_count.split(" (")[0]  # Basisname

            print(f"[GUI-Admin] on_tab_changed: Zu Tab '{tab_name}' gewechselt.")

            # --- DELEGIERT AN LIFECYCLE MANAGER ---
            self.lifecycle_manager.preload_tab(tab_name, tab_index, force_select=True)

        except (tk.TclError, IndexError) as e:
            print(f"[GUI-Admin] Fehler beim Ermitteln des Tabs in on_tab_changed: {e}")
        except Exception as e:
            print(f"[GUI-Admin] Unerwarteter Fehler in on_tab_changed: {e}")

    def preload_tab(self, tab_name, tab_index=None, force_select=False):
        """
        Löst das Laden eines Tabs aus, ohne ihn auszuwählen.
        (Wird z.B. vom Preloader P2 genutzt)
        """
        # --- DELEGIERT AN LIFECYCLE MANAGER ---
        self.lifecycle_manager.preload_tab(tab_name, tab_index, force_select=False)

    def update_single_tab_text(self, tab_name, new_text):
        """Aktualisiert den Text eines Tabs anhand seines Basisnamens."""
        widget_ref = self.tab_frames.get(tab_name)
        if widget_ref and widget_ref.winfo_exists():
            try:
                parent = self.notebook.nametowidget(widget_ref.winfo_parent())
                if parent == self.notebook:
                    current_text = self.notebook.tab(widget_ref, "text")
                    if current_text != new_text:
                        self.notebook.tab(widget_ref, text=new_text)
                else:
                    print(f"[DEBUG] update_single_tab_text: Frame für {tab_name} ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name}: {e}")

    def fetch_tab_title_counts(self):
        """ [NEU] Startet das Holen der Zähler über den Data Loader. """
        self.data_loader.start_fetch_tab_title_counts()

    def update_tab_titles_ui(self, counts):
        """
        [LÄUFT IM GUI-THREAD]
        Callback für den Data Loader. Aktualisiert die Tab-Titel (Texte).
        """
        if isinstance(counts, Exception):
            print(f"[FEHLER] update_tab_titles_ui erhielt Fehler: {counts}")
            counts = {}

        if not self.admin_window.winfo_exists():
            return

        self.last_tab_counts = counts  # Lokalen Cache aktualisieren

        try:
            for tab_name in self.tab_definitions.keys():
                if tab_name == "Dummy": continue

                count = counts.get(tab_name, 0)

                # Sonderfall: Mitarbeiter-Tab holt Zähler selbst, wenn geladen
                if tab_name == "Mitarbeiter":
                    tab_widget = self.tab_frames.get(tab_name)
                    if tab_name in self.loaded_tabs and hasattr(tab_widget, 'pending_approval_count'):
                        count = tab_widget.pending_approval_count
                    else:
                        count = counts.get(tab_name, 0)  # Fallback auf Zähler vom Loader

                tab_text = f"{tab_name} ({count})" if count > 0 else tab_name
                self.update_single_tab_text(tab_name, tab_text)

        except Exception as e:
            print(f"[FEHLER] Konnte Tab-Titel nicht aktualisieren: {e}")

    def update_tab_titles(self):
        """ (Veraltet) Liest nur noch aus dem zuletzt gespeicherten Cache. """
        print("[DEBUG] AdminTabManager.update_tab_titles (nutzt internen Cache)...")
        self.update_tab_titles_ui(self.last_tab_counts)

    def switch_to_tab(self, tab_name):
        """Wechselt zum Tab mit dem gegebenen Namen (Basisname ohne Zähler)."""
        widget_ref = self.tab_frames.get(tab_name)
        if widget_ref and widget_ref.winfo_exists():
            try:
                parent = self.notebook.nametowidget(widget_ref.winfo_parent())
                if parent == self.notebook:
                    print(f"[DEBUG] switch_to_tab: Wechsle zu Tab '{tab_name}'...")
                    self.notebook.select(widget_ref)
                else:
                    print(f"[DEBUG] switch_to_tab: Frame für '{tab_name}' ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                print(f"[DEBUG] switch_to_tab: Fehler beim Auswählen von '{tab_name}': {e}")
        else:
            print(f"[DEBUG] switch_to_tab: Tab/Frame '{tab_name}' nicht gefunden oder zerstört.")

    def _load_dynamic_tab(self, tab_name, TabClass, *args):
        """
        Lädt einen Tab dynamisch (synchron), der nicht in den Haupt-Definitionen ist.
        Delegiert an den LifecycleManager.
        """
        # --- DELEGIERT AN LIFECYCLE MANAGER ---
        self.lifecycle_manager.load_dynamic_tab(tab_name, TabClass, *args)

    # --- Refresh-Funktionen ---

    def refresh_all_tabs(self):
        """
        Startet das Neuladen der globalen Caches über den Data Loader.
        Der Data Loader wird nach Abschluss 'refresh_all_loaded_tabs_from_cache' aufrufen.
        """
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs (via Data Loader)...")
        # --- DELEGIERT AN DATA LOADER ---
        self.data_loader.start_refresh_all_tabs()

    def refresh_all_loaded_tabs_from_cache(self):
        """
        [Callback vom Data Loader]
        Aktualisiert die GUI aller geladenen Tabs mit den neuen Cache-Daten.
        """
        # --- DELEGIERT AN LIFECYCLE MANAGER ---
        self.lifecycle_manager.refresh_all_loaded_tabs_from_cache()

    def refresh_shift_plan(self):
        """Aktualisiert nur den Schichtplan-Tab (falls geladen)."""
        self.refresh_specific_tab("Schichtplan")

    def refresh_specific_tab(self, tab_name):
        """Aktualisiert einen spezifischen Tab, falls er geladen ist."""
        # --- DELEGIERT AN LIFECYCLE MANAGER ---
        self.lifecycle_manager.refresh_specific_tab(tab_name)

    def refresh_antragssperre_views(self):
        """ Aktualisiert Ansichten, die von der Antragssperre betroffen sind. """
        print("[DEBUG] refresh_antragssperre_views aufgerufen.")
        # (Diese Logik bleibt hier, da sie spezifische Tabs koordiniert)
        self.refresh_specific_tab("Schichtplan")
        self.refresh_specific_tab("Antragssperre")
        self.refresh_specific_tab("Urlaubsanträge")