# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
# --- Korrektur: datetime für open_user_order_window benötigt ---
from datetime import date, timedelta, datetime
# --- Ende Korrektur ---
import calendar
from collections import defaultdict

# --- NEUE IMPORTE FÜR THREADING ---
import threading
from queue import Queue, Empty
# ---------------------------------

# --- WICHTIGE IMPORTE ---
from .tabs.shift_plan_tab import ShiftPlanTab
from .tabs.user_management_tab import UserManagementTab
from .tabs.dog_management_tab import DogManagementTab
# --- Korrektur: ShiftTypesTab importieren ---
from .tabs.shift_types_tab import ShiftTypesTab
# ----------------------------------------
from .tabs.requests_tab import RequestsTab
from .tabs.log_tab import LogTab
from .tabs.bug_reports_tab import BugReportsTab
from .tabs.vacation_requests_tab import VacationRequestsTab
from .tabs.request_lock_tab import RequestLockTab
from .tabs.user_tab_settings_tab import UserTabSettingsTab
from .tabs.participation_tab import ParticipationTab
from .tabs.protokoll_tab import ProtokollTab
from .tabs.chat_tab import ChatTab
from .tabs.password_reset_requests_window import PasswordResetRequestsWindow

# --- NEUER IMPORT FÜR WARTUNGSTAB ---
from .tabs.settings_tab import SettingsTab
# --------------------------------------

from database.db_core import (
    ROLE_HIERARCHY,
    load_config_json,
    save_config_json,
    load_shift_frequency,
    save_shift_frequency,
    reset_shift_frequency,
    MIN_STAFFING_RULES_CONFIG_KEY,
    run_db_update_v1,
    run_db_update_is_approved,
    run_db_fix_approve_all_users,
    run_db_update_add_is_archived,
    run_db_update_add_archived_date
)
from database.db_chat import get_senders_with_unread_messages
from database.db_users import log_user_logout
from database.db_shifts import get_all_shift_types
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count, get_reports_with_user_feedback_count
from database.db_admin import get_pending_password_resets_count

# --- ShiftTypeDialog Import ist hier nicht mehr nötig ---
from .dialogs.user_order_window import UserOrderWindow
from .dialogs.shift_order_window import ShiftOrderWindow
from .dialogs.min_staffing_window import MinStaffingWindow
from .dialogs.holiday_settings_window import HolidaySettingsWindow
from .dialogs.event_settings_window import EventSettingsWindow
from .dialogs.request_settings_window import RequestSettingsWindow
from .dialogs.planning_assistant_settings_window import PlanningAssistantSettingsWindow
from .dialogs.color_settings_window import ColorSettingsWindow
from .dialogs.bug_report_dialog import BugReportDialog
from .holiday_manager import HolidayManager
from .event_manager import EventManager


class MainAdminWindow(tk.Toplevel):
    def __init__(self, master, user_data, app):
        print("[DEBUG] MainAdminWindow.__init__: Start")
        super().__init__(master)
        self.app = app  # Die Haupt-Applikationsinstanz
        self.user_data = user_data # HIER WIRD ES GESPEICHERT

        # --- KORREKTUR: Setze die user_id als direktes Attribut ---
        self.user_id = user_data.get('id')
        self.current_user_id = user_data.get('id')
        # --- ENDE KORREKTUR ---

        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name} (Admin)")
        self.attributes('-fullscreen', True)

        self.setup_styles()

        self.shift_types_data = {}
        self.staffing_rules = {}
        self.events = {}
        today = date.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        self.current_display_date = today.replace(day=1) + timedelta(days=days_in_month)
        self.current_year_holidays = {}
        self.shift_frequency = self.load_shift_frequency()

        self.load_all_data()
        print("[DEBUG] MainAdminWindow.__init__: Basisdaten geladen.")

        self.header_frame = ttk.Frame(self, padding=(10, 5, 10, 0))
        self.header_frame.pack(fill='x')
        self.setup_header()

        self.chat_notification_frame = tk.Frame(self, bg='tomato', cursor="hand2")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

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
            "Logs": LogTab,
            "Protokoll": ProtokollTab,
            "Wartung": SettingsTab,
            "Dummy": None
        }

        self.tab_frames = {} # Speichert Referenzen auf die Tab-Widgets (Platzhalter oder echt)
        self.loaded_tabs = set() # Namen der Tabs, die bereits geladen wurden

        # --- Threading für Tabs ---
        self.loading_tabs = set()
        self.tab_load_queue = Queue()
        self.tab_load_checker_running = False
        # -------------------------------

        self.setup_lazy_tabs()
        print("[DEBUG] MainAdminWindow.__init__: Lazy Tabs (Platzhalter) erstellt.")

        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.after(1000, self.check_for_updates)
        self.after(2000, self.check_chat_notifications)

        # --- Threaded-Start für ersten Tab ---
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        if self.notebook.tabs():
            self.notebook.select(0)
            self.on_tab_changed(None)

        print("[DEBUG] MainAdminWindow.__init__: Initialisierung abgeschlossen.")

    # --- _load_tab_threaded, _check_tab_load_queue, _load_tab_directly bleiben unverändert ---
    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """Lädt einen Tab im Hintergrund-Thread."""
        try:
            print(f"[Thread-Admin] Lade Tab: {tab_name}...")
            real_tab = None
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, self)
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.user_data)
            else:
                try:
                    real_tab = TabClass(self.notebook, self)
                except Exception as e1:
                    print(
                        f"[Thread-Admin] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:
                        real_tab = TabClass(self.notebook)
                    except Exception as e2:
                        print(f"[Thread-Admin] FEHLER: {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise

            self.tab_load_queue.put((tab_name, real_tab, tab_index))
            print(f"[Thread-Admin] Tab '{tab_name}' fertig geladen.")
        except Exception as e:
            print(f"[Thread-Admin] FEHLER beim Laden von Tab '{tab_name}': {e}")
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

            # Entferne "Lade..." Label, falls vorhanden
            for widget in placeholder_frame.winfo_children():
                if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                    widget.destroy()
                    break # Nur das eine Label entfernen

            if isinstance(real_tab_or_exception, Exception):
                e = real_tab_or_exception
                # Fehler im Platzhalter anzeigen
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
                print(f"[GUI-Checker-Admin] Fehler beim Laden von Tab '{tab_name}' angezeigt.")
            else:
                # Echten Tab einsetzen
                real_tab = real_tab_or_exception
                try:
                    self.notebook.unbind("<<NotebookTabChanged>>") # Event kurz deaktivieren
                    tab_options = self.notebook.tab(placeholder_frame) # Optionen merken
                    self.notebook.forget(placeholder_frame) # Platzhalter entfernen
                    self.notebook.insert(tab_index, real_tab, **tab_options) # Echten Tab einfügen
                    # --- WICHTIG: Nach dem Einfügen select aufrufen ---
                    # Dies stellt sicher, dass der neu geladene Tab auch aktiv ist,
                    # wenn er derjenige war, der den Ladevorgang ausgelöst hat.
                    self.notebook.select(real_tab)
                    # --- ENDE WICHTIG ---
                    self.loaded_tabs.add(tab_name)
                    self.tab_frames[tab_name] = real_tab # Referenz auf das ECHTE Widget aktualisieren
                    print(f"[GUI-Checker-Admin] Tab '{tab_name}' erfolgreich eingesetzt.")
                except tk.TclError as e:
                    # Fehler kann auftreten, wenn das Notebook-Widget in der Zwischenzeit zerstört wurde
                    print(f"[GUI-Checker-Admin] TclError beim Einsetzen von {tab_name}: {e}")
                finally:
                    # Event wieder aktivieren
                    self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        except Empty:
            # Queue ist leer, nichts zu tun
            pass
        except Exception as e:
            # Unerwarteter Fehler während der Queue-Verarbeitung
            print(f"[GUI-Checker-Admin] Unerwarteter Fehler in _check_tab_load_queue: {e}")
        finally:
            # Lade-Status für den bearbeiteten Tab entfernen
            if tab_name_processed and tab_name_processed in self.loading_tabs:
                self.loading_tabs.remove(tab_name_processed)

            # Den Checker weiterlaufen lassen, wenn noch Arbeit ansteht
            if not self.tab_load_queue.empty() or self.loading_tabs:
                self.after(100, self._check_tab_load_queue)
            else:
                # Keine Arbeit mehr -> Checker pausieren
                self.tab_load_checker_running = False
                print("[GUI-Checker-Admin] Keine Tabs mehr in Queue oder am Laden. Checker pausiert.")

    def _load_tab_directly(self, tab_name, tab_index):
        # (Wird nicht mehr direkt verwendet, bleibt als Fallback)
        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs: return
        if tab_name not in self.tab_definitions or not self.tab_definitions[tab_name]: return

        self.loading_tabs.add(tab_name)
        print(f"[GUI - direct load] Lade Tab (SYNCHRON): {tab_name}")
        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames[tab_name]

        for widget in placeholder_frame.winfo_children(): widget.destroy()
        loading_label = ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16))
        loading_label.pack(expand=True, anchor="center")
        self.update_idletasks()

        real_tab = None
        try:
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, self)
            elif TabClass.__name__ == "SettingsTab":
                real_tab = TabClass(self.notebook, self.user_data)
            else:
                try:
                    real_tab = TabClass(self.notebook, self)
                except TypeError:
                    print(
                        f"[GUI - direct load] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen. Versuche (master)...")
                    real_tab = TabClass(self.notebook)

            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)
                self.notebook.forget(placeholder_frame)
                self.notebook.insert(tab_index, real_tab, **tab_options)
                self.notebook.select(real_tab)
                self.loaded_tabs.add(tab_name)
                self.tab_frames[tab_name] = real_tab
                print(f"[GUI - direct load] Tab '{tab_name}' erfolgreich eingesetzt.")
            else:
                print(f"[GUI - direct load] FEHLER: Platzhalter für {tab_name} existierte nicht mehr.")

        except Exception as e:
            print(f"[GUI - direct load] FEHLER beim Laden/Einsetzen von Tab '{tab_name}': {e}")
            if placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
        finally:
            if tab_name in self.loading_tabs: self.loading_tabs.remove(tab_name)
    # --------------------------------------------------------------------------------------


    def on_tab_changed(self, event):
        """Startet den Lade-Thread für den ausgewählten Tab, falls noch nicht geladen."""
        try:
            selected_tab_id = self.notebook.select()
            if not selected_tab_id: return # Kein Tab ausgewählt
            tab_index = self.notebook.index(selected_tab_id)
            # Hole das Widget, das AKTUELL an diesem Index ist (kann Platzhalter oder echt sein)
            current_widget_at_index = self.notebook.nametowidget(selected_tab_id)

            # Ermittle den zugehörigen Basisnamen aus den Optionen des Notebook-Tabs
            tab_info = self.notebook.tab(tab_index)
            if not tab_info: return
            tab_name_with_count = tab_info.get("text", "")
            tab_name = tab_name_with_count.split(" (")[0] # Basisname

            print(f"[GUI-Admin] on_tab_changed: Zu Tab '{tab_name}' gewechselt.")

            # Prüfe, ob dieser Tab bereits geladen ist ODER gerade lädt
            if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
                print(f"[GUI-Admin] -> Tab '{tab_name}' ist bereits geladen oder wird geladen. Keine Aktion.")
                return

            # Prüfe, ob es eine Definition für diesen Tab gibt
            if tab_name not in self.tab_definitions or self.tab_definitions[tab_name] is None:
                 print(f"[GUI-Admin] -> Keine Definition für Tab '{tab_name}'. Keine Aktion.")
                 return # Nichts zu laden

            # --- Start des Ladevorgangs ---
            print(f"[GUI-Admin] -> Starte Ladevorgang für {tab_name}")
            TabClass = self.tab_definitions[tab_name]
            # Stelle sicher, dass wir den PLATZHALTER haben, um die Ladeanzeige zu zeigen
            placeholder_frame = self.tab_frames.get(tab_name)

            if not placeholder_frame or not placeholder_frame.winfo_exists():
                print(f"[GUI-Admin] FEHLER: Platzhalter-Frame für '{tab_name}' nicht gefunden oder bereits zerstört.")
                # Optional: Versuchen, den Platzhalter neu zu erstellen? Eher unwahrscheinlich.
                return

            # Bereinige Platzhalter und zeige Ladeanzeige, *nur wenn es der Platzhalter ist*
            # is_placeholder = not isinstance(current_widget_at_index, TabClass) if TabClass else True # Alte Prüfung
            is_placeholder = (placeholder_frame == current_widget_at_index) # Sicherere Prüfung
            if is_placeholder:
                print(f"[GUI-Admin] -> Zeige Ladeanzeige in Platzhalter für '{tab_name}'.")
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16)).pack(expand=True,
                                                                                                     anchor="center")
                self.update_idletasks() # Wichtig, damit die Anzeige sofort erscheint

            self.loading_tabs.add(tab_name)

            # Starte den Hintergrund-Thread zum Laden
            threading.Thread(
                target=self._load_tab_threaded,
                args=(tab_name, TabClass, tab_index),
                daemon=True # Wichtig, damit Thread bei App-Ende beendet wird
            ).start()

            # Starte den Queue-Checker, falls er nicht läuft
            if not self.tab_load_checker_running:
                print("[GUI-Checker-Admin] Starte Checker-Loop.")
                self.tab_load_checker_running = True
                self.after(50, self._check_tab_load_queue) # Kurze Verzögerung, dann prüfen

        except (tk.TclError, IndexError) as e:
             # Fehler beim Zugriff auf Notebook-Informationen
             print(f"[GUI-Admin] Fehler beim Ermitteln des Tabs in on_tab_changed: {e}")
        except Exception as e:
             # Andere unerwartete Fehler
             print(f"[GUI-Admin] Unerwarteter Fehler in on_tab_changed: {e}")


    # --- setup_styles, setup_lazy_tabs, update_single_tab_text, update_tab_titles bleiben unverändert ---
    def setup_styles(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            print("Clam theme not available, using default.")
        self.style.configure('Bug.TButton', background='dodgerblue', foreground='white', font=('Segoe UI', 9, 'bold'))
        self.style.map('Bug.TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])
        self.style.configure('Logout.TButton', background='gold', foreground='black', font=('Segoe UI', 10, 'bold'),
                             padding=6)
        self.style.map('Logout.TButton', background=[('active', 'goldenrod')], foreground=[('active', 'black')])
        self.style.configure('Notification.TButton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))
        self.style.map('Notification.TButton',
                       background=[('active', '#e0e0e0')],
                       relief=[('pressed', 'sunken')])
        self.style.configure('Settings.TMenubutton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))

    def setup_lazy_tabs(self):
        print("[DEBUG] setup_lazy_tabs: Erstelle Platzhalter...")
        i = 0
        for tab_name, TabClass in self.tab_definitions.items():
            placeholder_frame = ttk.Frame(self.notebook, padding=20)
            self.notebook.add(placeholder_frame, text=tab_name)
            self.tab_frames[tab_name] = placeholder_frame # Speichert initial den Platzhalter
            if TabClass is None: # Für deaktivierte Tabs
                try:
                    self.notebook.tab(i, state='disabled')
                    print(f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' (Index {i}) deaktiviert.")
                except tk.TclError as e:
                    print(f"[FEHLER] setup_lazy_tabs: Konnte Tab '{tab_name}' nicht deaktivieren: {e}")
            i += 1
        self.update_tab_titles() # Aktualisiert Titel basierend auf DB-Counts

    def update_single_tab_text(self, tab_name, new_text):
        """Aktualisiert den Text eines Tabs anhand seines Basisnamens."""
        widget_ref = self.tab_frames.get(tab_name) # Holt Platzhalter oder echtes Widget
        if widget_ref and widget_ref.winfo_exists():
            try:
                # Prüfen, ob das Widget noch ein Tab im Notebook ist
                if self.notebook.nametowidget(widget_ref.winfo_parent()) == self.notebook:
                    self.notebook.tab(widget_ref, text=new_text)
                else:
                     # Sollte nicht passieren, wenn self.tab_frames korrekt ist
                     print(f"[DEBUG] update_single_tab_text: Frame für {tab_name} ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                 # Kann passieren, wenn Widget gerade zerstört wird
                print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name}: {e} (Widget ungültig/zerstört/kein Tab)")
        # else: Kein Widget für diesen Namen gefunden (sollte nicht passieren bei initial Setup)

    def update_tab_titles(self):
        """Aktualisiert die Titel von Tabs, die Zähler anzeigen (Anfragen, Bugs etc.)."""
        print("[DEBUG] update_tab_titles wird ausgeführt.")
        try:
            # Wunschanfragen
            pending_wunsch_count = len(get_pending_wunschfrei_requests())
            tab_text_wunsch = "Wunschanfragen" + (f" ({pending_wunsch_count})" if pending_wunsch_count > 0 else "")
            self.update_single_tab_text("Wunschanfragen", tab_text_wunsch)

            # Urlaubsanträge
            pending_urlaub_count = get_pending_vacation_requests_count()
            tab_text_urlaub = "Urlaubsanträge" + (f" ({pending_urlaub_count})" if pending_urlaub_count > 0 else "")
            self.update_single_tab_text("Urlaubsanträge", tab_text_urlaub)

            # Bug-Reports (inkl. Feedback)
            open_bug_count = get_open_bug_reports_count() # Gesamtzahl offener Reports
            tab_text_bugs = "Bug-Reports" + (f" ({open_bug_count})" if open_bug_count > 0 else "")
            self.update_single_tab_text("Bug-Reports", tab_text_bugs)

            # Optional: Weitere Tabs hier hinzufügen
            # ...

        except Exception as e:
            # Fallback bei DB-Fehlern
            print(f"[FEHLER] Konnte Tab-Titel nicht aktualisieren: {e}")
            self.update_single_tab_text("Wunschanfragen", "Wunschanfragen (?)")
            self.update_single_tab_text("Urlaubsanträge", "Urlaubsanträge (?)")
            self.update_single_tab_text("Bug-Reports", "Bug-Reports (?)")
    # --------------------------------------------------------------------------------------


    # --- switch_to_tab, _load_dynamic_tab, etc. bleiben unverändert ---
    def switch_to_tab(self, tab_name):
        """Wechselt zum Tab mit dem gegebenen Namen (Basisname ohne Zähler)."""
        widget_ref = self.tab_frames.get(tab_name) # Holt Platzhalter oder echtes Widget
        if widget_ref and widget_ref.winfo_exists():
            try:
                # Prüfe, ob das Widget (Platzhalter oder echt) ein Tab im Notebook ist
                if self.notebook.nametowidget(widget_ref.winfo_parent()) == self.notebook:
                    print(f"[DEBUG] switch_to_tab: Wechsle zu Tab '{tab_name}'...")
                    self.notebook.select(widget_ref)
                    # Stelle sicher, dass der Ladevorgang ggf. ausgelöst wird
                    # (on_tab_changed wird durch select() getriggert)
                    # self.on_tab_changed(None) # Nicht nötig, da select() das Event auslöst
                else:
                    print(f"[DEBUG] switch_to_tab: Frame für '{tab_name}' ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError) as e:
                # Fehler beim Zugriff auf das Widget oder dessen Parent
                print(
                    f"[DEBUG] switch_to_tab: Fehler beim Auswählen von '{tab_name}': {e} (Widget ungültig/Elternteil nicht Notebook).")
        else:
             # Widget nicht gefunden oder bereits zerstört
            print(f"[DEBUG] switch_to_tab: Tab/Frame '{tab_name}' nicht gefunden oder zerstört.")


    def _load_dynamic_tab(self, tab_name, TabClass, *args):
        # (Bleibt synchron für spezielle Dialog-ähnliche Tabs)
        # 1. Prüfen, ob Tab schon geladen und gültig ist -> dann auswählen
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                        print(f"[GUI - dyn] Tab '{tab_name}' bereits geladen und gültig. Wechsle...")
                        self.notebook.select(frame)
                        return # Fertig
                except (tk.TclError, KeyError):
                    print(f"[GUI - dyn] Tab '{tab_name}' war geladen, aber Widget ungültig. Lade neu.")
                    pass # Fehler ignorieren, Tab neu laden
            # Wenn wir hier sind, ist der Tab zwar geladen, aber das Widget ist ungültig oder kein Tab mehr
            if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
            if tab_name in self.tab_frames: del self.tab_frames[tab_name] # Entferne ungültige Referenz

        # 2. Prüfen, ob Tab gerade lädt (sollte bei synchron nicht passieren, aber sicherheitshalber)
        if tab_name in self.loading_tabs:
            print(f"[GUI - dyn] WARNUNG: {tab_name} lädt bereits (sollte bei sync nicht sein). Breche ab.")
            return

        # 3. Ladevorgang starten (synchron)
        print(f"[LazyLoad] Lade dynamischen Tab: {tab_name} (im GUI-Thread)")
        self.loading_tabs.add(tab_name) # Markieren als "am Laden"

        # Erstelle Platzhalter temporär, zeige Ladeanzeige
        placeholder_frame = ttk.Frame(self.notebook, padding=20)
        loading_label = ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16))
        loading_label.pack(expand=True, anchor="center")
        tab_index = -1
        try:
            self.notebook.unbind("<<NotebookTabChanged>>") # Event kurz aus
            self.notebook.add(placeholder_frame, text=tab_name) # Am Ende hinzufügen
            self.notebook.select(placeholder_frame) # Auswählen
            tab_index = self.notebook.index(placeholder_frame) # Index merken
            # self.tab_frames[tab_name] = placeholder_frame # *Nicht* speichern, da es sofort ersetzt wird
        finally:
            self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed) # Event wieder an
        self.update_idletasks() # Ladeanzeige sofort zeigen

        real_tab = None
        try:
            # Erstelle die echte Tab-Instanz
            # (Diese Initialisierungen müssen synchron bleiben)
            if TabClass.__name__ == "UserTabSettingsTab":
                real_tab = TabClass(self.notebook, *args)
            elif TabClass.__name__ in ["RequestLockTab", "PasswordResetRequestsWindow"]:
                 real_tab = TabClass(self.notebook, *args) # Annahme: Diese brauchen nur master
            # --- NEU: Korrekte Initialisierung für andere Typen ---
            elif TabClass.__name__ == "SettingsTab":
                 real_tab = TabClass(self.notebook, self.user_data)
            elif TabClass.__name__ == "ShiftTypesTab":
                 real_tab = TabClass(self.notebook, self)
            # --- ENDE NEU ---
            else:
                # Fallback für andere, die vielleicht nur 'master' brauchen
                print(f"[WARNUNG] _load_dynamic_tab: Unbekannter Typ {TabClass.__name__}, versuche mit (master).")
                try:
                    real_tab = TabClass(self.notebook) # Fallback 1: Nur master
                except TypeError:
                    print(f"[FEHLER] _load_dynamic_tab: {TabClass.__name__} konnte nicht initialisiert werden.")
                    raise # Fehler weitergeben

            # Ersetze Platzhalter durch echten Tab
            if placeholder_frame.winfo_exists(): # Prüfe nochmal, ob Platzhalter noch da ist
                tab_options = self.notebook.tab(placeholder_frame) # Optionen vom Platzhalter holen
                if real_tab and tab_options and tab_index != -1:
                    try:
                        self.notebook.unbind("<<NotebookTabChanged>>")
                        self.notebook.forget(placeholder_frame) # Platzhalter entfernen
                        # Echten Tab an der gemerkten Position einfügen
                        self.notebook.insert(tab_index if tab_index < self.notebook.index('end') else 'end', real_tab, **tab_options)
                        self.notebook.select(real_tab) # Zum neuen Tab wechseln
                    finally:
                        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

                    self.loaded_tabs.add(tab_name)
                    self.tab_frames[tab_name] = real_tab # Referenz auf echten Tab speichern
                    print(f"[GUI] Dynamischer Tab '{tab_name}' erfolgreich eingesetzt.")
                else:
                    # Sollte nicht passieren, wenn TabClass gültig war
                    raise Exception("Konnte dyn. Tab-Objekt, Optionen oder Index nicht ermitteln.")
            else:
                # Platzhalter wurde irgendwie zerstört, bevor er ersetzt werden konnte
                # Das ist schlecht, da der echte Tab nicht eingefügt werden kann.
                raise tk.TclError(f"Platzhalter für dyn. Tab {tab_name} existierte nicht mehr beim Ersetzen.")

        except Exception as e:
            print(f"[GUI] FEHLER beim Laden/Einfügen von dynamischem Tab '{tab_name}': {e}")
            if placeholder_frame and placeholder_frame.winfo_exists():
                # Fehler im (noch vorhandenen) Platzhalter anzeigen
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
            else:
                # Platzhalter weg UND Fehler -> Nur Meldung, Tab ist verloren
                print(
                    f"[GUI] FEHLER: Platzhalter für {tab_name} existierte nicht mehr bei Fehlerbehandlung (dyn. Tab).")
                messagebox.showerror("Fehler beim Laden", f"Konnte Tab '{tab_name}' nicht laden:\n{e}", parent=self)
        finally:
             # Sicherstellen, dass der Lade-Status entfernt wird, egal was passiert
            if tab_name in self.loading_tabs:
                self.loading_tabs.remove(tab_name)
    # --------------------------------------------------------------------------------------


    # --- open_request_lock_window, open_user_tab_settings, etc. bleiben unverändert ---
    def open_request_lock_window(self):
        self._load_dynamic_tab("Antragssperre", RequestLockTab, self) # self wird als admin_window übergeben

    def open_user_tab_settings(self):
        all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen", "Chat"]
        # Übergibt all_user_tab_names als '*args' an _load_dynamic_tab -> UserTabSettingsTab.__init__
        self._load_dynamic_tab("Benutzer-Reiter", UserTabSettingsTab, all_user_tab_names)

    def open_password_resets_window(self):
        self._load_dynamic_tab("Passwort-Resets", PasswordResetRequestsWindow, self) # self wird als admin_window übergeben

    def open_shift_types_window(self):
        """Wechselt zum Schichtarten-Tab oder lädt ihn."""
        print("[DEBUG] Wechsle/Lade Schichtarten-Tab...")
        self.switch_to_tab("Schichtarten")
    # --------------------------------------------------------------------------------------

    # --- on_close, logout, setup_header bleiben unverändert ---
    def on_close(self):
        print("[DEBUG] MainAdminWindow.on_close aufgerufen.")
        self.save_shift_frequency()
        try:
            log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        except Exception as e:
            print(f"[FEHLER] Konnte Logout nicht loggen: {e}")
        self.app.on_app_close() # Schließt die gesamte Anwendung

    def logout(self):
        print("[DEBUG] MainAdminWindow.logout aufgerufen.")
        self.save_shift_frequency()
        try:
            log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        except Exception as e:
            print(f"[FEHLER] Konnte Logout nicht loggen: {e}")
        # Ruft die Logout-Methode der Hauptanwendung auf, die dieses Fenster schließt
        # und das Login-Fenster wieder anzeigt.
        self.app.on_logout(self)

    def setup_header(self):
        # Frame für Benachrichtigungen (links)
        self.notification_frame = ttk.Frame(self.header_frame)
        self.notification_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        # Initial leer, wird von update_header_notifications gefüllt
        ttk.Label(self.notification_frame, text="").pack()

        # Menü-Button für Einstellungen (rechts)
        settings_menubutton = ttk.Menubutton(self.header_frame, text="⚙️ Einstellungen", style='Settings.TMenubutton')
        settings_menubutton.pack(side="right", padx=5)
        settings_menu = tk.Menu(settings_menubutton, tearoff=0) # Das Dropdown-Menü
        settings_menubutton["menu"] = settings_menu

        # Menüeinträge hinzufügen
        settings_menu.add_command(label="Schichtarten", command=self.open_shift_types_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Mitarbeiter-Sortierung", command=self.open_user_order_window) # Diese Funktion wird angepasst
        settings_menu.add_command(label="Schicht-Sortierung", command=self.open_shift_order_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Besetzungsregeln", command=self.open_staffing_rules_window)
        settings_menu.add_command(label="Feiertage", command=self.open_holiday_settings_window)
        settings_menu.add_command(label="Sondertermine", command=self.open_event_settings_window)
        settings_menu.add_command(label="Farbeinstellungen", command=self.open_color_settings_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Anfragen verwalten", command=self.open_request_settings_window)
        settings_menu.add_command(label="Antragssperre", command=self.open_request_lock_window)
        settings_menu.add_command(label="Benutzer-Reiter sperren", command=self.open_user_tab_settings)
        settings_menu.add_command(label="Planungs-Helfer", command=self.open_planning_assistant_settings)
        settings_menu.add_separator()
        # --- Verlinkung zum Wartungstab ---
        settings_menu.add_command(label="Datenbank Wartung", command=lambda: self.switch_to_tab("Wartung"))
    # --------------------------------------------------------------------------------------


    # --- _run_db_update_with_confirmation und alte apply_... Methoden bleiben unverändert ---
    def _run_db_update_with_confirmation(self, message, db_function):
        """ Führt eine DB-Update-Funktion nach Bestätigung aus. """
        if messagebox.askyesno("Bestätigung erforderlich", message, parent=self):
            try:
                success, result_message = db_function()
                if success:
                    messagebox.showinfo("Update erfolgreich", result_message, parent=self)
                else:
                    messagebox.showerror("Update fehlgeschlagen", result_message, parent=self)
            except Exception as e:
                # Fängt unerwartete Fehler während der DB-Operation ab
                print(f"FEHLER bei DB Update ({db_function.__name__}): {e}")
                messagebox.showerror("Schwerer Datenbankfehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=self)

    # --- Alte DB-Fix Methoden (nicht mehr im Menü, aber evtl. vom Wartungstab genutzt) ---
    def apply_archived_date_fix(self):
        msg = "Dies fügt die Spalte 'archived_date' zur Benutzer-Tabelle hinzu, falls sie fehlt.\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_add_archived_date)

    def apply_is_archived_fix(self):
        msg = "Dies fügt die Spalte 'is_archived' zur Benutzer-Tabelle hinzu, falls sie fehlt.\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_add_is_archived)

    def apply_all_users_approval_fix(self):
        # Zusätzliche Warnung wegen der drastischen Auswirkung
        if messagebox.askyesno("ACHTUNG: Kritische Aktion",
                               "Sind Sie ABSOLUT SICHER, dass Sie ALLE bestehenden Benutzerkonten auf 'freigeschaltet' setzen möchten?\nDies kann nicht einfach rückgängig gemacht werden!",
                               icon='warning', parent=self):
            # Erneute Bestätigung innerhalb der Hilfsfunktion
            self._run_db_update_with_confirmation("Wirklich ALLE Benutzer freischalten?", run_db_fix_approve_all_users)

    def apply_is_approved_fix(self):
        msg = "Dies fügt die Spalte 'is_approved' zur Benutzer-Tabelle hinzu, um die manuelle Freischaltung zu ermöglichen.\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_is_approved)

    def apply_database_fix(self):
        msg = "Dies führt notwendige Updates an der Datenbank für die Chat-Funktionalität durch (fügt Spalten/Tabellen hinzu, falls benötigt).\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_v1)
    # --------------------------------------------------------------------------------------

    # --- setup_footer, check_chat_notifications, go_to_chat bleiben unverändert ---
    def setup_footer(self):
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def check_chat_notifications(self):
        try:
            # Hole aktuelle ungelesene Nachrichten
            new_senders = get_senders_with_unread_messages(self.user_data['id'])

            # Prüfe, ob Benachrichtigungsleiste aktuell sichtbar ist
            is_visible = self.chat_notification_frame.winfo_ismapped()

            # Aktion nur nötig, wenn neue Nachrichten da sind ODER die Leiste verschwinden soll
            if new_senders or is_visible:
                # Alte Inhalte löschen (nur wenn nötig)
                if is_visible:
                    for widget in self.chat_notification_frame.winfo_children():
                        widget.destroy()

                if new_senders:
                    latest_sender_id = new_senders[0]['sender_id'] # Nimm den neuesten Absender für den Klick
                    total_unread = sum(s['unread_count'] for s in new_senders)
                    action = lambda event=None, uid=latest_sender_id: self.go_to_chat(uid)

                    # Leiste anzeigen (pack), falls sie nicht schon sichtbar ist
                    if not is_visible:
                        self.chat_notification_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)

                    # Event-Binding für Klick auf die Leiste selbst
                    self.chat_notification_frame.bind("<Button-1>", action)

                    # Text-Label erstellen
                    label_text = f"Sie haben {total_unread} neue Nachricht(en)! Hier klicken zum Anzeigen."
                    notification_label = tk.Label(self.chat_notification_frame, text=label_text, bg='tomato', fg='white',
                                                  font=('Segoe UI', 12, 'bold'), cursor="hand2")
                    notification_label.pack(side='left', padx=15, pady=5);
                    notification_label.bind("<Button-1>", action) # Auch Label klickbar machen

                    # Optional: Button "Anzeigen" rechts
                    # show_button = ttk.Button(self.chat_notification_frame, text="Anzeigen", command=action)
                    # show_button.pack(side='right', padx=15)
                else:
                    # Keine neuen Nachrichten -> Leiste ausblenden (falls sie sichtbar war)
                    if is_visible:
                        self.chat_notification_frame.pack_forget()

        except Exception as e:
            # Fehler beim Abrufen -> Leiste sicherheitshalber ausblenden
            print(f"[FEHLER] bei check_chat_notifications: {e}")
            if self.chat_notification_frame.winfo_ismapped():
                self.chat_notification_frame.pack_forget()

        finally:
            # Nächsten Check planen (z.B. alle 10 Sekunden)
            self.after(10000, self.check_chat_notifications)


    def go_to_chat(self, user_id):
        """Wechselt zum Chat-Tab und versucht, den Chat mit der user_id zu öffnen."""
        print(f"[DEBUG] go_to_chat aufgerufen für User ID: {user_id}")
        self.switch_to_tab("Chat") # Löst ggf. das Laden aus

        # Definiere eine Hilfsfunktion, die prüft, ob der Tab bereit ist
        def _select_user_when_ready():
            # 1. Prüfen, ob der Chat-Tab jetzt geladen ist
            if "Chat" in self.loaded_tabs:
                chat_tab = self.tab_frames.get("Chat")
                # 2. Prüfen, ob das Widget gültig ist und die Methode hat
                if chat_tab and chat_tab.winfo_exists() and hasattr(chat_tab, "select_user"):
                    try:
                        print(f"[DEBUG] Chat-Tab ist geladen, rufe select_user({user_id}) auf.")
                        chat_tab.select_user(user_id) # Rufe die Methode im ChatTab auf
                        # Nach erfolgreichem Anzeigen, Benachrichtigung ausblenden
                        if self.chat_notification_frame.winfo_ismapped():
                           self.chat_notification_frame.pack_forget()
                           print("[DEBUG] Chat-Benachrichtigung ausgeblendet.")
                    except Exception as e:
                        print(f"[FEHLER] beim Aufrufen von chat_tab.select_user für {user_id}: {e}")
                # Debugging-Ausgaben für andere Fälle
                elif chat_tab and not chat_tab.winfo_exists():
                    print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab Widget existiert nicht mehr.")
                elif not chat_tab:
                    print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab nicht im Frame-Dictionary gefunden.")
                else: # chat_tab existiert, hat aber keine select_user Methode
                    print("[FEHLER] go_to_chat/_select_user_when_ready: Chat-Tab hat keine 'select_user' Methode.")

            # 3. Wenn Tab noch lädt ODER noch gar nicht geladen -> erneut versuchen
            elif "Chat" in self.loading_tabs or ("Chat" not in self.loaded_tabs and "Chat" in self.tab_definitions):
                print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab noch nicht geladen/wird geladen, warte 200ms...")
                # Erneuter Aufruf nach kurzer Wartezeit
                self.after(200, _select_user_when_ready)
            else:
                # Sollte nicht passieren, aber als Fallback
                print(
                    f"[DEBUG] go_to_chat/_select_user_when_ready: Unerwarteter Status für Chat-Tab (UserID: {user_id}). Breche Wartevorgang ab.")

        # Starte den Wartevorgang mit kurzer initialer Verzögerung
        self.after(50, _select_user_when_ready)
    # --------------------------------------------------------------------------------------


    # --- check_for_updates, open_bug_report_dialog, refresh_antragssperre_views, update_header_notifications bleiben unverändert ---
    def check_for_updates(self):
        """ Regelmäßiger Check für Benachrichtigungen, offene Anträge etc. """
        print("[DEBUG] check_for_updates gestartet.")
        try:
            # 1. Tab-Titel aktualisieren (z.B. Zähler für Anträge/Bugs)
            self.update_tab_titles()
            # 2. Header-Benachrichtigungen aktualisieren (Buttons für dringende Aktionen)
            self.update_header_notifications()

            # 3. Spezifische Checks für geladene Tabs (optional)
            # Beispiel: Prüfe auf neue Benutzerfreischaltungen im Mitarbeiter-Tab
            if "Mitarbeiter" in self.loaded_tabs:
                user_tab = self.tab_frames.get("Mitarbeiter")
                # Sicherstellen, dass das Widget existiert und die Methode hat
                if user_tab and user_tab.winfo_exists() and hasattr(user_tab, 'check_pending_approvals'):
                    try:
                        print("[DEBUG] check_for_updates: Prüfe ausstehende Freischaltungen im Mitarbeiter-Tab.")
                        user_tab.check_pending_approvals()
                    except Exception as e_user:
                         print(f"[FEHLER] bei user_tab.check_pending_approvals: {e_user}")

            # Beispiel: Chat-Benachrichtigungen (wird separat behandelt, hier evtl. redundant)
            # self.check_chat_notifications() # Wird bereits in eigener Schleife aufgerufen

        except Exception as e:
            # Allgemeiner Fehler im Update-Prozess
            print(f"[FEHLER] in check_for_updates: {e}")

        finally:
            # Nächsten Check planen (z.B. alle 60 Sekunden)
            self.after(60000, self.check_for_updates)

    def open_bug_report_dialog(self):
        """ Öffnet den Dialog zum Melden eines Bugs. """
        # Übergibt check_for_updates als Callback, damit die Tab-Titel (Bug-Zähler)
        # und Header-Benachrichtigungen nach dem Senden aktualisiert werden.
        BugReportDialog(self, self.user_data['id'], self.check_for_updates)

    def refresh_antragssperre_views(self):
        """ Aktualisiert Ansichten, die von der Antragssperre betroffen sind. """
        print("[DEBUG] refresh_antragssperre_views aufgerufen.")

        # 1. Schichtplan-Tab aktualisieren (falls geladen)
        #    Der Schichtplan zeigt möglicherweise an, ob Tage gesperrt sind.
        if "Schichtplan" in self.loaded_tabs:
            plan_tab = self.tab_frames.get("Schichtplan")
            # Prüfe, ob Widget gültig ist und die Methode hat
            if plan_tab and plan_tab.winfo_exists() and hasattr(plan_tab, 'update_lock_status'):
                try:
                    print("[DEBUG] -> Aktualisiere Sperrstatus im Schichtplan-Tab.")
                    plan_tab.update_lock_status()
                except Exception as e:
                    print(f"[FEHLER] bei plan_tab.update_lock_status: {e}")

        # 2. Antragssperre-Tab selbst aktualisieren (falls geladen)
        #    Damit die Liste der Sperren aktuell ist.
        if "Antragssperre" in self.loaded_tabs: # Name des Tabs ggf. anpassen
            lock_tab = self.tab_frames.get("Antragssperre") # Name des Tabs ggf. anpassen
            # Prüfe, ob Widget gültig ist und die Methode hat
            if lock_tab and lock_tab.winfo_exists() and hasattr(lock_tab, 'load_locks_for_year'):
                try:
                    print("[DEBUG] -> Lade Sperren neu im Antragssperre-Tab.")
                    # Annahme: Der Tab merkt sich das aktuell angezeigte Jahr
                    lock_tab.load_locks_for_year()
                except Exception as e:
                    print(f"[FEHLER] bei lock_tab.load_locks_for_year: {e}")

        # Optional: Weitere Tabs aktualisieren, falls sie Sperrinformationen anzeigen
        # z.B. Wunschanfragen-Tab, Urlaubsanträge-Tab


    def update_header_notifications(self):
        """ Aktualisiert die Benachrichtigungs-Buttons im Header. """
        # Alte Buttons entfernen
        for widget in self.notification_frame.winfo_children():
            widget.destroy()

        notifications = []
        has_error = False # Flag für DB-Fehler

        try:
            # 1. Passwort-Resets
            pending_password_resets = get_pending_password_resets_count()
            if pending_password_resets > 0:
                notifications.append(
                    {"text": f"{pending_password_resets} Passwort-Reset(s)", "bg": "mediumpurple", "fg": "white",
                     "action": self.open_password_resets_window}) # Direkter Funktionsaufruf öffnet dyn. Tab

            # 2. Wunschfrei-Anfragen
            pending_wunsch_count = len(get_pending_wunschfrei_requests())
            if pending_wunsch_count > 0:
                notifications.append(
                    {"text": f"{pending_wunsch_count} Offene Wunschanfrage(n)", "bg": "orange", "fg": "black",
                     "tab": "Wunschanfragen"}) # Name des Ziel-Tabs

            # 3. Urlaubsanträge
            pending_urlaub_count = get_pending_vacation_requests_count()
            if pending_urlaub_count > 0:
                notifications.append(
                    {"text": f"{pending_urlaub_count} Offene Urlaubsanträge", "bg": "lightblue", "fg": "black",
                     "tab": "Urlaubsanträge"})

            # 4. User-Feedback zu Bug-Reports (höhere Priorität als nur offene)
            user_feedback_count = get_reports_with_user_feedback_count()
            if user_feedback_count > 0:
                notifications.append(
                    {"text": f"{user_feedback_count} User-Feedback(s)", "bg": "springgreen", "fg": "black",
                     "tab": "Bug-Reports"})

            # 5. Offene Bug-Reports (nur zählen, wenn KEIN User-Feedback)
            open_bug_count = get_open_bug_reports_count()
            actual_open_bugs = open_bug_count - user_feedback_count # Nur die ohne Feedback
            if actual_open_bugs > 0:
                 notifications.append({"text": f"{actual_open_bugs} Offene Bug-Report(s)", "bg": "tomato", "fg": "white", "tab": "Bug-Reports"})

            # Optional: Neue Benutzer zur Freischaltung (falls implementiert)
            # pending_approval_count = ...
            # if pending_approval_count > 0:
            #    notifications.append({"text": f"{pending_approval_count} Benutzer-Freischaltung(en)", ... "tab": "Mitarbeiter"})


        except Exception as e:
            # Fehler beim Abrufen der Daten -> Fehlermeldung anzeigen
            print(f"[FEHLER] beim Abrufen der Benachrichtigungsdaten: {e}")
            has_error = True

        # Buttons erstellen oder Meldung anzeigen
        if has_error:
             ttk.Label(self.notification_frame, text="Fehler beim Laden der Benachrichtigungen!", foreground="red", font=('Segoe UI', 10, 'bold')).pack(padx=5)
        elif not notifications:
            # Keine Benachrichtigungen vorhanden
            ttk.Label(self.notification_frame, text="Keine neuen Benachrichtigungen",
                      font=('Segoe UI', 10, 'italic')).pack(padx=5)
        else:
            # Benachrichtigungs-Buttons erstellen
            for i, notif in enumerate(notifications):
                # Dynamischer Style-Name, um Farben pro Button zu setzen
                style_name = f'Notif{i}.TButton'
                self.style.configure(style_name, background=notif["bg"], foreground=notif.get("fg", "black"), # Fallback für fg
                                     font=('Segoe UI', 10, 'bold'), padding=(10, 5))
                # Hover-Effekt definieren (leicht abgedunkelte Farbe)
                self.style.map(style_name, background=[('active', self._calculate_hover_color(notif["bg"]))],
                               relief=[('pressed', 'sunken')]) # Gedrückt-Effekt

                # Aktion für den Button festlegen
                command = None
                if "action" in notif: # Direkte Funktion (z.B. für dyn. Tabs)
                    command = notif["action"]
                else: # Zu einem Tab wechseln
                    tab_name = notif.get("tab")
                    if tab_name:
                        # Wichtig: Lambda verwenden, um den aktuellen Wert von tab_name zu binden
                        command = lambda tab=tab_name: self.switch_to_tab(tab)

                # Button erstellen, wenn eine Aktion definiert ist
                if command:
                    btn = ttk.Button(self.notification_frame, text=notif["text"], style=style_name, command=command)
                    # Gleichmäßig im Frame verteilen
                    btn.pack(side="left", padx=5, fill="x", expand=True)
    # --------------------------------------------------------------------------------------


    # --- _calculate_hover_color, load_all_data, refresh_all_tabs, etc. bleiben unverändert ---
    def _calculate_hover_color(self, base_color):
        """Dunkelt eine Hex-Farbe leicht ab für den Hover-Effekt."""
        try:
            # Versuche, benannte Farben aufzulösen
            if not base_color.startswith('#'):
                try:
                    rgb = self.winfo_rgb(base_color) # Gibt (r, g, b) im 16-bit Format
                    r, g, b = [x // 256 for x in rgb] # Konvertiere zu 8-bit
                    hex_color = f"#{r:02x}{g:02x}{b:02x}"
                except tk.TclError:
                    return '#e0e0e0' # Sicherer Fallback für unbekannte Namen
            else:
                hex_color = base_color

            # Prüfe gültiges Hex-Format
            if len(hex_color) not in [4, 7]: return '#e0e0e0'

            # Hex zu RGB
            if len(hex_color) == 4: # #RGB
                r, g, b = [int(c * 2, 16) for c in hex_color[1:]]
            else: # #RRGGBB
                r, g, b = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]

            # Abdunkeln
            factor = 0.85
            r = max(0, int(r * factor))
            g = max(0, int(g * factor))
            b = max(0, int(b * factor))

            # Zurück zu Hex
            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
             # Fallback bei Konvertierungsfehlern
            return '#e0e0e0'


    def load_all_data(self):
        """Lädt alle notwendigen Basisdaten (Schichtarten, Regeln, Feiertage, Events)."""
        print("[DEBUG] load_all_data gestartet.")
        # Lade Daten in Instanzvariablen
        try:
            self.load_shift_types() # Lädt self.shift_types_data
        except Exception as e_st:
            print(f"[FEHLER] Kritisch: Schichtarten konnten nicht geladen werden: {e_st}")
            messagebox.showerror("Kritischer Ladefehler", f"Schichtarten konnten nicht geladen werden:\n{e_st}\nEinige Funktionen sind möglicherweise beeinträchtigt.", parent=self)
            self.shift_types_data = {} # Sicherer Fallback

        try:
             self.load_staffing_rules() # Lädt self.staffing_rules
        except Exception as e_sr:
            print(f"[FEHLER] Besetzungsregeln konnten nicht geladen werden: {e_sr}")
            messagebox.showwarning("Ladefehler", f"Besetzungsregeln konnten nicht geladen werden:\n{e_sr}\nVerwende Standardregeln.", parent=self)
            # self.staffing_rules wird in load_staffing_rules schon auf Default gesetzt

        # Lade Feiertage und Events für das *aktuelle* Kalenderjahr beim Start
        current_year = date.today().year
        try:
            self._load_holidays_for_year(current_year) # Lädt self.current_year_holidays
        except Exception as e_ho:
            print(f"[FEHLER] Feiertage für {current_year} konnten nicht geladen werden: {e_ho}")
            messagebox.showwarning("Ladefehler", f"Feiertage für {current_year} konnten nicht geladen werden:\n{e_ho}", parent=self)
            self.current_year_holidays = {}

        try:
            self._load_events_for_year(current_year) # Lädt self.events
        except Exception as e_ev:
            print(f"[FEHLER] Sondertermine für {current_year} konnten nicht geladen werden: {e_ev}")
            messagebox.showwarning("Ladefehler", f"Sondertermine für {current_year} konnten nicht geladen werden:\n{e_ev}", parent=self)
            self.events = {}

        print(f"[DEBUG] Basisdaten für {current_year} initial geladen.")

    def refresh_all_tabs(self):
        """Lädt alle Basisdaten neu und aktualisiert alle BEREITS GELADENEN Tabs."""
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs...")
        self.load_all_data() # Lädt Schichtarten, Regeln, Feiertage, Events neu

        loaded_tab_names = list(self.loaded_tabs) # Kopie, falls Set während Iteration geändert wird
        print(f"[DEBUG] Geladene Tabs für Refresh: {loaded_tab_names}")

        for tab_name in loaded_tab_names:
            frame = self.tab_frames.get(tab_name)
            # Prüfen, ob das Frame-Objekt existiert und noch ein gültiges Widget ist
            if frame and frame.winfo_exists():
                try:
                    # Sicherstellen, dass es immer noch ein Tab im Notebook ist
                    parent_is_notebook = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if parent_is_notebook:
                        # Versuche, eine passende Refresh-Methode aufzurufen
                        refreshed = False
                        if hasattr(frame, 'refresh_data'):
                            print(f"[DEBUG] -> rufe refresh_data() für {tab_name} auf")
                            frame.refresh_data()
                            refreshed = True
                        elif hasattr(frame, 'refresh_plan'): # Speziell für ShiftPlanTab
                            print(f"[DEBUG] -> rufe refresh_plan() für {tab_name} auf")
                            frame.refresh_plan()
                            refreshed = True
                        elif hasattr(frame, 'load_data'): # Fallback für Tabs mit 'load_data'
                             print(f"[DEBUG] -> rufe load_data() für {tab_name} auf")
                             frame.load_data()
                             refreshed = True
                        # Optional: Weitere spezifische Refresh-Methoden hier prüfen
                        # elif hasattr(frame, 'reload_list'): ...

                        if not refreshed:
                             print(f"[WARNUNG] Tab '{tab_name}' hat keine bekannte Refresh-Methode (refresh_data, refresh_plan, load_data).")

                except (tk.TclError, KeyError) as e:
                     # Fehler kann auftreten, wenn Widget-Hierarchie unerwartet oder Widget zerstört wird
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
                except Exception as e:
                    # Unerwartete Fehler während der Refresh-Methode des Tabs
                    print(f"[FEHLER] Unerwarteter Fehler beim Refresh von Tab '{tab_name}': {e}")
            else:
                 # Frame nicht gefunden oder zerstört -> Bereinigen
                 print(f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                 if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                 if tab_name in self.tab_frames: del self.tab_frames[tab_name]


        self.check_for_updates() # Aktualisiere Header etc. nach dem Refresh
        print("[DEBUG] Refresh aller geladenen Tabs abgeschlossen.")

    def load_shift_types(self):
        """Lädt alle Schichtarten aus der Datenbank."""
        try:
            # Holt alle Schichtarten als Liste von Dictionaries
            all_types = get_all_shift_types()
            # Konvertiert die Liste in ein Dictionary, wobei das Kürzel der Schlüssel ist
            # Beispiel: {'F': {'id': 1, 'name': 'Frühdienst', 'abbreviation': 'F', ...}, ...}
            self.shift_types_data = {st['abbreviation']: st for st in all_types}
            print(f"[DEBUG] {len(self.shift_types_data)} Schichtarten geladen.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Schichtarten: {e}")
            messagebox.showerror("Datenbankfehler", f"Schichtarten konnten nicht geladen werden:\n{e}", parent=self)
            self.shift_types_data = {} # Sicherer Fallback auf leeres Dictionary

    def load_staffing_rules(self):
        """Lädt die Mindestbesetzungsregeln aus der Konfiguration (JSON in DB)."""
        try:
            # Lädt JSON-String aus DB und parst ihn zu Python-Dict
            rules = load_config_json(MIN_STAFFING_RULES_CONFIG_KEY)

            # Standardfarben als Fallback definieren
            default_colors = {
                "alert_bg": "#FF5555",          # Unterbesetzung
                "overstaffed_bg": "#FFFF99",    # Überbesetzung
                "success_bg": "#90EE90",        # Korrekte Besetzung
                "weekend_bg": "#EAF4FF",        # Wochenende Hintergrund
                "holiday_bg": "#FFD700",        # Feiertag Hintergrund
                "violation_bg": "#FF5555",      # Regelverletzung (z.B. max. Schichten)
                "Ausstehend": "orange",         # Ausstehende Wunschanfrage
                "Admin_Ausstehend": "#E0B0FF"   # Ausstehender Urlaubsantrag
                # Weitere Farben nach Bedarf...
            }
            # Standardstruktur der Regeln mit leeren Dictionaries als Fallback
            defaults = {
                "Mo-Do": {}, "Fr": {}, "Sa-So": {}, "Holiday": {}, "Daily": {},
                "Colors": default_colors
            }

            # Wenn keine Regeln geladen wurden oder das Format ungültig ist
            if not rules or not isinstance(rules, dict):
                print("[WARNUNG] Besetzungsregeln nicht gefunden oder ungültig, verwende Standard.")
                self.staffing_rules = defaults # Komplette Defaults verwenden
            else:
                # Regeln wurden geladen -> Validieren und ggf. mit Defaults auffüllen
                # 1. Sicherstellen, dass alle Hauptkategorien (Mo-Do, Fr, etc.) existieren
                for key, default_val in defaults.items():
                    if key not in rules:
                        rules[key] = default_val # Fehlende Kategorie hinzufügen
                    # 2. Speziell für Farben: Sicherstellen, dass alle Standardfarben existieren
                    elif key == "Colors":
                         # Prüfen, ob der Wert für "Colors" ein Dictionary ist
                         if isinstance(rules[key], dict):
                             # Gehe durch alle Standardfarben und füge sie hinzu, falls sie fehlen
                             for ckey, cval in default_colors.items():
                                 if ckey not in rules["Colors"]:
                                     print(f"[DEBUG] Füge fehlende Standardfarbe hinzu: Colors['{ckey}'] = '{cval}'")
                                     rules["Colors"][ckey] = cval
                         else:
                             # Wenn "Colors" kein Dict ist (ungültig), überschreibe es komplett
                             print("[WARNUNG] Ungültiger 'Colors'-Eintrag in Besetzungsregeln, verwende Standardfarben.")
                             rules["Colors"] = default_colors

                self.staffing_rules = rules # Die validierten/ergänzten Regeln speichern
                print("[DEBUG] Besetzungsregeln geladen und validiert.")

        except Exception as e:
            # Allgemeiner Fehler beim Laden oder Verarbeiten
            print(f"[FEHLER] beim Laden der Besetzungsregeln: {e}")
            messagebox.showerror("Ladefehler", f"Besetzungsregeln konnten nicht geladen werden:\n{e}\nVerwende Standardregeln.", parent=self)
            # Sicherer Fallback auf komplette Defaults
            self.staffing_rules = defaults


    def _load_holidays_for_year(self, year):
        """Lädt die Feiertage für ein spezifisches Jahr mithilfe des HolidayManagers."""
        try:
            # Ruft die statische Methode des Managers auf
            self.current_year_holidays = HolidayManager.get_holidays_for_year(year)
            print(f"[DEBUG] Feiertage für {year} geladen ({len(self.current_year_holidays)} Einträge).")
        except Exception as e:
            # Fehler beim Laden (z.B. DB-Problem im Manager)
            print(f"[FEHLER] beim Laden der Feiertage für {year}: {e}")
            messagebox.showwarning("Fehler Feiertage", f"Feiertage für {year} konnten nicht geladen werden:\n{e}", parent=self)
            self.current_year_holidays = {} # Leeres Dictionary als sicherer Fallback


    def _load_events_for_year(self, year):
        """Lädt die Sondertermine (Events) für ein spezifisches Jahr mithilfe des EventManagers."""
        try:
             # Ruft die statische Methode des Managers auf
            self.events = EventManager.get_events_for_year(year)
            print(f"[DEBUG] Sondertermine für {year} geladen ({len(self.events)} Einträge).")
        except Exception as e:
            # Fehler beim Laden (z.B. DB-Problem im Manager)
            print(f"[FEHLER] beim Laden der Sondertermine für {year}: {e}")
            messagebox.showwarning("Fehler Sondertermine", f"Sondertermine für {year} konnten nicht geladen werden:\n{e}", parent=self)
            self.events = {} # Leeres Dictionary als sicherer Fallback
    # --------------------------------------------------------------------------------------


    # --- is_holiday, get_event_type, get_contrast_color, load_shift_frequency, save_shift_frequency, reset_shift_frequency, get_allowed_roles bleiben unverändert ---
    def is_holiday(self, check_date):
        """Prüft, ob ein gegebenes Datum ein Feiertag im aktuell geladenen Jahr ist."""
        # Sicherstellen, dass check_date ein date-Objekt ist
        if not isinstance(check_date, date):
            try:
                if hasattr(check_date, 'date'): # Konvertiere datetime zu date
                    check_date = check_date.date()
                else: # Versuche String-Konvertierung (ISO-Format YYYY-MM-DD)
                    check_date = date.fromisoformat(str(check_date))
            except (TypeError, ValueError):
                print(f"[WARNUNG] is_holiday: Ungültiges Datumformat erhalten: {check_date}")
                return False # Ungültiges Format -> kein Feiertag

        # Prüfe, ob das Jahr des Datums mit dem Jahr übereinstimmt, für das Feiertage geladen wurden
        # TODO: Dynamisches Nachladen implementieren, wenn Feiertage für mehrere Jahre benötigt werden
        # Aktuell wird angenommen, dass immer nur das Jahr von self.current_display_date relevant ist
        # Besser: Direkt das Jahr aus check_date verwenden und ggf. nachladen
        target_year = check_date.year
        # Beispiel: Wenn Feiertage noch nicht für dieses Jahr geladen wurden
        # if target_year != getattr(self, '_loaded_holiday_year', None):
        #    self._load_holidays_for_year(target_year)
        #    self._loaded_holiday_year = target_year # Merken, welches Jahr geladen ist

        # Prüfe, ob das Datum im Dictionary der geladenen Feiertage für das Zieljahr vorhanden ist
        return check_date in self.current_year_holidays # Prüft nur im aktuell geladenen Jahr


    def get_event_type(self, current_date):
        """Gibt den Typ des Sondertermins für ein Datum zurück, falls vorhanden."""
        # Sicherstellen, dass current_date ein date-Objekt ist
        if not isinstance(current_date, date):
            try:
                if hasattr(current_date, 'date'):
                    current_date = current_date.date()
                else:
                    current_date = date.fromisoformat(str(current_date))
            except (TypeError, ValueError):
                 print(f"[WARNUNG] get_event_type: Ungültiges Datumformat erhalten: {current_date}")
                 return None # Kein Event für ungültiges Datum

        # Nutze die Logik des EventManagers mit den aktuell geladenen Events
        # TODO: Analog zu Feiertagen, ggf. dynamisches Nachladen für das Jahr von current_date implementieren
        return EventManager.get_event_type(current_date, self.events)


    def get_contrast_color(self, hex_color):
        """Berechnet Schwarz oder Weiß als gut lesbare Kontrastfarbe zu einer Hex-Farbe."""
        # 1. Eingabe validieren und ggf. auflösen (benannte Farben -> Hex)
        if not isinstance(hex_color, str): return 'black' # Ungültiger Typ
        if not hex_color.startswith('#'):
            try:
                # Versuche, benannte Farbe in RGB umzuwandeln
                rgb_16bit = self.winfo_rgb(hex_color)
                r, g, b = [x // 256 for x in rgb_16bit] # Zu 8-bit konvertieren
                hex_color = f"#{r:02x}{g:02x}{b:02x}" # Weiter mit Hex
            except tk.TclError:
                print(f"[WARNUNG] get_contrast_color: Unbekannte Farbe '{hex_color}', verwende Schwarz.")
                return 'black' # Fallback für unbekannte Farbnamen

        # 2. Hex-Format prüfen (#RGB oder #RRGGBB)
        if len(hex_color) not in [4, 7]:
            print(f"[WARNUNG] get_contrast_color: Ungültiges Hex-Format '{hex_color}', verwende Schwarz.")
            return 'black' # Fallback für ungültiges Format

        # 3. Hex zu RGB konvertieren
        try:
            if len(hex_color) == 4: # #RGB -> #RRGGBB
                r, g, b = [int(c * 2, 16) for c in hex_color[1:]]
            else: # #RRGGBB
                r, g, b = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
        except ValueError:
            print(f"[WARNUNG] get_contrast_color: Fehler bei Hex-Konvertierung für '{hex_color}', verwende Schwarz.")
            return 'black' # Fallback bei Konvertierungsfehler

        # 4. Luminanz berechnen (Formel berücksichtigt menschliche Wahrnehmung)
        # luminance = (0.299 * r + 0.587 * g + 0.114 * b) # Standardformel
        # Alternative Formel (oft als besser empfunden)
        luminance = (r * 299 + g * 587 + b * 114) / 1000

        # 5. Entscheiden basierend auf Schwellwert (0-255)
        threshold = 140 # Kann angepasst werden, >128 neigt eher zu Schwarz auf hellen Farben
        contrast_color = 'black' if luminance >= threshold else 'white'
        # print(f"[DEBUG] Kontrast für {hex_color} (L: {luminance:.1f}) -> {contrast_color}")
        return contrast_color


    def load_shift_frequency(self):
        """Lädt die Häufigkeit der zugewiesenen Schichten aus der DB-Konfiguration."""
        try:
            # Annahme: load_shift_frequency gibt ein dict zurück oder None/leeres dict
            freq_data = load_shift_frequency()
            # Initialisiere defaultdict(int), damit Zugriffe auf nicht existierende User-IDs 0 ergeben
            # Übergib die geladenen Daten an den Konstruktor
            return defaultdict(int, freq_data if freq_data else {})
        except Exception as e:
            # Fallback bei Fehlern (z.B. DB nicht erreichbar, JSON-Fehler)
            print(f"[FEHLER] beim Laden der Schichthäufigkeit: {e}")
            messagebox.showerror("Ladefehler", f"Die Schichthäufigkeit konnte nicht geladen werden:\n{e}", parent=self)
            return defaultdict(int) # Leeres defaultdict als sicherer Fallback


    def save_shift_frequency(self):
        """Speichert die aktuelle Schichthäufigkeit (aus self.shift_frequency) in die DB."""
        # Nur speichern, wenn das defaultdict nicht leer ist (optional, spart DB-Zugriff)
        if not self.shift_frequency:
            print("[DEBUG] Schichthäufigkeit ist leer, Speichern übersprungen.")
            return

        try:
            # Konvertiere defaultdict zurück in ein normales dict für die Speicherung
            freq_to_save = dict(self.shift_frequency)
            print(f"[DEBUG] Speichere Schichthäufigkeit: {len(freq_to_save)} Einträge.")
            if not save_shift_frequency(freq_to_save):
                # Zeige Warnung nur, wenn save_shift_frequency explizit False zurückgibt
                messagebox.showwarning("Speicherfehler",
                                       "Die Schichthäufigkeit konnte nicht in der Konfiguration gespeichert werden (DB-Problem?).",
                                       parent=self)
            # Kein "Erfolg"-Popup beim normalen Beenden/Logout, um den User nicht zu stören
        except Exception as e:
            # Fängt unerwartete Fehler während des Speicherns ab
            print(f"[FEHLER] beim Speichern der Schichthäufigkeit: {e}")
            messagebox.showerror("Schwerer Speicherfehler",
                                 f"Speichern der Schichthäufigkeit ist fehlgeschlagen:\n{e}",
                                 parent=self)


    def reset_shift_frequency(self):
        """Setzt den Zähler für die Schichthäufigkeit in der DB und lokal zurück."""
        # Sicherheitsabfrage
        if messagebox.askyesno("Zähler zurücksetzen",
                               "Möchten Sie den Zähler für die Schichthäufigkeit wirklich für ALLE Mitarbeiter auf Null zurücksetzen?\nDiese Aktion kann nicht rückgängig gemacht werden!",
                               icon='warning', parent=self):
            try:
                # Rufe die DB-Funktion zum Löschen/Zurücksetzen auf
                if reset_shift_frequency():
                    # Wenn erfolgreich, leere auch das lokale defaultdict
                    self.shift_frequency.clear()
                    print("[DEBUG] Schichthäufigkeit erfolgreich zurückgesetzt.")
                    messagebox.showinfo("Erfolg", "Der Zähler für die Schichthäufigkeit wurde zurückgesetzt.", parent=self)
                    # Aktualisiere den Schichtplan, falls er geladen ist, um die Anzeige zu aktualisieren
                    self.refresh_specific_tab("Schichtplan")
                else:
                    # DB-Funktion hat False zurückgegeben
                    messagebox.showerror("Fehler", "Fehler beim Zurücksetzen des Zählers in der Datenbank.", parent=self)
            except Exception as e:
                # Fängt unerwartete Fehler während des DB-Zugriffs ab
                print(f"[FEHLER] beim Zurücksetzen der Schichthäufigkeit: {e}")
                messagebox.showerror("Schwerer Fehler", f"Zurücksetzen des Zählers fehlgeschlagen:\n{e}", parent=self)


    def get_allowed_roles(self):
        """Gibt eine Liste der Rollen zurück, die der aktuelle Admin verwalten (erstellen/bearbeiten) darf."""
        current_admin_role = self.user_data.get('role', 'Benutzer') # Eigene Rolle holen, Fallback 'Benutzer'
        admin_level = ROLE_HIERARCHY.get(current_admin_role, 0) # Numerisches Level der eigenen Rolle

        # Erlaubte Rollen sind alle, die ein STRIKT NIEDRIGERES Level haben
        allowed_roles = [role for role, level in ROLE_HIERARCHY.items() if level < admin_level]

        # Admins dürfen auch andere Admins verwalten (gleiches Level), ABER NICHT SuperAdmins
        if current_admin_role == "Admin":
             if "Admin" not in allowed_roles: # Füge hinzu, falls nicht schon durch niedrigere Level drin
                 allowed_roles.append("Admin")
             # Entferne Rollen, die höher oder gleich SuperAdmin sind
             allowed_roles = [r for r in allowed_roles if ROLE_HIERARCHY.get(r, 99) < ROLE_HIERARCHY.get("SuperAdmin", 99)]

        # SuperAdmins dürfen alle Rollen verwalten
        elif current_admin_role == "SuperAdmin":
            allowed_roles = list(ROLE_HIERARCHY.keys()) # Alle definierten Rollen

        # Die Rolle "Benutzer" sollte i.d.R. nicht manuell vergeben werden (nur bei Registrierung)
        # Entferne sie aus der Liste der auswählbaren Rollen im Admin-Panel
        if "Benutzer" in allowed_roles:
             allowed_roles.remove("Benutzer")

        print(f"[DEBUG] Erlaubte Rollen für {current_admin_role} (Level {admin_level}): {allowed_roles}")
        return allowed_roles

    # --------------------------------------------------------------------------------------


    # --- HIER IST DIE NOCHMALS ANGEPASSTE FUNKTION ---
    def open_user_order_window(self):
        """
        Öffnet das Fenster zur Sortierung der Benutzer.
        Versucht, das Datum und den Callback des aktuell ausgewählten,
        vollständig geladenen Schichtplan-Tabs zu verwenden.
        Nutzt Fallback (heutiges Datum, globaler Refresh), wenn dies nicht gelingt.
        """
        for_date = datetime.now() # Fallback-Datum
        callback = self.refresh_all_tabs # Fallback-Callback
        is_specific_month = False # Flag, ob wir einen spezifischen Monat haben
        show_info_message = True # Flag, ob die Info-Nachricht angezeigt werden soll

        try:
            selected_tab_id = self.notebook.select()
            if not selected_tab_id:
                print("[DEBUG] open_user_order_window: Kein Tab ausgewählt.")
                raise tk.TclError("Kein Tab ausgewählt.") # Geht zum Fallback

            # Das Widget holen, das aktuell im Notebook an dieser Stelle ist
            current_widget = self.notebook.nametowidget(selected_tab_id)

            # --- NEUE, DIREKTERE PRÜFUNG ---
            # Prüfen, ob das aktuelle Widget direkt eine Instanz von ShiftPlanTab ist
            # UND die benötigten Attribute hat. Das funktioniert auch nach dem Lazy Loading.
            if isinstance(current_widget, ShiftPlanTab):
                # Versuch, auf die Attribute zuzugreifen. Wenn sie nicht da sind -> AttributeError
                current_year = current_widget.current_year
                current_month = current_widget.current_month
                # Prüfe, ob die Werte gültig sind (nicht None etc.)
                if current_year is not None and current_month is not None:
                    for_date = datetime(current_year, current_month, 1) # Ersten des Monats nehmen
                    # Spezifischen Callback für DIESEN Tab verwenden
                    # Prüfe, ob refresh_plan existiert, sonst Fallback auf refresh_data
                    if hasattr(current_widget, 'refresh_plan'):
                         callback = current_widget.refresh_plan
                    elif hasattr(current_widget, 'refresh_data'):
                         callback = current_widget.refresh_data
                    # Wenn keine Refresh-Methode -> Behalte globalen Callback

                    is_specific_month = True
                    show_info_message = False # Keine Info-Nachricht nötig
                    print(f"[DEBUG] Öffne UserOrderWindow für spezifischen Monat: {for_date.strftime('%Y-%m')}")
                else:
                    # Hat den Typ, aber Attribute sind ungültig -> Fallback
                    print("[DEBUG] ShiftPlanTab gefunden, aber current_year/month ungültig. Verwende Fallback.")
                    # Keine Exception werfen, einfach zum Fallback übergehen (show_info_message bleibt True)

            else:
                # Das aktuelle Widget ist kein ShiftPlanTab (oder noch der Platzhalter)
                print(f"[DEBUG] Aktuelles Widget ist kein geladener ShiftPlanTab (Typ: {type(current_widget)}). Verwende Fallback.")
                # show_info_message bleibt True

        except (tk.TclError, AttributeError, ValueError) as e:
            # Fängt Fehler beim Zugriff auf Notebook/Widget ODER fehlende/ungültige Attribute ODER ValueError bei datetime() ab
            print(f"[WARNUNG] Fehler beim Ermitteln des Tabs/Datums in open_user_order_window: {e}. Verwende Fallback.")
            # show_info_message bleibt True (Standard)

        except Exception as e:
            # Andere unerwartete Fehler
            print(f"Unerwarteter Fehler beim Öffnen des UserOrderWindow: {e}")
            messagebox.showerror("Fehler", f"Konnte das Sortierfenster nicht korrekt vorbereiten:\n{e}", parent=self)
            # Im Zweifel immer den Fallback verwenden, show_info_message bleibt True

        # Zeige die Info-Nachricht nur an, wenn wir den Fallback verwenden
        if show_info_message:
             messagebox.showinfo("Info",
                                "Sie bearbeiten die Standard-Sortierung (basierend auf heute).\n\n"
                                "Um die Sortierung für einen bestimmten Monat zu sehen (inkl. zukünftiger/archivierter Mitarbeiter), "
                                "wählen Sie bitte zuerst den entsprechenden Schichtplan-Tab aus und stellen Sie sicher, dass er vollständig geladen ist.",
                                parent=self)

        # Öffne das Fenster mit dem ermittelten Datum und Callback
        print(f"[DEBUG] Rufe UserOrderWindow auf mit for_date={for_date.strftime('%Y-%m-%d')} und callback={getattr(callback, '__name__', 'lambda/unknown')}")
        UserOrderWindow(self, callback=callback, for_date=for_date)
    # --- ENDE DER ANGEPASSTEN FUNKTION ---

    # --- open_shift_order_window, open_staffing_rules_window, etc. bleiben unverändert ---
    def open_shift_order_window(self):
        """ Öffnet das Fenster zur Sortierung der Schichtarten. """
        # Übergibt refresh_all_tabs als Callback, da sich die Schichtreihenfolge
        # potenziell auf alle Schichtpläne auswirken kann.
        ShiftOrderWindow(self, callback=self.refresh_all_tabs)

    def open_staffing_rules_window(self):
        """Öffnet das Einstellungsfenster für die Mindestbesetzung."""
        def save_and_refresh(new_rules):
            """Callback-Funktion zum Speichern der Regeln und Aktualisieren der GUI."""
            print("[DEBUG] Speichere Besetzungsregeln...")
            try:
                # Ruft die Speicherfunktion aus db_core auf
                if save_config_json(MIN_STAFFING_RULES_CONFIG_KEY, new_rules):
                    self.staffing_rules = new_rules # Aktualisiere die Regeln im Hauptfenster
                    messagebox.showinfo("Gespeichert", "Die Besetzungsregeln wurden erfolgreich aktualisiert.",
                                        parent=self) # Gib dem Benutzer Feedback
                    # Aktualisiere (nur) den Schichtplan-Tab, da nur dieser die Regeln direkt anzeigt
                    self.refresh_specific_tab("Schichtplan")
                else:
                    # Speichern in DB fehlgeschlagen
                    messagebox.showerror("Fehler", "Die Besetzungsregeln konnten nicht in der Konfiguration gespeichert werden.",
                                         parent=self)
            except Exception as e:
                # Unerwarteter Fehler beim Speichern
                print(f"[FEHLER] beim Speichern der Besetzungsregeln: {e}")
                messagebox.showerror("Schwerer Speicherfehler", f"Speichern der Besetzungsregeln fehlgeschlagen:\n{e}", parent=self)

        # Erstelle und zeige das Einstellungsfenster
        # Übergib die aktuellen Regeln (self.staffing_rules) und die Callback-Funktion
        staffing_window = MinStaffingWindow(self, current_rules=self.staffing_rules, callback=save_and_refresh)
        staffing_window.focus_force() # Setze den Fokus auf das neue Fenster

    def refresh_shift_plan(self):
        """Aktualisiert nur den Schichtplan-Tab (falls geladen)."""
        self.refresh_specific_tab("Schichtplan")


    def refresh_specific_tab(self, tab_name):
        """Aktualisiert einen spezifischen Tab, falls er geladen ist und eine Refresh-Methode hat."""
        print(f"[DEBUG] refresh_specific_tab angefordert für: '{tab_name}'")
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            # Prüfen, ob das Frame-Objekt existiert, ein gültiges Widget ist und zum Notebook gehört
            if frame and frame.winfo_exists():
                try:
                    parent_is_notebook = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if parent_is_notebook:
                        # Versuche, eine passende Refresh-Methode aufzurufen
                        refreshed = False
                        # Priorisierte Methode: 'refresh_plan' (oft spezifischer)
                        if hasattr(frame, 'refresh_plan'):
                            print(f"[DEBUG] -> rufe refresh_plan() für {tab_name} auf")
                            frame.refresh_plan()
                            refreshed = True
                        # Fallback 1: 'refresh_data'
                        elif hasattr(frame, 'refresh_data'):
                            print(f"[DEBUG] -> rufe refresh_data() für {tab_name} auf")
                            frame.refresh_data()
                            refreshed = True
                        # Fallback 2: 'load_data' (könnte weniger effizient sein)
                        elif hasattr(frame, 'load_data'):
                             print(f"[DEBUG] -> rufe load_data() für {tab_name} auf")
                             frame.load_data()
                             refreshed = True

                        if not refreshed:
                             print(f"[WARNUNG] Tab '{tab_name}' ist geladen, hat aber keine bekannte Refresh-Methode (refresh_plan, refresh_data, load_data).")

                except (tk.TclError, KeyError) as e:
                     # Kann passieren, wenn Widget-Hierarchie unerwartet oder Widget zerstört
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
                except Exception as e:
                    # Unerwarteter Fehler in der Refresh-Methode des Tabs selbst
                    print(f"[FEHLER] Unerwarteter Fehler während des Refresh von Tab '{tab_name}': {e}")
            else:
                 # Frame nicht (mehr) gültig -> Bereinigen
                 print(f"[WARNUNG] Tab-Widget für '{tab_name}' nicht gefunden oder existiert nicht mehr. Entferne aus Verwaltung.")
                 if tab_name in self.loaded_tabs: self.loaded_tabs.remove(tab_name)
                 if tab_name in self.tab_frames: del self.tab_frames[tab_name]
        else:
            # Tab war noch gar nicht geladen
            print(f"[DEBUG] Tab '{tab_name}' ist nicht geladen, kein Refresh nötig.")

    def open_holiday_settings_window(self):
        # Ermittle das Jahr aus dem aktuell angezeigten Datum oder nimm das aktuelle Jahr
        year_to_edit = self.current_display_date.year if self.current_display_date else date.today().year
        # Übergibt refresh_all_tabs als Callback, da sich Feiertage auf viele Ansichten auswirken
        HolidaySettingsWindow(self, year=year_to_edit, callback=self.refresh_all_tabs)

    def open_event_settings_window(self):
         # Ermittle das Jahr analog zu Feiertagen
         year_to_edit = self.current_display_date.year if self.current_display_date else date.today().year
         # Übergibt refresh_all_tabs als Callback
         EventSettingsWindow(self, year=year_to_edit, callback=self.refresh_all_tabs)

    def open_color_settings_window(self):
         # Übergibt refresh_all_tabs, da Farbänderungen (z.B. für Schichtarten)
         # potenziell alle Pläne beeinflussen
        ColorSettingsWindow(self, callback=self.refresh_all_tabs)

    def open_request_settings_window(self):
         # Öffnet Einstellungsdialog für Anfragetypen etc.
         # Änderungen hier wirken sich i.d.R. erst auf zukünftige Anfragen aus,
         # daher ist ein sofortiger globaler Refresh nicht zwingend nötig.
         RequestSettingsWindow(self)

    def open_planning_assistant_settings(self):
         # Öffnet Einstellungsdialog für den Planungsgenerator
         PlanningAssistantSettingsWindow(self)
    # --------------------------------------------------------------------------------------