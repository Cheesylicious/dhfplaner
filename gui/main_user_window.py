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
from .event_manager import EventManager  # Importiert für get_event_type
from database.db_shifts import get_all_shift_types
from database.db_requests import (get_unnotified_requests, mark_requests_as_notified,
                                  get_unnotified_vacation_requests_for_user, mark_vacation_requests_as_notified,
                                  get_pending_admin_requests_for_user)
from database.db_reports import (get_unnotified_bug_reports_for_user, mark_bug_reports_as_notified,
                                 get_reports_awaiting_feedback_for_user)
from database.db_users import mark_tutorial_seen, log_user_logout
from .tab_lock_manager import TabLockManager
from database.db_core import load_config_json, load_shift_frequency, save_shift_frequency  # Angepasste Imports
from database.db_chat import get_senders_with_unread_messages
# --- NEUER IMPORT FÜR DB-GESTEUERTE REIHENFOLGE ---
from .user_tab_order_manager import UserTabOrderManager as TabOrderManager

# USER_TAB_ORDER_FILE = 'user_tab_order_config.json' # ENTFERNT
DEFAULT_RULES = {"Daily": {}, "Sa-So": {}, "Fr": {}, "Mo-Do": {}, "Holiday": {}, "Colors": {}}


# Die ursprüngliche Klasse TabOrderManager wurde entfernt.

class TabOrderWindow(tk.Toplevel):
    """Fenster zum Anpassen der Reiter-Reihenfolge (Nutzt jetzt DB-Manager)."""

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
        # Stelle sicher, dass alle Tabs vorhanden sind, auch neue
        for tab in all_tab_names:
            if tab not in self.current_order:
                self.current_order.append(tab)
        # Entferne alte, nicht mehr existierende Tabs
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
        # Nutzt TabOrderManager (jetzt DB-Manager)
        if TabOrderManager.save_order(new_order):
            self.callback(new_order)
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Reihenfolge konnte nicht gespeichert werden.", parent=self)


class MainUserWindow(tk.Toplevel):
    def __init__(self, master, user_data, app):
        print("[DEBUG] MainUserWindow.__init__: Start")
        super().__init__(master)
        self.app = app
        self.user_data = user_data
        self.show_request_popups = True
        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name}")
        self.attributes('-fullscreen', True)
        self.setup_styles()

        today = date.today()
        if today.month == 12:
            self.current_display_date = today.replace(year=today.year + 1, month=1, day=1)
        else:
            self.current_display_date = today.replace(month=today.month + 1, day=1)

        # Basisdaten laden (passiert im Lade-Thread)
        self.shift_types_data = {}
        self.staffing_rules = self.load_staffing_rules()
        self.current_year_holidays = {}
        self.events = {}
        self.shift_frequency = self.load_shift_frequency()
        self.load_shift_types()
        self._load_holidays_for_year(self.current_display_date.year)
        self._load_events_for_year(self.current_display_date.year)
        print("[DEBUG] MainUserWindow.__init__: Basisdaten geladen.")

        # --- UI-Gerüst aufbauen ---
        self.setup_ui()  # Erstellt Header, leeres Notebook etc.
        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- Periodische Checks ---
        self.after(500, self.run_periodic_checks)

        if not self.user_data.get('has_seen_tutorial'):
            self.show_tutorial()

        # --- LAZY LOADING TRIGGER ---
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        if self.notebook.tabs():
            self.notebook.select(0)
            self.on_tab_changed(None)

        print("[DEBUG] MainUserWindow.__init__: Initialisierung abgeschlossen.")

    # --- NEUE FUNKTIONEN FÜR TAB-THREADING ---

    def _load_tab_threaded(self, tab_name, TabClass, tab_index):
        """
        Läuft im Hintergrund-Thread.
        Erstellt die Tab-Instanz (der langsame Teil).
        """
        try:
            print(f"[Thread] Lade Tab: {tab_name}...")

            # WICHTIG: Prüfen, welches Argument die Tab-Klasse erwartet
            # (self = MainUserWindow, self.user_data = dict)
            if tab_name in ["Schichtplan", "Chat", "Bug-Reports", "Mein Urlaub"]:
                real_tab = TabClass(self.notebook, self)
            else:
                # Fallback für Tabs, die nur user_data erwarten (wie MyRequestsTab)
                try:
                    real_tab = TabClass(self.notebook, self.user_data)
                except TypeError:
                    print(f"[FEHLER] Fallback-Instanziierung für {tab_name} fehlgeschlagen. Versuche mit 'self'.")
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
            result = self.tab_load_queue.get_nowait()
            tab_name, real_tab, tab_index = result

            print(f"[GUI-Checker] Empfange Ergebnis für: {tab_name}")

            placeholder_frame = self.tab_frames[tab_name]

            if isinstance(real_tab, Exception):
                ttk.Label(placeholder_frame,
                          text=f"Fehler beim Laden:\n{real_tab}",
                          font=("Segoe UI", 12), foreground="red").pack(expand=True, anchor="center")
                for widget in placeholder_frame.winfo_children():
                    if isinstance(widget, ttk.Label) and "Lade" in widget.cget("text"):
                        widget.destroy()
                self.loading_tabs.remove(tab_name)
            else:
                tab_options = self.notebook.tab(placeholder_frame)
                self.notebook.forget(placeholder_frame)
                self.notebook.insert(tab_index, real_tab, **tab_options)
                self.notebook.select(real_tab)

                self.loaded_tabs.add(tab_name)
                self.loading_tabs.remove(tab_name)
                self.tab_frames[tab_name] = real_tab
                print(f"[GUI-Checker] Tab '{tab_name}' erfolgreich eingesetzt.")

        except Empty:
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

        # 1. Prüfen, ob der Tab gesperrt ist. Wenn ja, nicht laden.
        if TabLockManager.is_tab_locked(tab_name):
            print(f"[LazyLoad] Tab '{tab_name}' ist gesperrt. Ladevorgang abgebrochen.")
            self.loaded_tabs.add(tab_name)  # Als "geladen" markieren, um es nicht nochmal zu versuchen
            return

        # 2. "Wird geladen..."-Nachricht anzeigen
        ttk.Label(placeholder_frame, text=f"Lade {tab_name}...",
                  font=("Segoe UI", 16)).pack(expand=True, anchor="center")

        # 3. Status auf "lädt" setzen
        self.loading_tabs.add(tab_name)

        # 4. Hintergrund-Thread starten
        threading.Thread(
            target=self._load_tab_threaded,
            args=(tab_name, TabClass, tab_index),
            daemon=True
        ).start()

        # 5. Den Queue-Checker starten (falls er nicht schon läuft)
        if not self.tab_load_checker_running:
            print("[GUI-Checker] Starte Checker-Loop.")
            self.tab_load_checker_running = True
            self.after(100, self._check_tab_load_queue)

    # ----------------------------------------

    def setup_styles(self):
        # ... (unverändert) ...
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
        # ... (unverändert) ...
        log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        self.app.on_app_close()

    def logout(self):
        # ... (unverändert) ...
        log_user_logout(self.user_data['id'], self.user_data['vorname'], self.user_data['name'])
        self.app.on_logout(self)

    def setup_ui(self):
        # ... (unverändert) ...
        header_frame = ttk.Frame(self);
        header_frame.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Button(header_frame, text="Tutorial", command=self.show_tutorial).pack(side="left", padx=(0, 5))
        ttk.Button(header_frame, text="Reiter anpassen", command=self.open_tab_order_window).pack(side="right")
        self.chat_notification_frame = tk.Frame(self, bg='tomato', cursor="hand2")
        self.admin_request_frame = tk.Frame(self, bg='orange', height=40, cursor="hand2")
        self.bug_feedback_frame = tk.Frame(self, bg='deepskyblue', height=40, cursor="hand2")
        self.notebook = ttk.Notebook(self);
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- LAZY LOADING SETUP ---
        self.tab_definitions = {
            "Schichtplan": UserShiftPlanTab,
            "Chat": ChatTab,
            "Meine Anfragen": MyRequestsTab,
            "Mein Urlaub": VacationTab,
            "Bug-Reports": UserBugReportTab
        }
        self.tab_frames = {};
        self.loaded_tabs = set()

        # --- NEU: Threading für Tabs ---
        self.loading_tabs = set()
        self.tab_load_queue = Queue()
        self.tab_load_checker_running = False
        # -------------------------------

        self.setup_lazy_tabs()

    def setup_lazy_tabs(self):
        # ... (unverändert) ...
        print("[DEBUG] setup_lazy_tabs: Erstelle Platzhalter...")
        # Lade die Reihenfolge über den DB-Manager
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

    def run_periodic_checks(self):
        # ... (unverändert) ...
        self.check_all_notifications()
        self.check_for_admin_requests()
        self.check_for_bug_feedback_requests()
        self.check_chat_notifications()
        self.after(60000, self.run_periodic_checks)

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
        # ... (angepasst für Thread-Wartezeit) ...
        self.switch_to_tab("Chat")

        def _select_user_after_load():
            # --- KORREKTUR (Race Condition): Prüfe auf 'loaded_tabs' statt 'loading_tabs' ---
            if "Chat" in self.loaded_tabs and hasattr(self.tab_frames["Chat"], "select_user"):
                print(f"[DEBUG] Chat-Tab ist geladen, rufe select_user({user_id}) auf.")
                self.tab_frames["Chat"].select_user(user_id)

            # --- KORREKTUR: Prüfe, ob der Tab *noch lädt* oder *noch nicht geladen* ist ---
            elif "Chat" in self.loading_tabs or "Chat" not in self.loaded_tabs:
                print("[DEBUG] go_to_chat: Chat-Tab noch nicht geladen, warte 200ms...")
                self.after(200, _select_user_after_load)
            # --- ENDE KORREKTUR ---
            else:
                print(f"[DEBUG] go_to_chat: Konnte Benutzer {user_id} nicht auswählen, Tab-Status unbekannt.")

        _select_user_after_load()

    def switch_to_tab(self, tab_name):
        # ... (unverändert) ...
        if tab_name in self.tab_frames:
            frame = self.tab_frames[tab_name]
            self.notebook.select(frame)
        else:
            print(f"[DEBUG] switch_to_tab: Tab '{tab_name}' nicht in self.tab_frames gefunden.")

    def create_lock_overlay(self, parent_frame):
        # ... (unverändert) ...
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
        # ... (unverändert) ...
        return self.tab_frames.get(tab_name)

    def setup_footer(self):
        # ... (unverändert) ...
        footer_frame = ttk.Frame(self, padding=5);
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def open_bug_report_dialog(self):
        # ... (unverändert) ...
        BugReportDialog(self, self.user_data['id'])

    def show_tutorial(self):
        # ... (unverändert) ...
        TutorialWindow(self);
        mark_tutorial_seen(self.user_data['id']);
        self.user_data['has_seen_tutorial'] = 1

    def open_tab_order_window(self):
        # Ruft TabOrderWindow auf, das nun den DB-Manager verwendet.
        all_tab_names = list(self.tab_definitions.keys());
        TabOrderWindow(self, self.reorder_tabs, all_tab_names)

    def reorder_tabs(self, new_order):
        # ... (unverändert) ...
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

    def check_for_admin_requests(self):
        # ... (unverändert) ...
        for widget in self.admin_request_frame.winfo_children(): widget.destroy()
        count = get_pending_admin_requests_for_user(self.user_data['id'])
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

    def check_for_bug_feedback_requests(self):
        # ... (unverändert) ...
        for widget in self.bug_feedback_frame.winfo_children(): widget.destroy()
        report_ids = get_reports_awaiting_feedback_for_user(self.user_data['id']);
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

    def go_to_shift_plan(self):
        # ... (unverändert) ...
        self.switch_to_tab("Schichtplan")

    def go_to_bug_reports(self, report_id=None):
        # ... (angepasst für Thread-Wartezeit) ...
        self.switch_to_tab("Bug-Reports")

        def _select_report_after_load():
            if "Bug-Reports" in self.loaded_tabs and hasattr(self.tab_frames["Bug-Reports"], "select_report"):
                self.tab_frames["Bug-Reports"].select_report(report_id)
            elif "Bug-Reports" in self.loading_tabs or "Bug-Reports" not in self.loaded_tabs:
                self.after(200, _select_report_after_load)

        if report_id:
            _select_report_after_load()

    def check_all_notifications(self):
        # ... (unverändert, nutzt sicheren Zugriff auf self.loaded_tabs) ...
        all_messages = [];
        tabs_to_refresh = []
        unnotified_requests = get_unnotified_requests(self.user_data['id'])
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
        unnotified_vacation = get_unnotified_vacation_requests_for_user(self.user_data['id'])
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
        unnotified_reports = get_unnotified_bug_reports_for_user(self.user_data['id'])
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

    # --- Datenladefunktionen (bleiben gleich) ---
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

    def load_shift_types(self):
        # ... (unverändert) ...
        self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}

    def get_contrast_color(self, hex_color):
        # ... (unverändert) ...
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def load_staffing_rules(self):
        # ... (unverändert) ...
        rules = load_config_json('MIN_STAFFING_RULES');
        return rules if rules and 'Colors' in rules else DEFAULT_RULES

    def load_shift_frequency(self):
        # ... (unverändert) ...
        freq_data = load_shift_frequency()
        return freq_data if freq_data else {}

    def save_shift_frequency(self):
        # ... (unverändert) ...
        pass