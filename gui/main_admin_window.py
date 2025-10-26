# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta, datetime
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
        self.user_data = user_data

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
            # --- Korrektur: ShiftTypesTab hier definieren ---
            "Schichtarten": ShiftTypesTab,
            # -------------------------------------------
            "Wunschanfragen": RequestsTab,
            "Urlaubsanträge": VacationRequestsTab,
            "Bug-Reports": BugReportsTab,
            "Logs": LogTab,
            "Protokoll": ProtokollTab,
            "Dummy": None
        }

        self.tab_frames = {}
        self.loaded_tabs = set()

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

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """Lädt einen Tab im Hintergrund-Thread."""
        try:
            print(f"[Thread-Admin] Lade Tab: {tab_name}...")
            real_tab = None
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            # --- KORREKTUR: ShiftTypesTab braucht die AdminWindow (self), nicht die App ---
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, self)  # self ist die MainAdminWindow
            # -------------------------------------------------------------------------
            else:
                try:
                    # Die meisten Admin-Tabs erwarten (master, self = MainAdminWindow)
                    real_tab = TabClass(self.notebook, self)
                except Exception as e1:
                    print(
                        f"[Thread-Admin] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:  # Fallback für Tabs, die nur (master) erwarten
                        real_tab = TabClass(self.notebook)
                    except Exception as e2:
                        print(f"[Thread-Admin] FEHLER: {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise

            self.tab_load_queue.put((tab_name, real_tab, tab_index))
            print(f"[Thread-Admin] Tab '{tab_name}' fertig geladen.")
        except Exception as e:
            print(f"[Thread-Admin] FEHLER beim Laden von Tab '{tab_name}': {e}")
            self.tab_load_queue.put((tab_name, e, tab_index))  # Fehler in die Queue legen

    def _check_tab_load_queue(self):
        """Prüft die Queue und fügt geladene Tabs im GUI-Thread ein."""
        tab_name_processed = None  # Merker, welcher Tab bearbeitet wird
        try:
            result = self.tab_load_queue.get_nowait()
            tab_name, real_tab_or_exception, tab_index = result
            tab_name_processed = tab_name  # Merken für finally Block

            print(f"[GUI-Checker-Admin] Empfange Ergebnis für: {tab_name}")

            placeholder_frame = self.tab_frames.get(tab_name)
            if not placeholder_frame or not placeholder_frame.winfo_exists():
                print(f"[GUI-Checker-Admin] FEHLER: Platzhalter für {tab_name} existiert nicht mehr.")
                # loading_tabs wird im finally bereinigt
                return  # Mit nächstem Check fortfahren

            # Alte Lade-Labels entfernen
            for widget in placeholder_frame.winfo_children():
                if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                    widget.destroy()

            if isinstance(real_tab_or_exception, Exception):
                # Fehler beim Laden anzeigen
                e = real_tab_or_exception
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
                print(f"[GUI-Checker-Admin] Fehler beim Laden von Tab '{tab_name}' angezeigt.")
            else:
                # Erfolgreich geladen, Tab einsetzen
                real_tab = real_tab_or_exception
                try:
                    # Event-Binding entfernen, um unnötige Events während des Austauschs zu vermeiden
                    self.notebook.unbind("<<NotebookTabChanged>>")
                    # Optionen vom Platzhalter holen, BEVOR er entfernt wird
                    tab_options = self.notebook.tab(placeholder_frame)
                    # Platzhalter entfernen
                    self.notebook.forget(placeholder_frame)
                    # Neuen Tab an der richtigen Position einfügen
                    self.notebook.insert(tab_index, real_tab, **tab_options)
                    # Neuen Tab auswählen (wichtig!)
                    self.notebook.select(real_tab)
                    # Status aktualisieren
                    self.loaded_tabs.add(tab_name)
                    self.tab_frames[tab_name] = real_tab  # Referenz auf echten Tab
                    print(f"[GUI-Checker-Admin] Tab '{tab_name}' erfolgreich eingesetzt.")
                except tk.TclError as e:
                    # Fehler beim Einsetzen (z.B. Widget bereits zerstört)
                    print(f"[GUI-Checker-Admin] TclError beim Einsetzen von {tab_name}: {e}")
                    # Hier könnte man versuchen, den Platzhalter wiederherzustellen oder eine Fehlermeldung anzuzeigen
                finally:
                    # Event-Binding immer wieder hinzufügen, auch im Fehlerfall
                    self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        except Empty:
            # Queue ist leer, alles gut
            pass

        except Exception as e:
            # Unerwarteter Fehler im Checker selbst
            print(f"[GUI-Checker-Admin] Unerwarteter Fehler in _check_tab_load_queue: {e}")
            # Optional: Hier eine Fehlermeldung im UI anzeigen

        finally:
            # Entferne den Tab-Namen aus loading_tabs, egal ob Erfolg oder Fehler
            if tab_name_processed and tab_name_processed in self.loading_tabs:
                self.loading_tabs.remove(tab_name_processed)

            # Den Checker am Laufen halten? Nur wenn noch Arbeit da ist.
            if not self.tab_load_queue.empty() or self.loading_tabs:
                self.after(100, self._check_tab_load_queue)  # Weiter prüfen
            else:
                self.tab_load_checker_running = False  # Keine Arbeit mehr, pausieren
                print("[GUI-Checker-Admin] Keine Tabs mehr in Queue oder am Laden. Checker pausiert.")

    def _load_tab_directly(self, tab_name, tab_index):
        # (Wird nicht mehr direkt verwendet, bleibt als Fallback)
        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs: return
        if tab_name not in self.tab_definitions or not self.tab_definitions[tab_name]: return

        self.loading_tabs.add(tab_name)
        print(f"[GUI - direct load] Lade Tab (SYNCHRON): {tab_name}")
        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames[tab_name]

        # Zeige Lade-Label an
        for widget in placeholder_frame.winfo_children(): widget.destroy()
        loading_label = ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16))
        loading_label.pack(expand=True, anchor="center")
        self.update_idletasks()  # Wichtig, damit Label sichtbar wird

        real_tab = None
        try:
            # Initialisierung je nach Tab-Typ
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            # --- KORREKTUR: ShiftTypesTab braucht die AdminWindow (self), nicht die App ---
            elif TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, self)  # self ist die MainAdminWindow
            # -------------------------------------------------------------------------
            else:
                try:  # Versuche (master, self = MainAdminWindow)
                    real_tab = TabClass(self.notebook, self)
                except TypeError:  # Fallback auf (master)
                    print(
                        f"[GUI - direct load] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen. Versuche (master)...")
                    real_tab = TabClass(self.notebook)

            # Tab einsetzen (im GUI-Thread)
            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)  # Optionen holen
                self.notebook.forget(placeholder_frame)  # Platzhalter entfernen
                self.notebook.insert(tab_index, real_tab, **tab_options)  # Echten Tab einfügen
                self.notebook.select(real_tab)  # Echten Tab auswählen
                self.loaded_tabs.add(tab_name)
                self.tab_frames[tab_name] = real_tab  # Referenz aktualisieren
                print(f"[GUI - direct load] Tab '{tab_name}' erfolgreich eingesetzt.")
            else:
                # Sollte nicht passieren, aber sicher ist sicher
                print(f"[GUI - direct load] FEHLER: Platzhalter für {tab_name} existierte nicht mehr.")

        except Exception as e:
            print(f"[GUI - direct load] FEHLER beim Laden/Einsetzen von Tab '{tab_name}': {e}")
            if placeholder_frame.winfo_exists():  # Fehler im Platzhalter anzeigen
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
        finally:
            if tab_name in self.loading_tabs: self.loading_tabs.remove(tab_name)

    def on_tab_changed(self, event):
        """Startet den Lade-Thread für den ausgewählten Tab."""
        try:
            tab_id = self.notebook.select()
            if not tab_id: return
            tab_index = self.notebook.index(tab_id)
            tab_info = self.notebook.tab(tab_index)
            if not tab_info: return
            tab_name_with_count = tab_info.get("text", "")
            tab_name = tab_name_with_count.split(" (")[0]
        except (tk.TclError, IndexError):
            print("[GUI-Admin] Fehler beim Ermitteln des Tabs in on_tab_changed.")
            return

        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
            return

        if tab_name not in self.tab_definitions or self.tab_definitions[tab_name] is None:
            return

        print(f"[GUI-Admin] on_tab_changed: Starte Ladevorgang für {tab_name}")
        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames.get(tab_name)

        if not placeholder_frame or not placeholder_frame.winfo_exists():
            print(f"[GUI-Admin] FEHLER: Platzhalter-Frame für '{tab_name}' nicht gefunden oder bereits zerstört.")
            return

        for widget in placeholder_frame.winfo_children(): widget.destroy()
        ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16)).pack(expand=True,
                                                                                             anchor="center")
        self.update_idletasks()

        self.loading_tabs.add(tab_name)

        threading.Thread(
            target=self._load_tab_threaded,
            args=(tab_name, TabClass, tab_index),
            daemon=True
        ).start()

        if not self.tab_load_checker_running:
            print("[GUI-Checker-Admin] Starte Checker-Loop.")
            self.tab_load_checker_running = True
            self.after(50, self._check_tab_load_queue)

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
            self.tab_frames[tab_name] = placeholder_frame
            if TabClass is None:
                try:
                    self.notebook.tab(i, state='disabled')
                    print(f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' (Index {i}) deaktiviert.")
                except tk.TclError as e:
                    print(f"[FEHLER] setup_lazy_tabs: Konnte Tab '{tab_name}' nicht deaktivieren: {e}")
            i += 1
        self.update_tab_titles()

    def update_single_tab_text(self, tab_name, new_text):
        frame = self.tab_frames.get(tab_name)
        if frame:
            try:
                if frame.winfo_exists() and self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                    self.notebook.tab(frame, text=new_text)
            except (tk.TclError, KeyError):
                print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name} (Widget ungültig/zerstört)")

    def update_tab_titles(self):
        try:
            pending_wunsch_count = len(get_pending_wunschfrei_requests())
            tab_text_wunsch = "Wunschanfragen"
            if pending_wunsch_count > 0: tab_text_wunsch += f" ({pending_wunsch_count})"
            self.update_single_tab_text("Wunschanfragen", tab_text_wunsch)

            pending_urlaub_count = get_pending_vacation_requests_count()
            tab_text_urlaub = "Urlaubsanträge"
            if pending_urlaub_count > 0: tab_text_urlaub += f" ({pending_urlaub_count})"
            self.update_single_tab_text("Urlaubsanträge", tab_text_urlaub)

            open_bug_count = get_open_bug_reports_count()
            tab_text_bugs = "Bug-Reports"
            if open_bug_count > 0: tab_text_bugs += f" ({open_bug_count})"
            self.update_single_tab_text("Bug-Reports", tab_text_bugs)
        except Exception as e:
            print(f"[FEHLER] Konnte Tab-Titel nicht aktualisieren: {e}")
            self.update_single_tab_text("Wunschanfragen", "Wunschanfragen (?)")
            self.update_single_tab_text("Urlaubsanträge", "Urlaubsanträge (?)")
            self.update_single_tab_text("Bug-Reports", "Bug-Reports (?)")

    def switch_to_tab(self, tab_name):
        frame = self.tab_frames.get(tab_name)
        if frame and frame.winfo_exists():
            try:
                if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                    self.notebook.select(frame)
                else:
                    print(f"[DEBUG] switch_to_tab: Frame für '{tab_name}' ist kein aktueller Tab mehr.")
            except (tk.TclError, KeyError):
                print(
                    f"[DEBUG] switch_to_tab: Fehler beim Auswählen von '{tab_name}' (Widget ungültig/Elternteil nicht Notebook).")
        else:
            print(f"[DEBUG] switch_to_tab: Tab/Frame '{tab_name}' nicht gefunden oder zerstört.")

    def _load_dynamic_tab(self, tab_name, TabClass, *args):
        # (Bleibt synchron)
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                        self.notebook.select(frame)
                        return
                except (tk.TclError, KeyError):
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
            self.tab_frames[tab_name] = placeholder_frame
        finally:
            self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.update_idletasks()

        real_tab = None
        try:
            # --- KORREKTUR: ShiftTypesTab braucht die AdminWindow (self), nicht die App ---
            if TabClass.__name__ == "ShiftTypesTab":
                real_tab = TabClass(self.notebook, self)  # self ist die MainAdminWindow
            # -------------------------------------------------------------------------
            elif TabClass.__name__ == "UserTabSettingsTab":
                real_tab = TabClass(self.notebook, *args)
            elif TabClass.__name__ in ["RequestLockTab", "PasswordResetRequestsWindow"]:
                real_tab = TabClass(self.notebook, *args)
            else:
                print(f"[WARNUNG] _load_dynamic_tab: Unbekannter Typ {TabClass.__name__}, versuche mit (master).")
                real_tab = TabClass(self.notebook)

            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)
                if real_tab and tab_options and tab_index != -1:
                    try:
                        self.notebook.unbind("<<NotebookTabChanged>>")
                        self.notebook.forget(placeholder_frame)
                        self.notebook.insert(tab_index, real_tab, **tab_options)
                        self.notebook.select(real_tab)
                    finally:
                        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
                    self.loaded_tabs.add(tab_name)
                    self.tab_frames[tab_name] = real_tab
                    print(f"[GUI] Dynamischer Tab '{tab_name}' erfolgreich eingesetzt.")
                else:
                    raise Exception("Konnte dyn. Tab-Objekt, Optionen oder Index nicht ermitteln.")
            else:
                raise tk.TclError(f"Platzhalter für dyn. Tab {tab_name} existierte nicht mehr.")

        except Exception as e:
            print(f"[GUI] FEHLER beim Laden/Einfügen von dynamischem Tab '{tab_name}': {e}")
            if placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
            else:
                print(
                    f"[GUI] FEHLER: Platzhalter für {tab_name} existierte nicht mehr bei Fehlerbehandlung (dyn. Tab).")
                messagebox.showerror("Fehler beim Laden", f"Konnte Tab '{tab_name}' nicht laden:\n{e}", parent=self)
        finally:
            if tab_name in self.loading_tabs:
                self.loading_tabs.remove(tab_name)

    def open_request_lock_window(self):
        self._load_dynamic_tab("Antragssperre", RequestLockTab, self)

    def open_user_tab_settings(self):
        all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen", "Chat"]
        self._load_dynamic_tab("Benutzer-Reiter", UserTabSettingsTab, all_user_tab_names)

    def open_password_resets_window(self):
        self._load_dynamic_tab("Passwort-Resets", PasswordResetRequestsWindow, self)

    def open_shift_types_window(self):
        """Wechselt zum Schichtarten-Tab."""
        print("[DEBUG] Wechsle zum Schichtarten-Tab...")
        # --- Korrektur: Zum Tab wechseln statt Dialog öffnen ---
        self.switch_to_tab("Schichtarten")
        # ---------------------------------------------------

    def on_close(self):
        print("[DEBUG] MainAdminWindow.on_close aufgerufen.")
        self.save_shift_frequency()
        try:
            log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        except Exception as e:
            print(f"[FEHLER] Konnte Logout nicht loggen: {e}")
        self.app.on_app_close()

    def logout(self):
        print("[DEBUG] MainAdminWindow.logout aufgerufen.")
        self.save_shift_frequency()
        try:
            log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        except Exception as e:
            print(f"[FEHLER] Konnte Logout nicht loggen: {e}")
        self.app.on_logout(self)

    def setup_header(self):
        self.notification_frame = ttk.Frame(self.header_frame)
        self.notification_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(self.notification_frame, text="").pack()

        settings_menubutton = ttk.Menubutton(self.header_frame, text="⚙️ Einstellungen", style='Settings.TMenubutton')
        settings_menubutton.pack(side="right", padx=5)
        settings_menu = tk.Menu(settings_menubutton, tearoff=0)
        settings_menubutton["menu"] = settings_menu

        settings_menu.add_command(label="Schichtarten", command=self.open_shift_types_window)
        settings_menu.add_separator()
        settings_menu.add_command(label="Mitarbeiter-Sortierung", command=self.open_user_order_window)
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
        db_menu = tk.Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="Datenbank Wartung", menu=db_menu)
        db_menu.add_command(label="⚠️ FIX: ALLE ALTEN USER FREISCHALTEN", command=self.apply_all_users_approval_fix)
        db_menu.add_separator()
        db_menu.add_command(label="Update: Freischaltung Spalte ('is_approved')", command=self.apply_is_approved_fix)
        db_menu.add_command(label="Update: Archivierung Spalte ('is_archived')", command=self.apply_is_archived_fix)
        db_menu.add_command(label="Update: Archivierungsdatum Spalte ('archived_date')",
                            command=self.apply_archived_date_fix)
        db_menu.add_separator()
        db_menu.add_command(label="Update für Chat ausführen", command=self.apply_database_fix)

    def _run_db_update_with_confirmation(self, message, db_function):
        if messagebox.askyesno("Bestätigung", message, parent=self):
            try:
                success, result_message = db_function()
                if success:
                    messagebox.showinfo("Erfolg", result_message, parent=self)
                else:
                    messagebox.showerror("Fehler", result_message, parent=self)
            except Exception as e:
                print(f"FEHLER bei DB Update ({db_function.__name__}): {e}")
                messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=self)

    def apply_archived_date_fix(self):
        msg = "Dies fügt die Spalte 'archived_date' zur Benutzer-Tabelle hinzu... Fortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_add_archived_date)

    def apply_is_archived_fix(self):
        msg = "Dies fügt die Spalte 'is_archived' zur Benutzer-Tabelle hinzu... Fortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_add_is_archived)

    def apply_all_users_approval_fix(self):
        if messagebox.askyesno("ACHTUNG: FIX BESTÄTIGEN",
                               "Sind Sie sicher, dass Sie ALLE bestehenden Benutzer freischalten möchten...?",
                               icon='warning', parent=self):
            self._run_db_update_with_confirmation("Wirklich ALLE User freischalten?", run_db_fix_approve_all_users)

    def apply_is_approved_fix(self):
        msg = "Dies führt ein Update durch, um die fehlende 'is_approved' Spalte hinzuzufügen... Fortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_is_approved)

    def apply_database_fix(self):
        msg = "Dies führt ein Update der Datenbank für die Chat-Funktion durch... Fortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_v1)

    def setup_footer(self):
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def check_chat_notifications(self):
        try:
            for widget in self.chat_notification_frame.winfo_children():
                widget.destroy()

            senders = get_senders_with_unread_messages(self.user_data['id'])
            if senders:
                latest_sender_id = senders[0]['sender_id']
                total_unread = sum(s['unread_count'] for s in senders)
                action = lambda event=None, uid=latest_sender_id: self.go_to_chat(uid)

                self.chat_notification_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)
                self.chat_notification_frame.bind("<Button-1>", action)

                label_text = f"Sie haben {total_unread} neue Nachricht(en)! Hier klicken zum Anzeigen."
                notification_label = tk.Label(self.chat_notification_frame, text=label_text, bg='tomato', fg='white',
                                              font=('Segoe UI', 12, 'bold'), cursor="hand2")
                notification_label.pack(side='left', padx=15, pady=5);
                notification_label.bind("<Button-1>", action)

                show_button = ttk.Button(self.chat_notification_frame, text="Anzeigen", command=action)
                show_button.pack(side='right', padx=15)
            else:
                self.chat_notification_frame.pack_forget()

        except Exception as e:
            print(f"[FEHLER] bei check_chat_notifications: {e}")
            self.chat_notification_frame.pack_forget()

        finally:
            self.after(10000, self.check_chat_notifications)

    def go_to_chat(self, user_id):
        print(f"[DEBUG] go_to_chat aufgerufen für User ID: {user_id}")
        self.switch_to_tab("Chat")

        def _select_user_when_ready():
            # --- KORREKTUR (Race Condition): Prüfe auf 'loaded_tabs' statt 'loading_tabs' ---
            if "Chat" in self.loaded_tabs:
                chat_tab = self.tab_frames.get("Chat")
                if chat_tab and chat_tab.winfo_exists() and hasattr(chat_tab, "select_user"):
                    try:
                        print(f"[DEBUG] Chat-Tab ist geladen, rufe select_user({user_id}) auf.")
                        chat_tab.select_user(user_id)
                    except Exception as e:
                        print(f"[FEHLER] beim Aufrufen von select_user für {user_id}: {e}")
                # ... (Restliche Fehlerbehandlungen bleiben gleich) ...
                elif chat_tab and not chat_tab.winfo_exists():
                    print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab existiert nicht mehr.")
                elif not chat_tab:
                    print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab nicht im Frame-Dict.")
                else:
                    print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab hat keine 'select_user' Methode.")

            # --- KORREKTUR: Prüfe, ob der Tab *noch lädt* oder *noch nicht geladen* ist ---
            elif "Chat" in self.loading_tabs or "Chat" not in self.loaded_tabs:
                print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab noch nicht geladen, warte 200ms...")
                self.after(200, _select_user_when_ready)
            # --- ENDE KORREKTUR ---
            else:
                print(
                    f"[DEBUG] go_to_chat/_select_user_when_ready: Unbekannter Status für Chat-Tab (UserID: {user_id}). Breche ab.")

        self.after(50, _select_user_when_ready)

    def check_for_updates(self):
        print("[DEBUG] check_for_updates gestartet.")
        try:
            self.update_tab_titles()
            self.update_header_notifications()

            if "Mitarbeiter" in self.loaded_tabs:
                user_tab = self.tab_frames.get("Mitarbeiter")
                if user_tab and user_tab.winfo_exists() and hasattr(user_tab, 'check_pending_approvals'):
                    print("[DEBUG] check_for_updates: Prüfe ausstehende Freischaltungen.")
                    user_tab.check_pending_approvals()

        except Exception as e:
            print(f"[FEHLER] in check_for_updates: {e}")

        finally:
            self.after(60000, self.check_for_updates)

    def open_bug_report_dialog(self):
        BugReportDialog(self, self.user_data['id'], self.check_for_updates)

    def refresh_antragssperre_views(self):
        print("[DEBUG] refresh_antragssperre_views aufgerufen.")
        if "Schichtplan" in self.loaded_tabs:
            plan_tab = self.tab_frames.get("Schichtplan")
            if plan_tab and plan_tab.winfo_exists() and hasattr(plan_tab, 'update_lock_status'):
                print("[DEBUG] -> Aktualisiere Sperrstatus im Schichtplan-Tab.")
                plan_tab.update_lock_status()

        if "Antragssperre" in self.loaded_tabs:
            lock_tab = self.tab_frames.get("Antragssperre")
            if lock_tab and lock_tab.winfo_exists() and hasattr(lock_tab, 'load_locks_for_year'):
                print("[DEBUG] -> Lade Sperren neu im Antragssperre-Tab.")
                lock_tab.load_locks_for_year()

    def update_header_notifications(self):
        for widget in self.notification_frame.winfo_children():
            widget.destroy()

        notifications = []
        try:
            pending_password_resets = get_pending_password_resets_count()
            if pending_password_resets > 0:
                notifications.append(
                    {"text": f"{pending_password_resets} Passwort-Reset(s)", "bg": "mediumpurple", "fg": "white",
                     "action": self.open_password_resets_window})

            pending_wunsch_count = len(get_pending_wunschfrei_requests())
            if pending_wunsch_count > 0:
                notifications.append(
                    {"text": f"{pending_wunsch_count} Offene Wunschanfrage(n)", "bg": "orange", "fg": "black",
                     "tab": "Wunschanfragen"})

            pending_urlaub_count = get_pending_vacation_requests_count()
            if pending_urlaub_count > 0:
                notifications.append(
                    {"text": f"{pending_urlaub_count} Offene Urlaubsanträge", "bg": "lightblue", "fg": "black",
                     "tab": "Urlaubsanträge"})

            user_feedback_count = get_reports_with_user_feedback_count()
            if user_feedback_count > 0:
                notifications.append(
                    {"text": f"{user_feedback_count} User-Feedback(s)", "bg": "springgreen", "fg": "black",
                     "tab": "Bug-Reports"})

            open_bug_count = get_open_bug_reports_count()
            if open_bug_count > 0:
                notifications.append({"text": f"{open_bug_count} Offene Bug-Report(s)", "bg": "tomato", "fg": "white",
                                      "tab": "Bug-Reports"})

        except Exception as e:
            print(f"[FEHLER] beim Abrufen der Benachrichtigungsdaten: {e}")
            ttk.Label(self.notification_frame, text="Fehler beim Laden der Benachrichtigungen", foreground="red").pack()
            return

        if not notifications:
            ttk.Label(self.notification_frame, text="Keine neuen Benachrichtigungen",
                      font=('Segoe UI', 10, 'italic')).pack(padx=5)
        else:
            for i, notif in enumerate(notifications):
                style_name = f'Notif{i}.TButton'
                self.style.configure(style_name, background=notif["bg"], foreground=notif["fg"],
                                     font=('Segoe UI', 10, 'bold'), padding=(10, 5))
                self.style.map(style_name, background=[('active', self._calculate_hover_color(notif["bg"]))],
                               relief=[('pressed', 'sunken')])

                command = None
                if "action" in notif:
                    command = notif["action"]
                else:
                    tab_name = notif.get("tab")
                    if tab_name: command = lambda tab=tab_name: self.switch_to_tab(tab)

                if command:
                    btn = ttk.Button(self.notification_frame, text=notif["text"], style=style_name, command=command)
                    btn.pack(side="left", padx=5, fill="x", expand=True)

    def _calculate_hover_color(self, base_color):
        try:
            if not isinstance(base_color, str) or not base_color.startswith('#') or len(base_color) not in [4,
                                                                                                            7]: return '#e0e0e0'
            if len(base_color) == 4:
                r, g, b = [int(c * 2, 16) for c in base_color[1:]]
            else:
                r, g, b = [int(base_color[i:i + 2], 16) for i in (1, 3, 5)]
            factor = 0.85
            r, g, b = max(0, int(r * factor)), max(0, int(g * factor)), max(0, int(b * factor))
            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            return '#e0e0e0'

    def load_all_data(self):
        print("[DEBUG] load_all_data gestartet.")
        try:
            self.load_shift_types()
            self.load_staffing_rules()
            current_year = self.current_display_date.year
            self._load_holidays_for_year(current_year)
            self._load_events_for_year(current_year)
            print(f"[DEBUG] Basisdaten für {current_year} geladen.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Basisdaten: {e}")
            messagebox.showerror("Fehler beim Laden", f"Einige Basisdaten konnten nicht geladen werden:\n{e}",
                                 parent=self)

    def refresh_all_tabs(self):
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs...")
        self.load_all_data()  # Basisdaten neu laden

        loaded_tab_names = list(self.loaded_tabs)
        for tab_name in loaded_tab_names:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    is_tab = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                    if is_tab:
                        if hasattr(frame, 'refresh_data'):
                            print(f"[DEBUG] -> rufe refresh_data() für {tab_name} auf")
                            frame.refresh_data()
                        elif hasattr(frame, 'refresh_plan'):
                            print(f"[DEBUG] -> rufe refresh_plan() für {tab_name} auf")
                            frame.refresh_plan()
                except (tk.TclError, KeyError) as e:
                    print(f"[WARNUNG] Fehler beim Zugriff auf Tab '{tab_name}' für Refresh: {e}")
                except Exception as e:
                    print(f"[FEHLER] Unerwarteter Fehler beim Refresh von Tab '{tab_name}': {e}")

        self.check_for_updates()  # Allgemeine UI-Updates
        print("[DEBUG] Refresh aller geladenen Tabs abgeschlossen.")

    def load_shift_types(self):
        try:
            self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}
            print(f"[DEBUG] {len(self.shift_types_data)} Schichtarten geladen.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Schichtarten: {e}")
            self.shift_types_data = {}

    def load_staffing_rules(self):
        try:
            rules = load_config_json(MIN_STAFFING_RULES_CONFIG_KEY)
            default_colors = {"alert_bg": "#FF5555", "overstaffed_bg": "#FFFF99", "success_bg": "#90EE90",
                              "weekend_bg": "#EAF4FF", "holiday_bg": "#FFD700", "violation_bg": "#FF5555",
                              "Ausstehend": "orange", "Admin_Ausstehend": "#E0B0FF"}
            defaults = {"Mo-Do": {}, "Fr": {}, "Sa-So": {}, "Holiday": {}, "Daily": {}, "Colors": default_colors}

            if not rules or not isinstance(rules, dict):
                print("[WARNUNG] Besetzungsregeln nicht gefunden oder ungültig, verwende Standard.")
                self.staffing_rules = defaults
            else:
                for key, default_val in defaults.items():
                    if key not in rules:
                        rules[key] = default_val
                    elif key == "Colors" and isinstance(rules[key], dict):  # Farben einzeln prüfen
                        for ckey, cval in default_colors.items():
                            if ckey not in rules["Colors"]: rules["Colors"][ckey] = cval
                    elif key == "Colors" and not isinstance(rules[key],
                                                            dict):  # Komplette Colors ersetzen, wenn kein Dict
                        rules["Colors"] = default_colors
                self.staffing_rules = rules
                print("[DEBUG] Besetzungsregeln geladen und validiert.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Besetzungsregeln: {e}")
            self.staffing_rules = defaults  # Fallback

    def _load_holidays_for_year(self, year):
        try:
            self.current_year_holidays = HolidayManager.get_holidays_for_year(year)
            print(f"[DEBUG] Feiertage für {year} geladen.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Feiertage für {year}: {e}")
            self.current_year_holidays = {}

    def _load_events_for_year(self, year):
        try:
            self.events = EventManager.get_events_for_year(year)
            print(f"[DEBUG] Sondertermine für {year} geladen.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Sondertermine für {year}: {e}")
            self.events = {}

    def is_holiday(self, check_date):
        if not isinstance(check_date, date):
            try:
                check_date = date.fromisoformat(str(check_date))
            except (TypeError, ValueError):
                return False
        return check_date in self.current_year_holidays

    def get_event_type(self, current_date):
        if not isinstance(current_date, date):
            try:
                current_date = date.fromisoformat(str(current_date))
            except (TypeError, ValueError):
                return None
        return EventManager.get_event_type(current_date, self.events)

    def get_contrast_color(self, hex_color):
        if not isinstance(hex_color, str) or not hex_color.startswith('#') or len(hex_color) not in [4,
                                                                                                     7]: return 'black'
        try:
            if len(hex_color) == 4:
                r, g, b = [int(c * 2, 16) for c in hex_color[1:]]
            else:
                r, g, b = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
            luminance = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if luminance >= 128 else 'white'
        except ValueError:
            return 'black'

    def load_shift_frequency(self):
        try:
            freq_data = load_shift_frequency()
            return defaultdict(int, freq_data if freq_data else {})
        except Exception as e:
            print(f"[FEHLER] beim Laden der Schichthäufigkeit: {e}")
            return defaultdict(int)

    def save_shift_frequency(self):
        try:
            freq_to_save = dict(self.shift_frequency)
            if not save_shift_frequency(freq_to_save):
                messagebox.showwarning("Speicherfehler", "Die Schichthäufigkeit konnte nicht ... gespeichert werden.",
                                       parent=self)
        except Exception as e:
            print(f"[FEHLER] beim Speichern der Schichthäufigkeit: {e}")
            messagebox.showerror("Schwerer Fehler", f"Speichern der Schichthäufigkeit fehlgeschlagen:\n{e}",
                                 parent=self)

    def reset_shift_frequency(self):
        if messagebox.askyesno("Bestätigen", "Möchten Sie den Zähler ... zurücksetzen?", parent=self):
            try:
                if reset_shift_frequency():
                    self.shift_frequency.clear()
                    messagebox.showinfo("Erfolg", "Der Zähler wurde zurückgesetzt.", parent=self)
                    self.refresh_shift_plan()
                else:
                    messagebox.showerror("Fehler", "Fehler beim Zurücksetzen in der Datenbank.", parent=self)
            except Exception as e:
                print(f"[FEHLER] beim Zurücksetzen der Schichthäufigkeit: {e}")
                messagebox.showerror("Schwerer Fehler", f"Zurücksetzen fehlgeschlagen:\n{e}", parent=self)

    def get_allowed_roles(self):
        current_admin_role = self.user_data.get('role', 'User')
        admin_level = ROLE_HIERARCHY.get(current_admin_role, 0)
        allowed_roles = [role for role, level in ROLE_HIERARCHY.items() if level < admin_level]
        if current_admin_role == "SuperAdmin":
            allowed_roles.append("SuperAdmin")
        return allowed_roles

    def open_user_order_window(self):
        UserOrderWindow(self, callback=self.refresh_all_tabs)

    def open_shift_order_window(self):
        ShiftOrderWindow(self, callback=self.refresh_all_tabs)

    def open_staffing_rules_window(self):
        def save_and_refresh(new_rules):
            print("[DEBUG] Speichere Besetzungsregeln...")
            try:
                if save_config_json(MIN_STAFFING_RULES_CONFIG_KEY, new_rules):
                    self.staffing_rules = new_rules
                    messagebox.showinfo("Gespeichert", "Die Besetzungsregeln wurden erfolgreich aktualisiert.",
                                        parent=self)
                    self.refresh_specific_tab("Schichtplan")
                else:
                    messagebox.showerror("Fehler", "Die Besetzungsregeln konnten nicht ... gespeichert werden.",
                                         parent=self)
            except Exception as e:
                print(f"[FEHLER] beim Speichern der Besetzungsregeln: {e}")
                messagebox.showerror("Schwerer Fehler", f"Speichern fehlgeschlagen:\n{e}", parent=self)

        staffing_window = MinStaffingWindow(self, current_rules=self.staffing_rules, callback=save_and_refresh)
        staffing_window.focus_force()

    def refresh_shift_plan(self):
        self.refresh_specific_tab("Schichtplan")

    def refresh_specific_tab(self, tab_name):
        print(f"[DEBUG] refresh_specific_tab aufgerufen für: {tab_name}")
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                try:
                    is_tab = self.notebook.nametowidget(frame.winfo_parent()) == self.notebook
                except (tk.TclError, KeyError):
                    is_tab = False
                if is_tab:
                    if hasattr(frame, 'refresh_data'):
                        print(f"[DEBUG] -> rufe refresh_data() für {tab_name} auf")
                        try:
                            frame.refresh_data()
                        except Exception as e:
                            print(f"[FEHLER] bei refresh_data() für {tab_name}: {e}")
                    elif hasattr(frame, 'refresh_plan'):
                        print(f"[DEBUG] -> rufe refresh_plan() für {tab_name} auf")
                        try:
                            frame.refresh_plan()
                        except Exception as e:
                            print(f"[FEHLER] bei refresh_plan() für {tab_name}: {e}")
                    else:
                        print(f"[WARNUNG] Tab '{tab_name}' hat keine Refresh-Methode.")
            elif frame and not frame.winfo_exists():
                print(f"[WARNUNG] refresh_specific_tab: {tab_name}-Tab existiert nicht mehr.")
            elif not frame:
                print(f"[WARNUNG] refresh_specific_tab: {tab_name}-Tab nicht im Frame-Dictionary.")
        else:
            print(f"[DEBUG] Tab '{tab_name}' ist nicht geladen, kein Refresh nötig.")

    def open_holiday_settings_window(self):
        HolidaySettingsWindow(self, year=self.current_display_date.year, callback=self.refresh_all_tabs)

    def open_event_settings_window(self):
        EventSettingsWindow(self, year=self.current_display_date.year, callback=self.refresh_all_tabs)

    def open_color_settings_window(self):
        ColorSettingsWindow(self, callback=self.refresh_all_tabs)

    def open_request_settings_window(self):
        RequestSettingsWindow(self)

    def open_planning_assistant_settings(self):
        PlanningAssistantSettingsWindow(self)