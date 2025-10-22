# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta
import calendar
from collections import defaultdict

# --- NEUE IMPORTE für Threading ---
import threading
from queue import Queue, Empty
# ---------------------------------

# --- WICHTIGE IMPORTE ---
from .tabs.shift_plan_tab import ShiftPlanTab
from .tabs.user_management_tab import UserManagementTab
from .tabs.dog_management_tab import DogManagementTab
from .tabs.shift_types_tab import ShiftTypesTab
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
from .tabs.settings_tab import SettingsTab

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
    run_db_fix_approve_all_users  # <-- NEUER IMPORT
)
from database.db_chat import get_senders_with_unread_messages
from database.db_users import log_user_logout
from database.db_shifts import get_all_shift_types
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count, get_reports_with_user_feedback_count
from database.db_admin import get_pending_password_resets_count

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
        self.app = app
        self.user_data = user_data

        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name} (Admin)")
        self.attributes('-fullscreen', True)

        self.setup_styles()

        # Diese Daten werden *sofort* geladen (noch im Lade-Thread).
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

        # --- UI-Aufbau (nur das Gerüst) ---
        self.header_frame = ttk.Frame(self, padding=(10, 5, 10, 0))
        self.header_frame.pack(fill='x')
        self.setup_header()  # Header-Menüs (schnell)

        self.chat_notification_frame = tk.Frame(self, bg='tomato', cursor="hand2")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        # --- LAZY LOADING SETUP (STUFE 3) ---
        self.tab_definitions = {
            "Schichtplan": ShiftPlanTab,
            "Chat": ChatTab,
            "Teilnahmen": ParticipationTab,
            "Mitarbeiter": UserManagementTab,
            "Diensthunde": DogManagementTab,
            "Wunschanfragen": RequestsTab,
            "Urlaubsanträge": VacationRequestsTab,
            "Bug-Reports": BugReportsTab,
            "Logs": LogTab,
            "Protokoll": ProtokollTab,
            "Einstellungen": SettingsTab
        }
        self.tab_frames = {}
        self.loaded_tabs = set()

        # --- NEU: Threading für Tabs ---
        self.loading_tabs = set()
        self.tab_load_queue = Queue()
        self.tab_load_checker_running = False
        # -------------------------------

        self.setup_lazy_tabs()
        print("[DEBUG] MainAdminWindow.__init__: Lazy Tabs (Platzhalter) erstellt.")

        self.setup_footer()  # Footer (schnell)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- Periodische Updates starten ---
        self.after(1000, self.check_for_updates)
        self.after(2000, self.check_chat_notifications)

        # --- LAZY LOADING TRIGGER ---
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        if self.notebook.tabs():
            self.notebook.select(0)
            self.on_tab_changed(None)

        print("[DEBUG] MainAdminWindow.__init__: Initialisierung abgeschlossen.")

    # --- NEUE FUNKTIONEN FÜR TAB-THREADING ---

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """
        Läuft im Hintergrund-Thread.
        Erstellt die Tab-Instanz (der langsame Teil).
        """
        try:
            print(f"[Thread] Lade Tab: {tab_name}...")
            # Wenn der Tab UserTabSettingsTab ist, benötigt er die Liste der User-Tabs als Argument
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            else:
                real_tab = TabClass(self.notebook, self)

            # Ergebnis in die Queue legen
            self.tab_load_queue.put((tab_name, real_tab, tab_index))
            print(f"[Thread] Tab '{tab_name}' fertig geladen.")
        except Exception as e:
            print(f"[Thread] FEHLER beim Laden von Tab '{tab_name}': {e}")
            self.tab_load_queue.put((tab_name, e, tab_index))

    def _check_tab_load_queue(self):
        """
        Läuft im GUI-Thread (via 'after').
        Prüft die Queue und setzt die fertigen Tabs ein.
        """
        try:
            # (tab_name, real_tab_or_exception, tab_index)
            result = self.tab_load_queue.get_nowait()
            tab_name, real_tab, tab_index = result

            print(f"[GUI-Checker] Empfange Ergebnis für: {tab_name}")

            # Hole den Platzhalter-Frame
            placeholder_frame = self.tab_frames[tab_name]

            # Prüfen, ob beim Laden ein Fehler aufgetreten ist
            if isinstance(real_tab, Exception):
                # Fehler anzeigen
                ttk.Label(placeholder_frame,
                          text=f"Fehler beim Laden:\n{real_tab}",
                          font=("Segoe UI", 12), foreground="red").pack(expand=True, anchor="center")
                # Lade-Label entfernen
                for widget in placeholder_frame.winfo_children():
                    if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                        widget.destroy()
                self.loading_tabs.remove(tab_name)  # Ladeversuch beendet (gescheitert)
            else:
                # Erfolgreich geladen!
                # 1. Tab-Optionen vom Platzhalter holen
                tab_options = self.notebook.tab(placeholder_frame)

                # 2. Den Platzhalter aus dem Notebook entfernen
                self.notebook.forget(placeholder_frame)

                # 3. Den echten Tab an derselben Stelle einfügen
                self.notebook.insert(tab_index, real_tab, **tab_options)

                # 4. Den neuen, echten Tab auswählen (WICHTIG!)
                self.notebook.select(real_tab)

                # 5. Status aktualisieren
                self.loaded_tabs.add(tab_name)
                self.loading_tabs.remove(tab_name)
                self.tab_frames[tab_name] = real_tab  # Ersetze Platzhalter
                print(f"[GUI-Checker] Tab '{tab_name}' erfolgreich eingesetzt.")

        except Empty:
            # Queue ist leer, nichts zu tun
            pass

        if not self.tab_load_queue.empty() or self.loading_tabs:
            self.after(100, self._check_tab_load_queue)
        else:
            self.tab_load_checker_running = False
            print("[GUI-Checker] Alle Lade-Threads beendet. Checker pausiert.")

    def on_tab_changed(self, event):
        """
        Wird jedes Mal aufgerufen, wenn der Benutzer einen Tab anklickt.
        Startet jetzt nur noch den Lade-Thread.
        """
        try:
            tab_index = self.notebook.index(self.notebook.select())
            tab_name_with_count = self.notebook.tab(tab_index, "text")
            tab_name = tab_name_with_count.split(" (")[0]
        except (tk.TclError, IndexError):
            return

            # Prüfen, ob dieser Tab bereits geladen ist ODER gerade lädt
        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
            return

        if tab_name not in self.tab_definitions:
            return

        print(f"[GUI] on_tab_changed: Starte Ladevorgang für {tab_name}")

        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames[tab_name]

        # 1. "Wird geladen..."-Nachricht im Platzhalter anzeigen
        ttk.Label(placeholder_frame, text=f"Lade {tab_name}...",
                  font=("Segoe UI", 16), name="loading_label").pack(expand=True, anchor="center")

        # 2. Status auf "lädt" setzen
        self.loading_tabs.add(tab_name)

        # 3. Hintergrund-Thread starten
        threading.Thread(
            target=self._load_tab_threaded,
            args=(tab_name, TabClass, tab_index),
            daemon=True
        ).start()

        # 4. Den Queue-Checker starten (falls er nicht schon läuft)
        if not self.tab_load_checker_running:
            print("[GUI-Checker] Starte Checker-Loop.")
            self.tab_load_checker_running = True
            self.after(100, self._check_tab_load_queue)

    # ----------------------------------------

    def setup_styles(self):
        # ... (unverändert) ...
        self.style = ttk.Style(self)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass
        self.style.configure('Bug.TButton', background='dodgerblue', foreground='white', font=('Segoe UI', 9, 'bold'))
        self.style.map('Bug.TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])
        self.style.configure('Logout.TButton', background='gold', foreground='black', font=('Segoe UI', 10, 'bold'),
                             padding=6)
        self.style.map('Logout.TButton', background=[('active', 'goldenrod')], foreground=[('active', 'black')])
        self.style.configure('Notification.TButton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))
        self.style.map('Notification.TButton', background=[('active', '#e0e0e0')], relief=[('pressed', 'sunken')])
        self.style.configure('Settings.TMenubutton', font=('Segoe UI', 10, 'bold'), padding=(10, 5))

    def setup_lazy_tabs(self):
        print("[DEBUG] setup_lazy_tabs: Erstelle Platzhalter...")
        for tab_name in self.tab_definitions.keys():
            placeholder_frame = ttk.Frame(self.notebook, padding=20)
            self.notebook.add(placeholder_frame, text=tab_name)
            self.tab_frames[tab_name] = placeholder_frame
        self.update_tab_titles()

    def update_single_tab_text(self, tab_name, new_text):
        if tab_name in self.tab_frames:
            frame = self.tab_frames[tab_name]
            try:
                if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                    self.notebook.tab(frame, text=new_text)
            except tk.TclError:
                print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name}")

    def update_tab_titles(self):
        # ... (unverändert) ...
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

    def switch_to_tab(self, tab_name):
        if tab_name in self.tab_frames:
            frame = self.tab_frames[tab_name]
            self.notebook.select(frame)
        else:
            print(f"[DEBUG] switch_to_tab: Tab '{tab_name}' nicht in self.tab_frames gefunden.")

    def _load_dynamic_tab(self, tab_name, TabClass, *args):
        """
        Angepasste Funktion für dynamische Tabs, nutzt jetzt auch den Thread-Loader.
        """
        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
            # Tab ist schon geladen/lädt gerade. Nur auswählen.
            self.notebook.select(self.tab_frames[tab_name])
            return

        print(f"[LazyLoad] Lade dynamischen Tab: {tab_name}")

        # 1. Platzhalter erstellen
        placeholder_frame = ttk.Frame(self.notebook, padding=20)
        ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16)).pack(expand=True,
                                                                                             anchor="center")
        self.notebook.add(placeholder_frame, text=tab_name)
        self.notebook.select(placeholder_frame)

        tab_index = self.notebook.index(placeholder_frame)
        self.tab_frames[tab_name] = placeholder_frame
        self.loading_tabs.add(tab_name)

        # 2. Thread-Target anpassen, um *args zu übergeben
        def _load_dynamic_tab_threaded():
            try:
                print(f"[Thread] Lade dynamischen Tab: {tab_name}...")
                # Erstelle den Tab mit den *args (z.B. all_user_tab_names)
                if TabClass.__name__ == "UserTabSettingsTab":
                    # Spezialfall für UserTabSettingsTab, der all_user_tab_names als Argument erwartet
                    all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                          "Chat"]
                    real_tab = TabClass(self.notebook, all_user_tab_names)
                else:
                    # Annahme für die meisten dynamischen Tabs: Sie erwarten master und self (AdminWindow)
                    real_tab = TabClass(self.notebook, self)

                self.tab_load_queue.put((tab_name, real_tab, tab_index))
                print(f"[Thread] Dynamischer Tab '{tab_name}' fertig geladen.")
            except Exception as e:
                print(f"[Thread] FEHLER beim Laden von dynamischem Tab '{tab_name}': {e}")
                self.tab_load_queue.put((tab_name, e, tab_index))

        # 3. Thread starten
        threading.Thread(target=_load_dynamic_tab_threaded, daemon=True).start()

        # 4. Checker starten (falls nötig)
        if not self.tab_load_checker_running:
            print("[GUI-Checker] Starte Checker-Loop.")
            self.tab_load_checker_running = True
            self.after(100, self._check_tab_load_queue)

    def open_request_lock_window(self):
        self._load_dynamic_tab("Antragssperre", RequestLockTab, self)  # Übergibt 'self'

    def open_user_tab_settings(self):
        # ANNAHME: UserTabSettingsTab benötigt die Liste der User-Tabs
        all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen", "Chat"]
        self._load_dynamic_tab("Benutzer-Reiter", UserTabSettingsTab, all_user_tab_names)  # Übergibt Liste

    def open_password_resets_window(self):
        self._load_dynamic_tab("Passwort-Resets", PasswordResetRequestsWindow, self)  # Übergibt 'self'

    def open_shift_types_window(self):
        # ... (unverändert) ...
        print("[DEBUG] Öffne Schichtarten-Dialog...")
        try:
            from .dialogs.shift_type_dialog import ShiftTypeDialog
            ShiftTypeDialog(self, self.refresh_all_tabs)
        except ImportError:
            print("[FEHLER] ShiftTypeDialog nicht gefunden, versuche 'alten' ShiftTypesTab als Dialog")
            try:
                ShiftTypesTab(self, self.refresh_all_tabs)
            except Exception as e:
                print(f"Konnte Schichtarten-Fenster nicht öffnen: {e}")
                messagebox.showerror("Fehler", "Konnte Schichtarten-Editor nicht laden.")

    def on_close(self):
        # ... (unverändert) ...
        self.save_shift_frequency()
        log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        self.app.on_app_close()

    def logout(self):
        # ... (unverändert) ...
        self.save_shift_frequency()
        log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        self.app.on_logout(self)

    def setup_header(self):
        # ... (unverändert) ...
        self.notification_frame = ttk.Frame(self.header_frame)
        self.notification_frame.pack(side="left", fill="x", expand=True)
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

        # --- FIX BUTTONS ---
        settings_menu.add_command(label="⚠️ FIX: ALLE ALTEN USER FREISCHALTEN",
                                  command=self.apply_all_users_approval_fix)
        settings_menu.add_command(label="DB-Update: Freischaltung Spalte", command=self.apply_is_approved_fix)
        settings_menu.add_command(label="DB-Update für Chat ausführen", command=self.apply_database_fix)

    def apply_all_users_approval_fix(self):
        """Löst das manuelle Update aus, um alle bestehenden User freizuschalten (is_approved=1)."""
        if messagebox.askyesno("ACHTUNG: FIX BESTÄTIGEN",
                               "Sind Sie sicher, dass Sie ALLE bestehenden Benutzer freischalten möchten (is_approved=1)? Dies behebt das aktuelle Login-Problem.",
                               parent=self):
            success, message = run_db_fix_approve_all_users()
            if success:
                messagebox.showinfo("Erfolg: Login-Problem behoben",
                                    f"{message}\n\nBitte melden Sie sich nun ab und mit Ihren normalen Daten wieder an.",
                                    parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def apply_is_approved_fix(self):
        """Löst das manuelle Update für die is_approved Spalte aus."""
        if messagebox.askyesno("Bestätigung",
                               "Dies führt ein einmaliges Update durch, um die fehlende 'is_approved' Spalte hinzuzufügen. Dies behebt den Fehler bei der Benutzerregistrierung.",
                               parent=self):
            success, message = run_db_update_is_approved()
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def apply_database_fix(self):
        # ... (unverändert) ...
        if messagebox.askyesno("Bestätigung",
                               "Dies führt ein einmaliges Update der Datenbank für die Chat-Funktion durch. Fortfahren?",
                               parent=self):
            success, message = run_db_update_v1()
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def setup_footer(self):
        # ... (unverändert) ...
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def check_chat_notifications(self):
        # ... (unverändert) ...
        for widget in self.chat_notification_frame.winfo_children():
            widget.destroy()
        senders = get_senders_with_unread_messages(self.user_data['id'])
        if senders:
            latest_sender_id = senders[0]['sender_id']
            total_unread = sum(s['unread_count'] for s in senders)
            action = lambda event=None: self.go_to_chat(latest_sender_id)
            self.chat_notification_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)
            self.chat_notification_frame.bind("<Button-1>", action)
            label_text = f"Sie haben {total_unread} neue Nachricht(en)! Hier klicken zum Anzeigen."
            notification_label = tk.Label(self.chat_notification_frame, text=label_text, bg='tomato', fg='white',
                                          font=('Segoe UI', 12, 'bold'), cursor="hand2")
            notification_label.pack(side='left', padx=15, pady=5)
            notification_label.bind("<Button-1>", action)
            show_button = ttk.Button(self.chat_notification_frame, text="Anzeigen", command=action)
            show_button.pack(side='right', padx=15)
        else:
            self.chat_notification_frame.pack_forget()
        self.after(10000, self.check_chat_notifications)

    def go_to_chat(self, user_id):
        self.switch_to_tab("Chat")

        def _select_user_after_load():
            if "Chat" in self.loaded_tabs and hasattr(self.tab_frames["Chat"], "select_user"):
                self.tab_frames["Chat"].select_user(user_id)
            elif "Chat" in self.loading_tabs:
                self.after(100, _select_user_after_load)
            else:
                print("[DEBUG] go_to_chat: Konnte Benutzer nicht auswählen, Tab lädt nicht?")

        _select_user_after_load()

    def check_for_updates(self):
        # ... (unverändert) ...
        self.update_tab_titles()
        self.update_header_notifications()
        if "Mitarbeiter" in self.loaded_tabs and hasattr(self.tab_frames["Mitarbeiter"],
                                                         'update_password_reset_button'):
            self.tab_frames["Mitarbeiter"].update_password_reset_button()
        self.after(60000, self.check_for_updates)

    def open_bug_report_dialog(self):
        # ... (unverändert) ...
        BugReportDialog(self, self.user_data['id'], self.check_for_updates)

    def refresh_antragssperre_views(self):
        # ... (unverändert, sicherer Zugriff) ...
        if "Schichtplan" in self.loaded_tabs and self.tab_frames["Schichtplan"].winfo_exists():
            self.tab_frames["Schichtplan"].update_lock_status()
        if "Antragssperre" in self.loaded_tabs and self.tab_frames["Antragssperre"].winfo_exists():
            self.tab_frames["Antragssperre"].load_locks_for_year()

    def update_header_notifications(self):
        # ... (unverändert) ...
        for widget in self.notification_frame.winfo_children(): widget.destroy()
        notifications = []
        pending_password_resets = get_pending_password_resets_count()
        if pending_password_resets > 0: notifications.append(
            {"text": f"{pending_password_resets} Passwort-Reset(s)", "bg": "mediumpurple", "fg": "white",
             "action": self.open_password_resets_window})
        pending_wunsch_count = len(get_pending_wunschfrei_requests())
        if pending_wunsch_count > 0: notifications.append(
            {"text": f"{pending_wunsch_count} Offene Wunschanfrage(n)", "bg": "orange", "fg": "black",
             "tab": "Wunschanfragen"})
        pending_urlaub_count = get_pending_vacation_requests_count()
        if pending_urlaub_count > 0: notifications.append(
            {"text": f"{pending_urlaub_count} Offene Urlaubsanträge", "bg": "lightblue", "fg": "black",
             "tab": "Urlaubsanträge"})
        user_feedback_count = get_reports_with_user_feedback_count()
        if user_feedback_count > 0: notifications.append(
            {"text": f"{user_feedback_count} User-Feedback(s)", "bg": "springgreen", "fg": "black",
             "tab": "Bug-Reports"})
        open_bug_count = get_open_bug_reports_count()
        if open_bug_count > 0: notifications.append(
            {"text": f"{open_bug_count} Offene Bug-Report(s)", "bg": "tomato", "fg": "white", "tab": "Bug-Reports"})
        if not notifications:
            ttk.Label(self.notification_frame, text="Keine neuen Benachrichtigungen",
                      font=('Segoe UI', 10, 'italic')).pack()
        else:
            for i, notif in enumerate(notifications):
                self.style.configure(f'Notif{i}.TButton', background=notif["bg"], foreground=notif["fg"])
                command = notif.get("action", lambda tab=notif["tab"]: self.switch_to_tab(tab))
                btn = ttk.Button(self.notification_frame, text=notif["text"], style=f'Notif{i}.TButton',
                                 command=command)
                btn.pack(side="left", padx=5, fill="x", expand=True)

    def load_all_data(self):
        # ... (unverändert) ...
        self.load_shift_types()
        self.load_staffing_rules()
        self._load_holidays_for_year(self.current_display_date.year)
        self._load_events_for_year(self.current_display_date.year)

    def refresh_all_tabs(self):
        # ... (unverändert, sicherer Zugriff) ...
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs...")
        self.load_all_data()
        for tab_name in self.loaded_tabs:
            if tab_name in self.tab_frames:
                tab_frame = self.tab_frames[tab_name]
                if hasattr(tab_frame, 'refresh_data'):
                    print(f"[DEBUG] rufe refresh_data() für {tab_name} auf")
                    tab_frame.refresh_data()
                elif hasattr(tab_frame, 'refresh_plan'):
                    print(f"[DEBUG] rufe refresh_plan() für {tab_name} auf")
                    tab_frame.refresh_plan()
        self.check_for_updates()

    def load_shift_types(self):
        # ... (unverändert) ...
        self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}

    def load_staffing_rules(self):
        # ... (unverändert) ...
        rules = load_config_json(MIN_STAFFING_RULES_CONFIG_KEY)
        if not rules:
            self.staffing_rules = {"Mo-Do": {}, "Fr": {}, "Sa-So": {}, "Holiday": {}, "Daily": {},
                                   "Colors": {"alert_bg": "#FF5555", "overstaffed_bg": "#FFFF99",
                                              "success_bg": "#90EE90", "weekend_bg": "#EAF4FF",
                                              "holiday_bg": "#FFD700"}}
        else:
            self.staffing_rules = rules

    def _load_holidays_for_year(self, year):
        # ... (unverändert) ...
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def _load_events_for_year(self, year):
        # ... (unverändert) ...
        self.events = EventManager.get_events_for_year(year)

    def is_holiday(self, check_date):
        # ... (unverändert) ...
        return check_date in self.current_year_holidays

    def get_event_type(self, current_date):
        # ... (unverändert) ...
        return EventManager.get_event_type(current_date, self.events)

    def get_contrast_color(self, hex_color):
        # ... (unverändert) ...
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def load_shift_frequency(self):
        # ... (unverändert) ...
        freq_data = load_shift_frequency();
        return defaultdict(int, freq_data)

    def save_shift_frequency(self):
        # ... (unverändert) ...
        success = save_shift_frequency(self.shift_frequency)
        if not success: messagebox.showwarning("Speicherfehler",
                                               "Die Schichthäufigkeit konnte nicht in der Datenbank gespeichert werden.",
                                               parent=self)

    def reset_shift_frequency(self):
        # ... (unverändert) ...
        if messagebox.askyesno("Bestätigen", "Möchten Sie den Zähler für die Schichthäufigkeit wirklich zurücksetzen?",
                               parent=self):
            success = reset_shift_frequency()
            if success:
                self.shift_frequency.clear();
                messagebox.showinfo("Erfolg", "Der Zähler wurde zurückgesetzt.", parent=self)
            else:
                messagebox.showerror("Fehler", "Fehler beim Zurücksetzen in der Datenbank.", parent=self)

    def get_allowed_roles(self):
        # ... (unverändert) ...
        admin_level = ROLE_HIERARCHY.get(self.user_data['role'], 0)
        allowed_roles = [role for role, level in ROLE_HIERARCHY.items() if level < admin_level]
        if self.user_data['role'] == "SuperAdmin": allowed_roles.append("SuperAdmin")
        return allowed_roles

    def open_user_order_window(self):
        # ... (unverändert) ...
        UserOrderWindow(self, callback=self.refresh_all_tabs)

    def open_shift_order_window(self):
        # ... (unverändert) ...
        ShiftOrderWindow(self, callback=self.refresh_all_tabs)

    def open_staffing_rules_window(self):
        # ... (unverändert) ...
        def save_and_refresh(new_rules):
            if save_config_json(MIN_STAFFING_RULES_CONFIG_KEY, new_rules):
                self.staffing_rules = new_rules;
                self.refresh_shift_plan()
                messagebox.showinfo("Gespeichert", "Die Besetzungsregeln wurden erfolgreich aktualisiert.", parent=self)
            else:
                messagebox.showerror("Fehler",
                                     "Die Besetzungsregeln konnten nicht in der Datenbank gespeichert werden.",
                                     parent=self)

        staffing_window = MinStaffingWindow(self, current_rules=self.staffing_rules, callback=save_and_refresh)
        staffing_window.focus_force()

    def refresh_shift_plan(self):
        # ... (unverändert, sicherer Zugriff) ...
        if "Schichtplan" in self.loaded_tabs:
            self.tab_frames["Schichtplan"].refresh_plan()

    def open_holiday_settings_window(self):
        # ... (unverändert) ...
        HolidaySettingsWindow(self, year=self.current_display_date.year, callback=self.refresh_all_tabs)

    def open_event_settings_window(self):
        # ... (unverändert) ...
        EventSettingsWindow(self, year=self.current_display_date.year, callback=self.refresh_all_tabs)

    def open_color_settings_window(self):
        # ... (unverändert) ...
        ColorSettingsWindow(self, callback=self.refresh_all_tabs)

    def open_request_settings_window(self):
        # ... (unverändert) ...
        RequestSettingsWindow(self)

    def open_planning_assistant_settings(self):
        # ... (unverändert) ...
        PlanningAssistantSettingsWindow(self)