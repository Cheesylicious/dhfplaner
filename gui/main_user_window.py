# gui/main_user_window.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
from datetime import date, datetime, timedelta
import calendar

from .tabs.user_shift_plan_tab import UserShiftPlanTab
from .tabs.vacation_tab import VacationTab
from .tabs.my_requests_tab import MyRequestsTab
from .tabs.user_bug_report_tab import UserBugReportTab
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
from database.db_users import mark_tutorial_seen
from .tab_lock_manager import TabLockManager
from database.db_core import load_config_json

USER_TAB_ORDER_FILE = 'user_tab_order_config.json'
DEFAULT_RULES = {"Daily": {}, "Sa-So": {}, "Fr": {}, "Mo-Do": {}, "Holiday": {}, "Colors": {}}


class TabOrderManager:
    DEFAULT_ORDER = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports"]

    @staticmethod
    def load_order():
        if not os.path.exists(USER_TAB_ORDER_FILE):
            TabOrderManager.save_order(TabOrderManager.DEFAULT_ORDER)
            return TabOrderManager.DEFAULT_ORDER
        try:
            with open(USER_TAB_ORDER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return TabOrderManager.DEFAULT_ORDER

    @staticmethod
    def save_order(order_list):
        try:
            with open(USER_TAB_ORDER_FILE, 'w', encoding='utf-8') as f:
                json.dump(order_list, f, indent=4)
            return True
        except IOError:
            return False


class TabOrderWindow(tk.Toplevel):
    def __init__(self, master, callback, all_tab_names):
        super().__init__(master)
        self.callback = callback
        self.title("Reiter-Reihenfolge anpassen")
        self.geometry("400x500")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        ttk.Label(main_frame, text="Ändern Sie die Reihenfolge der Reiter im Hauptfenster.").pack(anchor="w",
                                                                                                  pady=(0, 10))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.tab_listbox = tk.Listbox(list_frame, selectmode="single")
        self.tab_listbox.grid(row=0, column=0, sticky="nsew")

        button_subframe = ttk.Frame(list_frame)
        button_subframe.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        ttk.Button(button_subframe, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(pady=2, fill="x")
        ttk.Button(button_subframe, text="↓ Runter", command=lambda: self.move_item(1)).pack(pady=2, fill="x")

        saved_order = TabOrderManager.load_order()
        final_display_order = []
        for tab_name in saved_order:
            if tab_name in all_tab_names:
                final_display_order.append(tab_name)
        for tab_name in all_tab_names:
            if tab_name not in final_display_order:
                final_display_order.append(tab_name)

        for tab_name in final_display_order:
            self.tab_listbox.insert(tk.END, tab_name)

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(15, 0))
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Speichern & Schließen", command=self.save_and_close).grid(row=0, column=0,
                                                                                               sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def move_item(self, direction):
        selection = self.tab_listbox.curselection()
        if not selection: return
        idx = selection[0]
        new_idx = idx + direction
        if not (0 <= new_idx < self.tab_listbox.size()): return
        item_text = self.tab_listbox.get(idx)
        self.tab_listbox.delete(idx)
        self.tab_listbox.insert(new_idx, item_text)
        self.tab_listbox.selection_set(new_idx)
        self.tab_listbox.activate(new_idx)

    def save_and_close(self):
        new_order = list(self.tab_listbox.get(0, tk.END))
        if TabOrderManager.save_order(new_order):
            messagebox.showinfo("Gespeichert", "Die Reiter-Reihenfolge wurde aktualisiert.", parent=self)
            self.callback(new_order)
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Die Reihenfolge konnte nicht gespeichert werden.", parent=self)


class MainUserWindow(tk.Toplevel):
    def __init__(self, master, user_data, app):
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
        self.shift_types_data = {}
        self.staffing_rules = self.load_staffing_rules()
        self.current_year_holidays = {}
        self.events = {}
        self.shift_frequency = self.load_shift_frequency()
        self.load_shift_types()
        self._load_holidays_for_year(self.current_display_date.year)
        self._load_events_for_year(self.current_display_date.year)
        self.setup_ui()
        self.setup_footer()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(500, self.run_periodic_checks)
        if not self.user_data.get('has_seen_tutorial'):
            self.show_tutorial()

    def setup_styles(self):
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
        self.app.on_app_close()

    def logout(self):
        self.app.on_logout(self)

    def setup_ui(self):
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Button(header_frame, text="Tutorial", command=self.show_tutorial).pack(side="left", padx=(0, 5))
        ttk.Button(header_frame, text="Reiter anpassen", command=self.open_tab_order_window).pack(side="right")
        self.admin_request_frame = tk.Frame(self, bg='orange', height=40, cursor="hand2")
        self.bug_feedback_frame = tk.Frame(self, bg='deepskyblue', height=40, cursor="hand2")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_frames = {}
        self.setup_tabs()

    def setup_tabs(self):
        self.tab_frames = {
            "Schichtplan": UserShiftPlanTab(self.notebook, self),
            "Meine Anfragen": MyRequestsTab(self.notebook, self.user_data),
            "Mein Urlaub": VacationTab(self.notebook, self.user_data),
            "Bug-Reports": UserBugReportTab(self.notebook, self)
        }
        saved_order = TabOrderManager.load_order()
        final_order = [tab for tab in saved_order if tab in self.tab_frames]
        final_order.extend([tab for tab in self.tab_frames if tab not in final_order])
        for tab_name in final_order:
            frame = self.tab_frames.get(tab_name)
            if frame:
                self.notebook.add(frame, text=tab_name)
                if TabLockManager.is_tab_locked(tab_name):
                    self.create_lock_overlay(frame)

    def create_lock_overlay(self, parent_frame):
        overlay = tk.Frame(parent_frame, bg='gray90', relief='raised', borderwidth=2)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1, anchor='nw')
        msg_frame = ttk.Frame(overlay, style="Overlay.TFrame")
        msg_frame.place(relx=0.5, rely=0.5, anchor='center')
        style = ttk.Style()
        style.configure("Overlay.TFrame", background='gray90')
        ttk.Label(msg_frame, text="🔧", font=('Segoe UI', 48, 'bold'), background='gray90', foreground='gray60').pack(
            pady=10)
        ttk.Label(msg_frame, text="Wartungsarbeiten", font=('Segoe UI', 22, 'bold'), background='gray90',
                  foreground='gray60').pack(pady=5)
        ttk.Label(msg_frame, text="Dieser Bereich wird gerade überarbeitet und ist in Kürze wieder verfügbar.",
                  font=('Segoe UI', 12), background='gray90', foreground='gray60').pack(pady=10)
        overlay.bind("<Button-1>", lambda e: "break")
        overlay.bind("<B1-Motion>", lambda e: "break")

    def get_tab(self, tab_name):
        return self.tab_frames.get(tab_name)

    def setup_footer(self):
        footer_frame = ttk.Frame(self, padding=5)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Button(footer_frame, text="Abmelden", command=self.logout, style='Logout.TButton').pack(side="left",
                                                                                                    padx=10, pady=5)
        ttk.Button(footer_frame, text="Bug / Fehler melden", command=self.open_bug_report_dialog,
                   style='Bug.TButton').pack(side="right", padx=10, pady=5)

    def open_bug_report_dialog(self):
        BugReportDialog(self, self.user_data['id'])

    def show_tutorial(self):
        TutorialWindow(self)
        mark_tutorial_seen(self.user_data['id'])
        self.user_data['has_seen_tutorial'] = 1

    def open_tab_order_window(self):
        all_tab_names = list(self.tab_frames.keys())
        TabOrderWindow(self, self.reorder_tabs, all_tab_names)

    def reorder_tabs(self, new_order):
        try:
            selected_tab_name = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            selected_tab_name = None
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)
        for tab_name in new_order:
            frame = self.tab_frames.get(tab_name)
            if frame:
                self.notebook.add(frame, text=tab_name)
        if selected_tab_name in new_order:
            for i, tab in enumerate(self.notebook.tabs()):
                if self.notebook.tab(tab, "text") == selected_tab_name:
                    self.notebook.select(i)
                    break
        elif self.notebook.tabs():
            self.notebook.select(0)

    def run_periodic_checks(self):
        self.check_all_notifications()
        self.check_for_admin_requests()
        self.check_for_bug_feedback_requests()
        self.after(60000, self.run_periodic_checks)

    def check_for_admin_requests(self):
        for widget in self.admin_request_frame.winfo_children():
            widget.destroy()
        count = get_pending_admin_requests_for_user(self.user_data['id'])
        if count > 0:
            self.admin_request_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)
            label_text = f"Sie haben {count} offene Schichtanfrage vom Admin!" if count > 1 else "Sie haben 1 offene Schichtanfrage vom Admin!"

            action = lambda event=None: self.go_to_shift_plan()

            notification_label = tk.Label(self.admin_request_frame, text=label_text, bg='orange', fg='black',
                                          font=('Segoe UI', 12, 'bold'), cursor="hand2")
            notification_label.pack(side='left', padx=15, pady=5)
            notification_label.bind("<Button-1>", action)
            self.admin_request_frame.bind("<Button-1>", action)

            show_button = ttk.Button(self.admin_request_frame, text="Anzeigen", command=action)
            show_button.pack(side='right', padx=15)
        else:
            self.admin_request_frame.pack_forget()

    def check_for_bug_feedback_requests(self):
        for widget in self.bug_feedback_frame.winfo_children():
            widget.destroy()

        report_ids = get_reports_awaiting_feedback_for_user(self.user_data['id'])
        count = len(report_ids)

        if count > 0:
            first_report_id = report_ids[0]
            action = lambda event=None: self.go_to_bug_reports(first_report_id)

            self.bug_feedback_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)
            self.bug_feedback_frame.bind("<Button-1>", action)

            label_text = f"Deine Rückmeldung wird für {count} Bug-Report(s) benötigt!"
            notification_label = tk.Label(self.bug_feedback_frame, text=label_text, bg='deepskyblue', fg='white',
                                          font=('Segoe UI', 12, 'bold'), cursor="hand2")
            notification_label.pack(side='left', padx=15, pady=5)
            notification_label.bind("<Button-1>", action)

            show_button = ttk.Button(self.bug_feedback_frame, text="Anzeigen", command=action)
            show_button.pack(side='right', padx=15)
        else:
            self.bug_feedback_frame.pack_forget()

    def go_to_shift_plan(self):
        for i, tab in enumerate(self.notebook.tabs()):
            if self.notebook.tab(tab, "text") == "Schichtplan":
                self.notebook.select(i)
                break

    def go_to_bug_reports(self, report_id=None):
        for i, tab in enumerate(self.notebook.tabs()):
            if "Bug-Reports" in self.notebook.tab(tab, "text"):
                self.notebook.select(i)
                if report_id and "Bug-Reports" in self.tab_frames:
                    self.after(100, lambda: self.tab_frames["Bug-Reports"].select_report(report_id))
                break

    def check_all_notifications(self):
        all_messages = []
        tabs_to_refresh = []
        unnotified_requests = get_unnotified_requests(self.user_data['id'])
        if unnotified_requests:
            message_lines = ["Sie haben Neuigkeiten zu Ihren 'Wunschfrei'-Anträgen:"]
            notified_ids = [req['id'] for req in unnotified_requests]
            for req in unnotified_requests:
                req_date = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
                status_line = f"- Ihr Antrag für den {req_date} wurde {req['status']}."
                if req['status'] == 'Abgelehnt' and req.get('rejection_reason'):
                    status_line += f" Grund: {req['rejection_reason']}"
                message_lines.append(status_line)
            all_messages.append("\n".join(message_lines))
            mark_requests_as_notified(notified_ids)
            tabs_to_refresh.append("Meine Anfragen")
        unnotified_vacation = get_unnotified_vacation_requests_for_user(self.user_data['id'])
        if unnotified_vacation:
            message_lines = ["Es gibt Neuigkeiten zu Ihren Urlaubsanträgen:"]
            notified_ids = [req['id'] for req in unnotified_vacation]
            for req in unnotified_vacation:
                start = datetime.strptime(req['start_date'], '%Y-%m-%d').strftime('%d.%m')
                end = datetime.strptime(req['end_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
                message_lines.append(f"- Ihr Urlaub von {start} bis {end} wurde {req['status']}.")
            all_messages.append("\n".join(message_lines))
            mark_vacation_requests_as_notified(notified_ids)
            tabs_to_refresh.append("Mein Urlaub")
        unnotified_reports = get_unnotified_bug_reports_for_user(self.user_data['id'])
        if unnotified_reports:
            message_lines = ["Es gibt Neuigkeiten zu Ihren Fehlerberichten:"]
            notified_ids = [report['id'] for report in unnotified_reports]
            for report in unnotified_reports:
                title = report['title']
                status = report['status']
                message_lines.append(f"- Ihr Bericht '{title[:30]}...' hat jetzt den Status: {status}.")
            all_messages.append("\n".join(message_lines))
            mark_bug_reports_as_notified(notified_ids)
            tabs_to_refresh.append("Bug-Reports")
        if all_messages and self.show_request_popups:
            messagebox.showinfo("Benachrichtigungen", "\n\n".join(all_messages), parent=self)
            if self.winfo_exists():
                if "Meine Anfragen" in tabs_to_refresh and "Meine Anfragen" in self.tab_frames:
                    self.tab_frames["Meine Anfragen"].refresh_data()
                if "Mein Urlaub" in tabs_to_refresh and "Mein Urlaub" in self.tab_frames:
                    self.tab_frames["Mein Urlaub"].refresh_data()
                if "Bug-Reports" in tabs_to_refresh and "Bug-Reports" in self.tab_frames:
                    # Die Methode heißt load_reports im user_bug_report_tab
                    if hasattr(self.tab_frames["Bug-Reports"], 'load_reports'):
                        self.tab_frames["Bug-Reports"].load_reports()

    def _load_holidays_for_year(self, year):
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def _load_events_for_year(self, year):
        self.events = EventManager.get_events_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def get_event_type(self, current_date):
        return EventManager.get_event_type(current_date, self.events)

    def load_shift_types(self):
        self.shift_types_data = {st['abbreviation']: st for st in get_all_shift_types()}

    def get_contrast_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7: return 'black'
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            y = (r * 299 + g * 587 + b * 114) / 1000
            return 'black' if y >= 128 else 'white'
        except ValueError:
            return 'black'

    def load_staffing_rules(self):
        rules = load_config_json('MIN_STAFFING_RULES')
        return rules if rules and 'Colors' in rules else DEFAULT_RULES

    def load_shift_frequency(self):
        try:
            with open('shift_frequency.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_shift_frequency(self):
        try:
            with open('shift_frequency.json', 'w') as f:
                json.dump(self.shift_frequency, f, indent=4)
        except IOError:
            messagebox.showwarning("Speicherfehler", "Die Schichthäufigkeit konnte nicht gespeichert werden.",
                                   parent=self)