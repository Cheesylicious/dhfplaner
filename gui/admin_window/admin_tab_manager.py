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
# from ..tabs.log_tab import LogTab # Auskommentiert
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

# --- DB-IMPORTE FÜR NEUE THREAD-FUNKTIONEN ---
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count
# --- KORREKTUR: Import von get_unapproved_users_count entfernt ---
from database.db_users import get_all_users
from database.db_dogs import get_all_dogs
from database.db_admin import get_pending_password_resets_count

# --- NEUER IMPORT FÜR BERECHTIGUNGEN (Regel 4) ---
# Importiert die DB-Funktion und die Liste der Tab-Namen (ALL_ADMIN_TABS)
try:
    from database.db_roles import get_all_roles_details, ALL_ADMIN_TABS
except ImportError as e:
    print(f"KRITISCHER FEHLER: db_roles.py konnte nicht importiert werden: {e}")
    # Fallback, damit das Programm nicht abstürzt (Regel 1)
    ALL_ADMIN_TABS = []


    def get_all_roles_details():
        return []
# --- ENDE NEU ---

try:
    from database.db_tasks import get_open_tasks_count, get_all_tasks
except ImportError:
    print("[WARNUNG] db_tasks nicht gefunden. Tab-Titel für Aufgaben wird nicht aktualisiert.")


    def get_open_tasks_count():
        return 0


    def get_all_tasks():
        return []


# --- ENDE KORREKTUR ---


class AdminTabManager:
    def __init__(self, admin_window, notebook):
        """
        Manager für das Lazy Loading und die Verwaltung der Notebook-Tabs.
        """
        super().__init__()
        self.admin_window = admin_window
        self.notebook = notebook
        self.user_data = admin_window.user_data

        self.thread_manager = self.admin_window.thread_manager

        # --- KORREKTUR: REIHENFOLGE GEÄNDERT ---

        # 1. Definition der Tabs (MUSS ZUERST KOMMEN)
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

            "Antragssperre": RequestLockTab,
            "Einstellungen": UserTabSettingsTab,
            "Passwort-Resets": PasswordResetRequestsWindow
        }

        # 2. Berechtigungs-Logik (GREIFT AUF tab_definitions ZU)
        self.user_role_id = self.user_data.get('role_id')
        self.user_permissions = self._load_user_permissions()

        # --- ENDE KORREKTUR ---

        # Abgleich der DB-Definition (ALL_ADMIN_TABS) mit den Code-Definitionen
        db_tabs = set(ALL_ADMIN_TABS)
        code_tabs = set(self.tab_definitions.keys())

        if db_tabs != code_tabs:
            print(f"[WARNUNG] Tab-Definitionen (admin_tab_manager) weichen von DB-Definition (db_roles) ab!")
            print(f"   Nur im Code: {code_tabs - db_tabs}")
            print(f"   Nur in DB-Def: {db_tabs - code_tabs}")

        # --- ENDE BERECHTIGUNGEN ---

        self.tab_frames = {}
        self.loaded_tabs = set()
        self.loading_tabs = set()
        self.tab_load_queue = Queue()
        self.tab_load_checker_running = False
        self.last_tab_counts = {}

    # --- NEUE FUNKTIONEN FÜR BERECHTIGUNGEN (Regel 4) ---
    def _load_user_permissions(self):
        """Lädt die Berechtigungen für die aktuelle Benutzerrolle."""
        print(f"[DEBUG] Lade Berechtigungen für Rolle ID: {self.user_role_id}")

        # Holt den RollenNAMEN (z.B. 'SuperAdmin') aus den Anmeldedaten
        user_role_name = self.user_data.get('role')

        # Admins und SuperAdmins (Master-Rollen) erhalten immer alle Rechte,
        # damit sie sich nicht selbst aussperren können.
        if user_role_name in ['Admin', 'SuperAdmin']:
            print(f"[DEBUG] Master-Rolle '{user_role_name}' erkannt. Gewähre alle Rechte.")
            # Greift jetzt auf self.tab_definitions zu, das bereits existiert
            return {tab_name: True for tab_name in self.tab_definitions}

        try:
            all_roles = get_all_roles_details()
            current_role_data = next((r for r in all_roles if r['id'] == self.user_role_id), None)

            if current_role_data:
                permissions = current_role_data.get('permissions', {})
                print(f"[DEBUG] Berechtigungen für Rolle '{current_role_data['name']}' geladen.")
                return permissions
            else:
                print(f"[WARNUNG] Rolle ID {self.user_role_id} nicht in DB gefunden. Keine Rechte gewährt.")
                return {}
        except Exception as e:
            print(f"[FEHLER] _load_user_permissions: {e}. Keine Rechte gewährt.")
            return {}

    def _has_permission(self, tab_name):
        """Prüft, ob der Benutzer die Berechtigung für einen Tab hat."""

        user_role_name = self.user_data.get('role')
        if user_role_name in ['Admin', 'SuperAdmin']:
            return True

        has_perm = self.user_permissions.get(tab_name, False)

        if tab_name == "Wartung" and not has_perm:
            has_perm = self.user_permissions.get("Einstellungen", False)
        elif tab_name == "Wunschanfragen" and not has_perm:
            has_perm = self.user_permissions.get("Anträge", False)

        if not has_perm:
            if self.tab_definitions.get(tab_name) is not None:
                print(f"[DEBUG] Zugriff verweigert für Rolle {self.user_role_id} auf Tab: {tab_name}")

        return has_perm

    def reevaluate_tab_permissions(self):
        """
        Wird vom RoleManagementDialog aufgerufen.
        Lädt Berechtigungen neu und blendet Tabs ein/aus.
        """
        print("[DEBUG] reevaluate_tab_permissions aufgerufen.")
        self.user_permissions = self._load_user_permissions()

        current_selected_tab_id = None
        try:
            current_selected_tab_id = self.notebook.select()
        except tk.TclError:
            pass

        current_tab_is_now_disabled = False
        all_tab_widgets = self.notebook.tabs()

        for tab_id in all_tab_widgets:
            try:
                tab_text_with_count = self.notebook.tab(tab_id, "text")
                if not tab_text_with_count:
                    continue

                tab_name = tab_text_with_count.split(" (")[0]

                if tab_name not in self.tab_definitions:
                    continue

                if self._has_permission(tab_name):
                    self.notebook.tab(tab_id, state='normal')
                else:
                    self.notebook.tab(tab_id, state='disabled')
                    if tab_id == current_selected_tab_id:
                        current_tab_is_now_disabled = True

            except tk.TclError as e:
                print(f"Fehler beim Zugriff auf Tab-ID {tab_id}: {e}")

        if current_tab_is_now_disabled:
            print("[DEBUG] Aktueller Tab wurde deaktiviert. Wechsle zu Tab 0.")
            if all_tab_widgets:
                first_normal_tab = all_tab_widgets[0]
                for tab_id in all_tab_widgets:
                    try:
                        if self.notebook.tab(tab_id, "state") == 'normal':
                            first_normal_tab = tab_id
                            break
                    except tk.TclError:
                        continue
                self.notebook.select(first_normal_tab)

    # --- ENDE NEUE FUNKTIONEN ---

    def setup_lazy_tabs(self):
        """
        Erstellt die Platzhalter-Tabs im Notebook.
        --- JETZT MIT BERECHTIGUNGSPRÜFUNG ---
        """
        print("[DEBUG] AdminTabManager.setup_lazy_tabs: Erstelle Platzhalter...")
        i = 0
        for tab_name, TabClass in self.tab_definitions.items():
            placeholder_frame = ttk.Frame(self.notebook, padding=20)

            if self._has_permission(tab_name):
                self.notebook.add(placeholder_frame, text=tab_name)
                self.tab_frames[tab_name] = placeholder_frame
            else:
                self.notebook.add(placeholder_frame, text=tab_name, state='disabled')
                print(f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' deaktiviert (Keine Berechtigung).")

            if TabClass is None:
                try:
                    current_index = self.notebook.index(placeholder_frame)
                    self.notebook.tab(current_index, state='disabled')
                    print(
                        f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' (Index {current_index}) explizit deaktiviert (Class=None).")
                except tk.TclError as e:
                    print(f"[FEHLER] setup_lazy_tabs: Konnte Tab '{tab_name}' nicht deaktivieren: {e}")
            i += 1

    def on_tab_changed(self, event):
        """Startet den Lade-Thread für den ausgewählten Tab, falls noch nicht geladen."""
        try:
            selected_tab_id = self.notebook.select()
            if not selected_tab_id: return
            tab_index = self.notebook.index(selected_tab_id)

            tab_info = self.notebook.tab(tab_index)
            if not tab_info: return

            if tab_info.get("state", "normal") == 'disabled':
                print(f"[GUI-Admin] on_tab_changed: Klick auf deaktivierten Tab. Wechsle zu Tab 0.")
                if self.notebook.tabs():
                    self.notebook.select(0)
                return

            tab_name_with_count = tab_info.get("text", "")
            tab_name = tab_name_with_count.split(" (")[0]  # Basisname

            print(f"[GUI-Admin] on_tab_changed: Zu Tab '{tab_name}' gewechselt.")

            if not self._has_permission(tab_name):
                print(f"[FEHLER] on_tab_changed: Zugriff auf {tab_name} blockiert (Keine Berechtigung).")
                if self.notebook.tabs(): self.notebook.select(0)
                return

            if tab_name in self.loaded_tabs:
                frame = self.tab_frames.get(tab_name)
                if frame and hasattr(frame, 'on_tab_focus'):
                    print(f"[GUI-Admin] on_tab_changed: Rufe on_tab_focus() für GELADENEN Tab '{tab_name}' auf.")
                    frame.on_tab_focus()
                return

            self.preload_tab(tab_name, tab_index, force_select=True)

        except (tk.TclError, IndexError) as e:
            print(f"[GUI-Admin] Fehler beim Ermitteln des Tabs in on_tab_changed: {e}")
        except Exception as e:
            print(f"[GUI-Admin] Unerwarteter Fehler in on_tab_changed: {e}")

    def preload_tab(self, tab_name, tab_index=None, force_select=False):
        """
        Löst das Laden eines Tabs aus, wenn er noch nicht geladen ist.
        """
        if not self._has_permission(tab_name):
            if not force_select:
                print(f"[GUI-Admin] preload_tab: Laden von '{tab_name}' blockiert (Keine Berechtigung).")
            return

        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
            if not force_select:
                print(f"[GUI-Admin] -> Tab '{tab_name}' ist bereits geladen oder wird geladen. Keine Aktion.")
            return

        if tab_name not in self.tab_definitions or self.tab_definitions[tab_name] is None:
            if not force_select:
                print(f"[GUI-Admin] -> Keine Definition für Tab '{tab_name}'. Keine Aktion.")
            return

        print(f"[GUI-Admin] -> Starte Ladevorgang für {tab_name} (Threaded)")
        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames.get(tab_name)

        if not placeholder_frame or not placeholder_frame.winfo_exists():
            print(f"[GUI-Admin] FEHLER: Platzhalter-Frame für '{tab_name}' nicht gefunden oder bereits zerstört.")
            return

        if tab_index is None:
            try:
                tab_index = self.notebook.index(placeholder_frame)
            except tk.TclError:
                print(f"[GUI-Admin] FEHLER: Konnte Index für Platzhalter {tab_name} nicht finden.")
                return

        if force_select:
            try:
                current_widget_at_index = self.notebook.nametowidget(self.notebook.select())
                is_placeholder = (placeholder_frame == current_widget_at_index)
                if is_placeholder:
                    print(f"[GUI-Admin] -> Zeige Ladeanzeige in Platzhalter für '{tab_name}'.")
                    for widget in placeholder_frame.winfo_children(): widget.destroy()
                    ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16)).pack(expand=True,
                                                                                                         anchor="center")
                    self.admin_window.update_idletasks()
            except tk.TclError:
                pass

        self.loading_tabs.add(tab_name)

        self.thread_manager.start_worker(
            self._load_tab_threaded,
            self._check_tab_load_queue,
            tab_name,
            TabClass,
            tab_index
        )

    # --- KORRIGIERTE FUNKTION (Fehlerbehebung): Race Condition (Regel 1 & 2) ---
    def _replace_placeholder(self, tab_name, real_tab, tab_index, placeholder_frame):
        """Hilfsfunktion, um einen Platzhalter synchron zu ersetzen."""
        try:
            is_preloading = False
            try:
                current_selected_index = self.notebook.index("current")
                if current_selected_index != tab_index:
                    is_preloading = True
                    print(f"[Preloader P2] Ersetze Platzhalter für '{tab_name}' im Hintergrund.")
            except Exception:
                is_preloading = False

            self.notebook.unbind("<<NotebookTabChanged>>")

            current_count = self.last_tab_counts.get(tab_name, 0)
            tab_text = f"{tab_name} ({current_count})" if current_count > 0 else tab_name

            # (1) Finde den Index des Platzhalters (kann sich durch Race Cond. geändert haben)
            try:
                placeholder_index = self.notebook.index(placeholder_frame)
                tab_index = placeholder_index  # Nutze den *aktuellen* Index
            except tk.TclError:
                print(f"Warnung: Platzhalter {tab_name} nicht mehr im Notebook. Abbruch.")
                return

            # (2) Entferne den Platzhalter
            self.notebook.forget(placeholder_frame)

            # (3) Hole die aktuelle Anzahl der Tabs (NACH dem 'forget')
            current_tab_count = len(self.notebook.tabs())  # z.B. 14

            # (4) Prüfe, ob der Ziel-Index (z.B. 14) GÜLTIG ist
            # --- KORREKTUR: Muss >= sein (Regel 1) ---
            if tab_index >= current_tab_count:
                # --- ENDE KORREKTUR ---
                # Dies fängt die Race Condition ab (Regel 1 & 2)
                # (z.B. wenn Index 14 war, aber durch 'forget' ist max Index 13)
                print(
                    f"[Race Condition Fix] Index {tab_index} für {tab_name} ungültig (max {current_tab_count - 1}). Füge am Ende ein.")
                tab_index = 'end'

                # (5) Füge den echten Tab am (ggf. korrigierten) Index ein
            self.notebook.insert(tab_index, real_tab, text=tab_text)

            if not is_preloading:
                self.notebook.select(real_tab)

            self.loaded_tabs.add(tab_name)
            self.tab_frames[tab_name] = real_tab
            print(f"[GUI-Admin] Tab '{tab_name}' erfolgreich eingesetzt.")
        except tk.TclError as e:
            print(f"[GUI-Admin] TclError beim Einsetzen von {tab_name}: {e}")
        finally:
            self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    # --- ENDE KORREKTUR ---

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """
        [LÄUFT IM THREAD]
        Lädt einen Tab im Hintergrund-Thread.
        """
        try:
            print(f"[Thread-Admin] Lade Tab: {tab_name}...")
            real_tab = None
            admin_window_ref = self.admin_window
            bootloader_app = self.admin_window.app

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
                real_tab = TabClass(self.notebook, admin_window_ref, bootloader_app.global_pending_vacations_count)

            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.user_data)

            elif TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, admin_window_ref)

            elif TabClass.__name__ in ["RequestLockTab", "PasswordResetRequestsWindow"]:
                real_tab = TabClass(self.notebook, admin_window_ref)

            else:
                try:
                    real_tab = TabClass(self.notebook, admin_window_ref)
                except Exception as e1:
                    print(
                        f"[Thread-Admin] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:
                        real_tab = TabClass(self.notebook)
                    except Exception as e2:
                        print(f"[Thread-Admin] FEHLER: {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise

            return (tab_name, real_tab, tab_index)

        except Exception as e:
            print(f"[Thread-Admin] FEHLER beim Laden von Tab '{tab_name}': {e}")
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
                print(f"[GUI-Checker-Admin] ThreadManager-Fehler: {error}")
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    tab_name_processed = result[0]
                return

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
                try:
                    # --- KORREKTUR (Fehlerbehebung): 'tab_index' übergeben (den der Thread gemeldet hat) ---
                    # (Dieser Index wird *innerhalb* von _replace_placeholder validiert)
                    self._replace_placeholder(tab_name, real_tab, tab_index, placeholder_frame)
                    # --- ENDE KORREKTUR ---
                except tk.TclError:
                    print(f"[GUI-Checker-Admin] Platzhalter {tab_name} nicht mehr im Notebook. Setze an Ende.")
                    self._replace_placeholder(tab_name, real_tab, 'end', placeholder_frame)

        except Exception as e:
            print(f"[GUI-Checker-Admin] Unerwarteter Fehler in _check_tab_load_queue: {e}")
        finally:
            if tab_name_processed and tab_name_processed in self.loading_tabs:
                self.loading_tabs.remove(tab_name_processed)

    def update_single_tab_text(self, tab_name, new_text):
        """Aktualisiert den Text eines Tabs anhand seines Basisnamens."""
        widget_ref = self.tab_frames.get(tab_name)
        if widget_ref and widget_ref.winfo_exists():
            try:
                parent = self.notebook.nametowidget(widget_ref.winfo_parent())
                if parent == self.notebook:
                    if self.notebook.tab(widget_ref, "state") == 'disabled':
                        return

                    current_text = self.notebook.tab(widget_ref, "text")
                    if current_text != new_text:
                        self.notebook.tab(widget_ref, text=new_text)
                else:
                    print(f"[DEBUG] update_single_tab_text: Frame für {tab_name} ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                if 'invalid command name' not in str(e):
                    print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name}: {e}")

    # --- NEUE FUNKTIONEN FÜR THREAD-BASIERTE TAB-TITEL ---

    def fetch_tab_title_counts(self):
        """
        [LÄUFT IM THREAD]
        Holt alle Zähler für die Tab-Titel aus der DB.
        """
        counts = {}
        try:
            counts["Wunschanfragen"] = len(get_pending_wunschfrei_requests())
            counts["Urlaubsanträge"] = get_pending_vacation_requests_count()
            counts["Bug-Reports"] = get_open_bug_reports_count()
            counts["Mitarbeiter"] = 0  # Platzhalter
            counts["Passwort-Resets"] = get_pending_password_resets_count()
            counts["Aufgaben"] = get_open_tasks_count()
            return counts
        except Exception as e:
            print(f"[FEHLER] fetch_tab_title_counts (Thread): {e}")
            return e

    def update_tab_titles_ui(self, counts):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert die Tab-Titel (Texte) basierend auf den geladenen Zählern.
        """
        if isinstance(counts, Exception):
            print(f"[FEHLER] update_tab_titles_ui erhielt Fehler: {counts}")
            counts = {}

        if not self.admin_window.winfo_exists():
            return

        self.last_tab_counts = counts

        try:
            for tab_name in self.tab_frames.keys():

                count = counts.get(tab_name, 0)
                if tab_name == "Mitarbeiter":
                    tab_widget = self.tab_frames.get(tab_name)
                    if tab_name in self.loaded_tabs and hasattr(tab_widget, 'pending_approval_count'):
                        count = tab_widget.pending_approval_count
                    else:
                        count = counts.get(tab_name, 0)

                tab_text = f"{tab_name} ({count})" if count > 0 else tab_name
                self.update_single_tab_text(tab_name, tab_text)

        except Exception as e:
            print(f"[FEHLER] Konnte Tab-Titel nicht aktualisieren: {e}")

    def update_tab_titles(self):
        """
        [VERALTET]
        Liest nur noch aus dem zuletzt gespeicherten Cache.
        """
        print("[DEBUG] AdminTabManager.update_tab_titles (nutzt internen Cache)...")
        self.update_tab_titles_ui(self.last_tab_counts)

    # --- ENDE NEUE FUNKTIONEN ---

    def switch_to_tab(self, tab_name):
        """Wechselt zum Tab mit dem gegebenen Namen (Basisname ohne Zähler)."""
        widget_ref = self.tab_frames.get(tab_name)

        if not widget_ref:
            print(f"[DEBUG] switch_to_tab: Tab '{tab_name}' nicht in self.tab_frames (vermutlich keine Berechtigung).")
            return

        if widget_ref.winfo_exists():
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
        """Lädt einen Tab dynamisch (synchron), der nicht in den Haupt-Definitionen ist."""

        if tab_name in ALL_ADMIN_TABS and not self._has_permission(tab_name):
            messagebox.showerror("Zugriff verweigert", f"Sie haben keine Berechtigung, '{tab_name}' zu öffnen.",
                                 parent=self.admin_window)
            return

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
                real_tab = TabClass(self.notebook, admin_window_ref, *args)
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.user_data)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, admin_window_ref)
            else:
                print(f"[WARNUNG] _load_dynamic_tab: Unbekannter Typ {TabClass.__name__}, versuche mit (master).")
                try:
                    real_tab = TabClass(self.notebook)
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
                self.loading_tabs.remove(tab_name_processed)

    # --- Refresh-Funktionen (JETZT THREAD-BASIERT) ---

    def refresh_all_tabs(self):
        """
        [LÄUFT IM GUI-THREAD]
        Startet das Neuladen der globalen Caches in einem Thread.
        """
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs (Thread-basiert)...")

        self.thread_manager.start_worker(
            self._fetch_global_caches,
            self._on_global_caches_refreshed
        )

    def _fetch_global_caches(self):
        """
        [LÄUFT IM THREAD]
        Holt alle Daten für die globalen Caches (blockierend).
        """
        print("[Thread-Admin] Aktualisiere globale Caches im Bootloader...")
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

    def _on_global_caches_refreshed(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback, wenn die Caches neu geladen wurden.
        """
        if not self.admin_window.winfo_exists():
            return

        bootloader_app = self.admin_window.app

        if error:
            print(f"[FEHLER] _on_global_caches_refreshed: {error}")
            return
        if isinstance(result, Exception):
            print(f"[FEHLER] _on_global_caches_refreshed (von Thread): {result}")
            return

        caches = result
        try:
            bootloader_app.global_user_cache = caches.get('user_cache', [])
            bootloader_app.global_dog_cache = caches.get('dog_cache', [])
            bootloader_app.global_pending_wishes_cache = caches.get('pending_wishes_cache', [])
            bootloader_app.global_pending_vacations_count = caches.get('pending_vacations_count', 0)
            bootloader_app.global_open_bugs_count = caches.get('open_bugs_count', 0)
            bootloader_app.global_open_tasks_count = caches.get('open_tasks_count', 0)
            print("[DEBUG] Globale Caches aktualisiert.")

            counts_for_titles = {
                "Wunschanfragen": len(bootloader_app.global_pending_wishes_cache),
                "Urlaubsanträge": bootloader_app.global_pending_vacations_count,
                "Bug-Reports": bootloader_app.global_open_bugs_count,
                "Aufgaben": bootlaoder_app.global_open_tasks_count,
                "Mitarbeiter": 0
            }
            self.update_tab_titles_ui(counts_for_titles)

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
                else:
                    print(
                        f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                    if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                    if tab_name in self.tab_frames: del self.tab_frames[tab_name]

            if hasattr(self.admin_window, 'notification_manager'):
                self.admin_window.notification_manager.check_for_updates_threaded()
            print("[DEBUG] Refresh aller geladenen Tabs abgeschlossen.")

        except Exception as e:
            print(f"[FEHLER] beim Anwenden der globalen Caches: {e}")

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

    def refresh_antragssperre_views(self):
        """ Aktualisiert Ansichten, die von der Antragssperre betroffen sind. """
        print("[DEBUG] refresh_antragssperre_views aufgerufen.")

        plan_tab_name = "Schichtplan"
        if plan_tab_name in self.loaded_tabs:
            plan_tab = self.tab_frames.get(plan_tab_name)
            if plan_tab and plan_tab.winfo_exists() and hasattr(plan_tab, 'update_lock_status'):
                try:
                    print("[DEBUG] -> Aktualisiere Sperrstatus im Schichtplan-Tab.")
                    plan_tab.update_lock_status()
                except Exception as e:
                    print(f"[FEHLER] bei plan_tab.update_lock_status: {e}")

        lock_tab_name = "Antragssperre"
        if lock_tab_name in self.loaded_tabs:
            lock_tab = self.tab_frames.get(lock_tab_name)
            if lock_tab and lock_tab.winfo_exists() and hasattr(lock_tab, 'load_locks_for_year'):
                try:
                    print("[DEBUG] -> Lade Sperren neu im Antragssperre-Tab.")
                    lock_tab.load_locks_for_year()
                except Exception as e:
                    print(f"[FEHLER] bei lock_tab.load_locks_for_year: {e}")

        vacation_tab_name = "Urlaubsanträge"
        if vacation_tab_name in self.loaded_tabs:
            self.refresh_specific_tab(vacation_tab_name)