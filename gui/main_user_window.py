# gui/main_user_window.py
import tkinter as tk
from tkinter import ttk, messagebox
# import json # ENTFERNT
# import os # ENTFERNT
from datetime import date, datetime, timedelta
import calendar

# --- NEUE IMPORTE für Threading ---
import threading
from queue import Queue, Empty
from utils.threading_utils import ThreadManager
# ---------------------------------

# --- WICHTIGE IMPORTE ---
from .tabs.user_shift_plan_tab import UserShiftPlanTab
from .tabs.vacation_tab import VacationTab
from .tabs.my_requests_tab import MyRequestsTab
from .tabs.user_bug_report_tab import UserBugReportTab
from .tabs.chat_tab import ChatTab
# -------------------------

from .dialogs.bug_report_dialog import BugReportDialog
from .dialogs.tutorial_window import TutorialWindow
from .holiday_manager import HolidayManager
from .event_manager import EventManager
from database.db_shifts import get_all_shift_types
from database.db_requests import (get_unnotified_requests, mark_requests_as_notified,
                                  get_unnotified_vacation_requests_for_user, mark_vacation_requests_as_notified,
                                  get_pending_admin_requests_for_user)
from database.db_reports import (get_unnotified_bug_reports_for_user, mark_bug_reports_as_notified,
                                 get_reports_awaiting_feedback_for_user)
from database.db_users import mark_tutorial_seen, log_user_logout
from .tab_lock_manager import TabLockManager
from database.db_core import load_config_json, load_shift_frequency, save_shift_frequency
from database.db_chat import get_senders_with_unread_messages
from .user_tab_order_manager import UserTabOrderManager as TabOrderManager

DEFAULT_RULES = {"Daily": {}, "Sa-So": {}, "Fr": {}, "Mo-Do": {}, "Holiday": {}, "Colors": {}}


class TabOrderWindow(tk.Toplevel):
    """Fenster zum Anpassen der Reiter-Reihenfolge (Nutzt jetzt DB-Manager)."""

    # (Diese Klasse bleibt unverändert)
    def __init__(self, master, callback, all_tab_names):
        super().__init__(master)
        self.callback = callback
        self.title("Reiter-Reihenfolge anpassen")
        self.geometry("400x500")
        self.transient(master)
        self.grab_set()

        self.main_frame = ttk.Frame(self, padding=10)
        self.main_frame.pack(fill='both', expand=True)

        ttk.Label(self.main_frame, text="Ziehe die Reiter in die gewünschte Reihenfolge.").pack(pady=5)

        self.listbox = tk.Listbox(self.main_frame, selectmode=tk.SINGLE, height=15)
        self.listbox.pack(fill='x', expand=True, pady=10)

        self.current_order = TabOrderManager.load_order()
        for tab in all_tab_names:
            if tab not in self.current_order:
                self.current_order.append(tab)
        self.current_order = [tab for tab in self.current_order if tab in all_tab_names]

        for item in self.current_order:
            self.listbox.insert(tk.END, item)

        self.listbox.bind("<Button-1>", self.on_press)
        self.listbox.bind("<B1-Motion>", self.on_drag)
        self.listbox.bind("<ButtonRelease-1>", self.on_release)

        self.drag_start_index = None

        btn_frame = ttk.Frame(self.main_frame)
        btn_frame.pack(fill='x', pady=10)

        save_btn = ttk.Button(btn_frame, text="Speichern", command=self.save)
        save_btn.pack(side='right', padx=5)

        cancel_btn = ttk.Button(btn_frame, text="Abbrechen", command=self.destroy)
        cancel_btn.pack(side='right')

    def on_press(self, event):
        self.drag_start_index = self.listbox.nearest(event.y)

    def on_drag(self, event):
        if self.drag_start_index is None:
            return
        current_index = self.listbox.nearest(event.y)
        if current_index != self.drag_start_index:
            item = self.listbox.get(self.drag_start_index)
            self.listbox.delete(self.drag_start_index)
            self.listbox.insert(current_index, item)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(current_index)
            self.listbox.activate(current_index)
            self.drag_start_index = current_index

    def on_release(self, event):
        self.drag_start_index = None

    def save(self):
        new_order = list(self.listbox.get(0, tk.END))
        if TabOrderManager.save_order(new_order):
            self.callback(new_order)
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Reihenfolge konnte nicht gespeichert werden.", parent=self)


class MainUserWindow(tk.Toplevel):
    def __init__(self, master, user_data, app):
        print("[DEBUG] MainUserWindow.__init__: Start")
        super().__init__(master)
        self.app = app  # Dies ist der Bootloader (Application)
        self.user_data = user_data
        self.user_id = self.user_data['id']  # Hilfsvariable
        self.show_request_popups = True
        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name}")
        self.attributes('-fullscreen', True)
        self.setup_styles()

        today = date.today()

        # HINWEIS: Dieses Datum wird vom Bootloader (P1a) gesetzt und
        # anschließend vom user_shift_plan_tab (der es lädt) verwaltet.
        self.current_display_date = self.app.current_display_date

        # Basisdaten laden (bleibt synchron, da für UI-Aufbau benötigt)
        # (Diese werden jetzt aus dem Bootloader-Cache (self.app) geholt)
        self.shift_types_data = self.app.shift_types_data
        self.staffing_rules = self.app.staffing_rules

        self.current_year_holidays = {}
        self.events = {}

        # (Diese laden wir weiterhin lokal, da sie User-spezifisch sein könnten)
        self.shift_frequency = self.load_shift_frequency()

        # (Diese sind bereits im Bootloader geladen, wir rufen sie nur auf,
        # um die Caches im Holiday/Event-Manager zu füllen, falls nötig)
        self._load_holidays_for_year(self.current_display_date.year)
        self._load_events_for_year(self.current_display_date.year)
        print("[DEBUG] MainUserWindow.__init__: Basisdaten referenziert.")

        # --- NEU: ThreadManager initialisieren ---
        self.thread_manager = ThreadManager(self)
        # -----------------------------------------

        # --- UI-Gerüst aufbauen ---
        self.setup_ui()
        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- Periodische Checks ---
        self.start_periodic_checkers()  # NEU

        if not self.user_data.get('has_seen_tutorial'):
            self.show_tutorial()

        # --- LAZY LOADING TRIGGER ---
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        if self.notebook.tabs():
            self.notebook.select(0)
            self.on_tab_changed(None)

        print("[DEBUG] MainUserWindow.__init__: Initialisierung abgeschlossen.")

    # --- FUNKTIONEN FÜR TAB-THREADING (Lazy Loading) ---
    # (Dieser Block bleibt unverändert, er nutzt das alte Threading-Modell)

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """
        Läuft im Hintergrund-Thread.
        Erstellt die Tab-Instanz (der langsame Teil).
        """
        try:
            print(f"[Thread] Lade Tab: {tab_name}...")
            if tab_name in ["Schichtplan", "Chat", "Bug-Reports", "Mein Urlaub"]:
                real_tab = TabClass(self.notebook, self)
            else:
                try:
                    real_tab = TabClass(self.notebook, self.user_data)
                except TypeError:
                    print(f"[FEHLER] Fallback-Instanziierung für {tab_name} fehlgeschlagen. Versuche mit 'self'.")
                    real_tab = TabClass(self.notebook, self)

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
            result = self.tab_load_queue.get_nowait()
            tab_name, real_tab, tab_index = result

            print(f"[GUI-Checker] Empfange Ergebnis für: {tab_name}")

            placeholder_frame = self.tab_frames[tab_name]

            if not placeholder_frame.winfo_exists():
                print(f"[GUI-Checker] Platzhalter für {tab_name} existiert nicht mehr. Abbruch.")
                if tab_name in self.loading_tabs:
                    self.loading_tabs.remove(tab_name)
                return

            if isinstance(real_tab, Exception):
                ttk.Label(placeholder_frame,
                          text=f"Fehler beim Laden:\n{real_tab}",
                          font=("Segoe UI", 12), foreground="red").pack(expand=True, anchor="center")
                for widget in placeholder_frame.winfo_children():
                    if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                        widget.destroy()
                if tab_name in self.loading_tabs:
                    self.loading_tabs.remove(tab_name)
            else:
                tab_options = self.notebook.tab(placeholder_frame)

                self.notebook.unbind("<<NotebookTabChanged>>")
                self.notebook.insert(placeholder_frame, real_tab, **tab_options)
                self.notebook.forget(placeholder_frame)
                self.notebook.select(real_tab)
                self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

                self.loaded_tabs.add(tab_name)
                if tab_name in self.loading_tabs:
                    self.loading_tabs.remove(tab_name)
                self.tab_frames[tab_name] = real_tab

                print(f"[GUI-Checker] Tab '{tab_name}' erfolgreich eingesetzt und ausgewählt.")

        except Empty:
            pass

        if not self.winfo_exists():
            return

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
            selected_widget_name = self.notebook.select()
            if not selected_widget_name:
                return
            tab_index = self.notebook.index(selected_widget_name)
            tab_name = self.notebook.tab(tab_index, "text")
        except (tk.TclError, IndexError):
            return

        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs:
            return
        if tab_name not in self.tab_definitions:
            return

        print(f"[GUI] on_tab_changed: Starte Ladevorgang für {tab_name}")

        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames[tab_name]

        if TabLockManager.is_tab_locked(tab_name):
            print(f"[LazyLoad] Tab '{tab_name}' ist gesperrt. Ladevorgang abgebrochen.")
            self.loaded_tabs.add(tab_name)
            return

        if not any(isinstance(w, ttk.Label) for w in placeholder_frame.winfo_children()):
            ttk.Label(placeholder_frame, text=f"Lade {tab_name}...",
                      font=("Segoe UI", 16)).pack(expand=True, anchor="center")

        self.loading_tabs.add(tab_name)

        threading.Thread(
            target=self._load_tab_threaded,
            args=(tab_name, TabClass, tab_index),
            daemon=True
        ).start()

        if not self.tab_load_checker_running:
            if not self.winfo_exists():
                return
            print("[GUI-Checker] Starte Checker-Loop.")
            self.tab_load_checker_running = True
            self.after(100, self._check_tab_load_queue)

    # ----------------------------------------

    def setup_styles(self):
        # (Unverändert)
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('Bug.TButton', background='dodgerblue', foreground='white', font=('Segoe UI', 9, 'bold'))
        style.map('Bug.TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])
        style.configure('Logout.TButton', background='gold', foreground='black', font=('Segoe UI', 10, 'bold'),
                        padding=6)
        style.map('Logout.TButton', background=[('active', 'goldenrod')], foreground=[('active', 'black')])

    def on_close(self):
        # (Unverändert)
        log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        self.app.on_app_close()

    def logout(self):
        # (Unverändert)
        log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        # KORREKTUR: on_logout erwartet keine Argumente
        self.app.on_logout()

    def setup_ui(self):
        # (Unverändert)
        header_frame = ttk.Frame(self);
        header_frame.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Button(header_frame, text="Tutorial", command=self.show_tutorial).pack(side="left", padx=(0, 5))
        ttk.Button(header_frame, text="Reiter anpassen", command=self.open_tab_order_window).pack(side="right")
        self.chat_notification_frame = tk.Frame(self, bg='tomato', cursor="hand2")
        self.admin_request_frame = tk.Frame(self, bg='orange', height=40, cursor="hand2")
        self.bug_feedback_frame = tk.Frame(self, bg='deepskyblue', height=40, cursor="hand2")
        self.notebook = ttk.Notebook(self);
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_definitions = {
            "Schichtplan": UserShiftPlanTab,
            "Chat": ChatTab,
            "Meine Anfragen": MyRequestsTab,
            "Mein Urlaub": VacationTab,
            "Bug-Reports": UserBugReportTab
        }
        self.tab_frames = {};
        self.loaded_tabs = set()

        self.loading_tabs = set()
        self.tab_load_queue = Queue()
        self.tab_load_checker_running = False

        self.setup_lazy_tabs()

    def setup_lazy_tabs(self):
        # (Unverändert)
        print("[DEBUG] setup_lazy_tabs: Erstelle Platzhalter...")
        saved_order = TabOrderManager.load_order()
        all_defined_tabs = self.tab_definitions.keys()
        final_order = [tab for tab in saved_order if tab in all_defined_tabs]
        final_order.extend([tab for tab in all_defined_tabs if tab not in final_order])
        for tab_name in final_order:
            frame = ttk.Frame(self.notebook, padding=20)
            self.notebook.add(frame, text=tab_name)
            self.tab_frames[tab_name] = frame
            if TabLockManager.is_tab_locked(tab_name):
                self.create_lock_overlay(frame)

    # --- START: PERIODISCHE CHECKS (THREAD-BASIERT) ---

    def start_periodic_checkers(self):
        """Startet die beiden periodischen Checker-Schleifen."""
        self.after(500, self.run_periodic_checks_threaded)
        self.after(2000, self.check_chat_notifications_threaded)

    # --- 1. Schleife: Allgemeine Benachrichtigungen (60 Sek.) ---

    def run_periodic_checks_threaded(self):
        """[GUI-Thread] Startet die Worker für die 60-Sekunden-Checks."""
        if not self.winfo_exists(): return

        print("[DEBUG] run_periodic_checks_threaded: Starte Worker...")
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self._fetch_periodic_data,
            self._on_periodic_data_fetched,
            self.user_id,
            self.show_request_popups
        )
        # -----------------------------------

    def _fetch_periodic_data(self, user_id, show_popups):
        """
        [WORKER-THREAD] Führt alle 60-Sekunden-DB-Abfragen aus.
        """
        results = {
            "all_notifications_data": None,
            "admin_requests_count": 0,
            "bug_feedback_ids": []
        }
        try:
            if show_popups:
                unnotified_requests = get_unnotified_requests(user_id)
                unnotified_vacation = get_unnotified_vacation_requests_for_user(user_id)
                unnotified_reports = get_unnotified_bug_reports_for_user(user_id)
                results["all_notifications_data"] = {
                    "requests": unnotified_requests,
                    "vacation": unnotified_vacation,
                    "reports": unnotified_reports
                }

            results["admin_requests_count"] = get_pending_admin_requests_for_user(user_id)
            results["bug_feedback_ids"] = get_reports_awaiting_feedback_for_user(user_id)

            return results
        except Exception as e:
            print(f"[FEHLER] in _fetch_periodic_data (Thread): {e}")
            return e

    def _on_periodic_data_fetched(self, result, error):
        """
        [GUI-Thread] Verarbeitet die Ergebnisse der 60-Sekunden-Checks.
        """
        if not self.winfo_exists():
            print("[DEBUG] _on_periodic_data_fetched: Fenster existiert nicht mehr.")
            return

        if error:
            print(f"[FEHLER] _on_periodic_data_fetched: {error}")
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_periodic_data_fetched (von Thread): {result}")
        elif result:
            if self.show_request_popups:
                self._process_all_notifications(result.get("all_notifications_data"))

            self._update_admin_requests_ui(result.get("admin_requests_count", 0))
            self._update_bug_feedback_ui(result.get("bug_feedback_ids", []))

        self.after(60000, self.run_periodic_checks_threaded)

    # --- 2. Schleife: Chat-Benachrichtigungen (10 Sek.) ---

    def check_chat_notifications_threaded(self):
        """[GUI-Thread] Startet den Worker für die 10-Sekunden-Chat-Checks."""
        if not self.winfo_exists(): return

        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            get_senders_with_unread_messages,
            self._on_chat_data_fetched,
            self.user_id
        )
        # -----------------------------------

    def _on_chat_data_fetched(self, result, error):
        """[GUI-Thread] Verarbeitet das Ergebnis der Chat-Abfrage."""
        if not self.winfo_exists():
            print("[DEBUG] _on_chat_data_fetched: Fenster existiert nicht mehr.")
            return

        senders = result
        if error:
            print(f"[FEHLER] _on_chat_data_fetched: {error}")
            senders = []
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_chat_data_fetched (von Thread): {result}")
            senders = []

        try:
            for widget in self.chat_notification_frame.winfo_children():
                widget.destroy()

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
        except Exception as e:
            print(f"[FEHLER] bei _on_chat_data_fetched UI-Update: {e}")
            if self.chat_notification_frame.winfo_ismapped():
                self.chat_notification_frame.pack_forget()
        finally:
            self.after(10000, self.check_chat_notifications_threaded)

    # --- Veraltete Funktionen ---
    def run_periodic_checks(self):
        pass

    def check_chat_notifications(self):
        pass

    # --- ENDE: PERIODISCHE CHECKS (THREAD-BASIERT) ---

    def go_to_chat(self, user_id):
        # (Unverändert)
        self.switch_to_tab("Chat")

        def _select_user_after_load():
            if not self.winfo_exists(): return

            if "Chat" in self.loaded_tabs and hasattr(self.tab_frames["Chat"], "select_user"):
                print(f"[DEBUG] Chat-Tab ist geladen, rufe select_user({user_id}) auf.")
                self.tab_frames["Chat"].select_user(user_id)
            elif "Chat" in self.loading_tabs or "Chat" not in self.loaded_tabs:
                print("[DEBUG] go_to_chat: Chat-Tab noch nicht geladen, warte 200ms...")
                self.after(200, _select_user_after_load)
            else:
                print(f"[DEBUG] go_to_chat: Konnte Benutzer {user_id} nicht auswählen, Tab-Status unbekannt.")

        _select_user_after_load()

    def switch_to_tab(self, tab_name):
        # (Unverändert)
        if tab_name in self.tab_frames:
            frame = self.tab_frames[tab_name]
            self.notebook.select(frame)
        else:
            print(f"[DEBUG] switch_to_tab: Tab '{tab_name}' nicht in self.tab_frames gefunden.")

    def create_lock_overlay(self, parent_frame):
        # (Unverändert)
        overlay = tk.Frame(parent_frame, bg='gray90', relief='raised', borderwidth=2)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1, anchor='nw')
        msg_frame = ttk.Frame(overlay, style="Overlay.TFrame");
        msg_frame.place(relx=0.5, rely=0.5, anchor='center')
        style = ttk.Style();
        style.configure("Overlay.TFrame", background='gray90')
        ttk.Label(msg_frame, text="🔧", font=('Segoe UI', 48, 'bold'), background='gray90', foreground='gray60').pack(
            pady=10)
        ttk.Label(msg_frame, text="Wartungsarbeiten", font=('Segoe UI', 22, 'bold'), background='gray90',
                  foreground='gray60').pack(pady=5)
        ttk.Label(msg_frame, text="Dieser Bereich wird gerade überarbeitet und ist in Kürze wieder verfügbar.",
                  font=('Segoe UI', 12), background='gray90', foreground='gray60').pack(pady=10)
        overlay.bind("<Button-1>", lambda e: "break");
        overlay.bind("<B1-Motion>", lambda e: "break")

    def get_tab(self, tab_name):
        # (Unverändert)
        return self.tab_frames.get(tab_name)

    def setup_footer(self):
        # (Unverändert)
        footer_frame = ttk.Frame(self, padding=5);
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def open_bug_report_dialog(self):
        # (Unverändert)
        BugReportDialog(self, self.user_data['id'])

    def show_tutorial(self):
        # (Unverändert)
        TutorialWindow(self);
        mark_tutorial_seen(self.user_data['id']);
        self.user_data['has_seen_tutorial'] = 1

    def open_tab_order_window(self):
        # (Unverändert)
        all_tab_names = list(self.tab_definitions.keys());
        TabOrderWindow(self, self.reorder_tabs, all_tab_names)

    def reorder_tabs(self, new_order):
        # (Unverändert)
        try:
            selected_tab_frame = self.notebook.nametowidget(self.notebook.select())
        except tk.TclError:
            selected_tab_frame = None
        for tab_frame_widget in self.notebook.tabs():
            self.notebook.forget(tab_frame_widget)
        for tab_name in new_order:
            frame_widget = self.tab_frames.get(tab_name)
            if frame_widget:
                current_text = self.notebook.tab(frame_widget, "text")
                if not current_text:
                    current_text = tab_name
                self.notebook.add(frame_widget, text=current_text)
        if selected_tab_frame and selected_tab_frame in self.notebook.tabs():
            self.notebook.select(selected_tab_frame)
        elif self.notebook.tabs():
            self.notebook.select(0)

    # --- UI-Update-Funktionen (aufgeteilt) ---

    def _update_admin_requests_ui(self, count):
        """[GUI-Thread] Aktualisiert die Admin-Anfrage-Leiste."""
        if not self.winfo_exists(): return
        try:
            for widget in self.admin_request_frame.winfo_children(): widget.destroy()

            if count > 0:
                self.admin_request_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)
                label_text = f"Sie haben {count} offene Schichtanfrage vom Admin!" if count > 1 else "Sie haben 1 offene Schichtanfrage vom Admin!"
                action = lambda event=None: self.go_to_shift_plan()
                notification_label = tk.Label(self.admin_request_frame, text=label_text, bg='orange', fg='black',
                                              font=('Segoe UI', 12, 'bold'), cursor="hand2")
                notification_label.pack(side='left', padx=15, pady=5);
                notification_label.bind("<Button-1>", action);
                self.admin_request_frame.bind("<Button-1>", action)
                show_button = ttk.Button(self.admin_request_frame, text="Anzeigen", command=action);
                show_button.pack(side='right', padx=15)
            else:
                self.admin_request_frame.pack_forget()
        except Exception as e:
            print(f"[FEHLER] _update_admin_requests_ui: {e}")
            if self.admin_request_frame.winfo_ismapped():
                self.admin_request_frame.pack_forget()

    def _update_bug_feedback_ui(self, report_ids):
        """[GUI-Thread] Aktualisiert die Bug-Feedback-Leiste."""
        if not self.winfo_exists(): return
        try:
            for widget in self.bug_feedback_frame.winfo_children(): widget.destroy()

            count = len(report_ids)
            if count > 0:
                first_report_id = report_ids[0];
                action = lambda event=None: self.go_to_bug_reports(first_report_id)
                self.bug_feedback_frame.pack(fill='x', side='top', ipady=5, before=self.notebook);
                self.bug_feedback_frame.bind("<Button-1>", action)
                label_text = f"Deine Rückmeldung wird für {count} Bug-Report(s) benötigt!"
                notification_label = tk.Label(self.bug_feedback_frame, text=label_text, bg='deepskyblue', fg='white',
                                              font=('Segoe UI', 12, 'bold'), cursor="hand2")
                notification_label.pack(side='left', padx=15, pady=5);
                notification_label.bind("<Button-1>", action)
                show_button = ttk.Button(self.bug_feedback_frame, text="Anzeigen", command=action);
                show_button.pack(side='right', padx=15)
            else:
                self.bug_feedback_frame.pack_forget()
        except Exception as e:
            print(f"[FEHLER] _update_bug_feedback_ui: {e}")
            if self.bug_feedback_frame.winfo_ismapped():
                self.bug_feedback_frame.pack_forget()

    def _process_all_notifications(self, data):
        """
        [GUI-Thread] Verarbeitet die Popup-Benachrichtigungen.
        """
        if not data or not self.winfo_exists():
            return

        all_messages = [];
        tabs_to_refresh = []

        unnotified_requests = data.get("requests", [])
        unnotified_vacation = data.get("vacation", [])
        unnotified_reports = data.get("reports", [])

        try:
            if unnotified_requests:
                message_lines = ["Sie haben Neuigkeiten zu Ihren 'Wunschfrei'-Anträgen:"];
                notified_ids = [req['id'] for req in unnotified_requests]
                for req in unnotified_requests:
                    req_date = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
                    status_line = f"- Ihr Antrag für den {req_date} wurde {req['status']}."
                    if req['status'] == 'Abgelehnt' and req.get(
                            'rejection_reason'): status_line += f" Grund: {req['rejection_reason']}"
                    message_lines.append(status_line)
                all_messages.append("\n".join(message_lines));
                mark_requests_as_notified(notified_ids);
                tabs_to_refresh.append("Meine Anfragen")

            if unnotified_vacation:
                message_lines = ["Es gibt Neuigkeiten zu Ihren Urlaubsanträgen:"];
                notified_ids = [req['id'] for req in unnotified_vacation]
                for req in unnotified_vacation:
                    start = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m');
                    end = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
                    message_lines.append(f"- Ihr Urlaub von {start} bis {end} wurde {req['status']}.")
                all_messages.append("\n".join(message_lines));
                mark_vacation_requests_as_notified(notified_ids);
                tabs_to_refresh.append("Mein Urlaub")

            if unnotified_reports:
                message_lines = ["Es gibt Neuigkeiten zu Ihren Fehlerberichten:"];
                notified_ids = [report['id'] for report in unnotified_reports]
                for report in unnotified_reports:
                    title = report['title'];
                    status = report['status'];
                    message_lines.append(f"- Ihr Bericht '{title[:30]}...' hat jetzt den Status: {status}.")
                all_messages.append("\n".join(message_lines));
                mark_bug_reports_as_notified(notified_ids);
                tabs_to_refresh.append("Bug-Reports")

            if all_messages and self.show_request_popups:
                messagebox.showinfo("Benachrichtigungen", "\n\n".join(all_messages), parent=self)
                if self.winfo_exists():
                    if "Meine Anfragen" in tabs_to_refresh and "Meine Anfragen" in self.loaded_tabs:
                        self.tab_frames["Meine Anfragen"].refresh_data()
                    if "Mein Urlaub" in tabs_to_refresh and "Mein Urlaub" in self.loaded_tabs:
                        self.tab_frames["Mein Urlaub"].refresh_data()
                    if "Bug-Reports" in tabs_to_refresh and "Bug-Reports" in self.loaded_tabs:
                        if hasattr(self.tab_frames["Bug-Reports"], 'load_reports'):
                            self.tab_frames["Bug-Reports"].load_reports()
        except Exception as e:
            print(f"[FEHLER] _process_all_notifications: {e}")

    # Veraltete Funktionen
    def check_for_admin_requests(self):
        pass

    def check_for_bug_feedback_requests(self):
        pass

    def check_all_notifications(self):
        pass

    def go_to_shift_plan(self):
        # (Unverändert)
        self.switch_to_tab("Schichtplan")

    def go_to_bug_reports(self, report_id=None):
        # (Unverändert)
        self.switch_to_tab("Bug-Reports")

        def _select_report_after_load():
            if not self.winfo_exists(): return

            if "Bug-Reports" in self.loaded_tabs and hasattr(self.tab_frames["Bug-Reports"], "select_report"):
                self.tab_frames["Bug-Reports"].select_report(report_id)
            elif "Bug-Reports" in self.loading_tabs or "Bug-Reports" not in self.loaded_tabs:
                self.after(200, _select_report_after_load)

        if report_id:
            _select_report_after_load()

    # --- Datenladefunktionen (bleiben gleich) ---
    def _load_holidays_for_year(self, year):
        # (Unverändert)
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def _load_events_for_year(self, year):
        # (Unverändert)
        self.events = EventManager.get_events_for_year(year)

    def is_holiday(self, check_date):
        # (Unverändert)
        # Greift auf die statische Methode zu (wie im Bootloader)
        return HolidayManager.is_holiday(check_date)

    def get_event_type(self, current_date):
        # (Unverändert)
        # Greift auf die statische Methode zu (wie im Bootloader)
        year_events = EventManager.get_events_for_year(current_date.year)
        return year_events.get(current_date.strftime('%Y-%m-%d'))

    def load_shift_types(self):
        # (Unverändert)
        # Nutzt die bereits im Bootloader (self.app) geladenen Daten
        self.shift_types_data = self.app.shift_types_data

    def get_contrast_color(self, hex_color):
        # (Unverändert)
        # Nutzt die Hilfsfunktion vom Bootloader (self.app)
        return self.app.get_contrast_color(hex_color)

    def load_staffing_rules(self):
        # (Unverändert)
        # Nutzt die bereits im Bootloader (self.app) geladenen Daten
        return self.app.staffing_rules

    def load_shift_frequency(self):
        # (Unverändert)
        freq_data = load_shift_frequency()
        return freq_data if freq_data else {}

    def save_shift_frequency(self):
        # (Unverändert)
        pass

    # --- NEU (P4): Proxy-Methode zum Auslösen des Preloaders ---
    def trigger_shift_plan_preload(self, new_year, new_month):
        """
        Proxy-Methode (P4): Leitet den Blättern-Trigger an den PreloadingManager (auf self.app) weiter.
        """
        # Greift auf den Manager zu, der auf der Bootloader-Instanz (self.app) lebt
        if hasattr(self.app, 'preloading_manager') and self.app.preloading_manager:
            self.app.preloading_manager.trigger_shift_plan_preload(new_year, new_month)
        else:
            print("[WARNUNG MUW] PreloadingManager nicht auf app gefunden. P4-Trigger ignoriert.")
    # -------------------------------------------------------------------