# gui/main_user_window.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
from datetime import date, datetime

from .tabs.user_shift_plan_tab import UserShiftPlanTab
from .tabs.vacation_tab import VacationTab
from .tabs.my_requests_tab import MyRequestsTab
from .tabs.user_bug_report_tab import UserBugReportTab
from .dialogs.bug_report_dialog import BugReportDialog
from .dialogs.tutorial_window import TutorialWindow
from .holiday_manager import HolidayManager
from database.db_manager import (
    get_all_shift_types, get_unnotified_requests, mark_requests_as_notified,
    get_unnotified_bug_reports_for_user, mark_bug_reports_as_notified
)

USER_TAB_ORDER_FILE = 'user_tab_order_config.json'
STAFFING_RULES_FILE = 'min_staffing_rules.json'
DEFAULT_RULES = {"Colors": {}}


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
    def __init__(self, master, callback):
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

        current_order = TabOrderManager.load_order()
        for tab_name in current_order:
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
    def __init__(self, master, user_data):
        super().__init__(master)
        self.master = master
        self.user_data = user_data

        full_name = f"{self.user_data['vorname']} {self.user_data['name']}".strip()
        self.title(f"Planer - Angemeldet als {full_name}")
        self.attributes('-fullscreen', True)

        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        style.configure('Bug.TButton', background='dodgerblue', foreground='white', font=('Segoe UI', 9, 'bold'))
        style.map('Bug.TButton',
                  background=[('active', '#0056b3')],
                  foreground=[('active', 'white')])

        style.configure('Logout.TButton', background='gold', foreground='black', font=('Segoe UI', 10, 'bold'),
                        padding=6)
        style.map('Logout.TButton',
                  background=[('active', 'goldenrod')],
                  foreground=[('active', 'black')])

        self.current_display_date = date.today()
        self.shift_types_data = {}
        self.staffing_rules = self.load_staffing_rules()
        self.current_year_holidays = {}
        self.load_shift_types()
        self._load_holidays_for_year(self.current_display_date.year)

        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=10, pady=(5, 0))

        ttk.Button(header_frame, text="Tutorial", command=self.show_tutorial).pack(side="left", padx=(0, 5))

        ttk.Button(header_frame, text="Reiter anpassen", command=self.open_tab_order_window).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_frames = {}
        self.setup_tabs()
        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.master.on_app_close)
        self.after(100, self.check_for_wunschfrei_notifications)
        self.after(200, self.check_for_bug_report_notifications)

    def setup_tabs(self):
        self.tab_frames = {
            "Schichtplan": UserShiftPlanTab(self.notebook, self),
            "Meine Anfragen": MyRequestsTab(self.notebook, self),
            "Mein Urlaub": VacationTab(self.notebook, self),
            "Bug-Reports": UserBugReportTab(self.notebook, self)
        }
        saved_order = TabOrderManager.load_order()
        final_order = []
        existing_tabs = list(self.tab_frames.keys())
        for tab_name in saved_order:
            if tab_name in existing_tabs:
                final_order.append(tab_name)
                existing_tabs.remove(tab_name)
        final_order.extend(existing_tabs)
        for tab_name in final_order:
            frame = self.tab_frames.get(tab_name)
            if frame:
                self.notebook.add(frame, text=tab_name)

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

    def logout(self):
        self.withdraw()
        self.master.login_window.clear_input_fields()
        self.master.login_window.deiconify()

    def open_tab_order_window(self):
        TabOrderWindow(self, self.reorder_tabs)

    def reorder_tabs(self, new_order):
        try:
            selected_tab_name = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            selected_tab_name = None
        all_tabs = {self.notebook.tab(tab_id, "text"): self.notebook.nametowidget(tab_id) for tab_id in
                    self.notebook.tabs()}
        for tab_id in list(self.notebook.tabs()):
            self.notebook.forget(tab_id)
        for tab_name in new_order:
            if tab_name in all_tabs:
                self.notebook.add(all_tabs[tab_name], text=tab_name)
        if selected_tab_name in new_order:
            self.notebook.select(new_order.index(selected_tab_name))

    def check_for_bug_report_notifications(self):
        unnotified_reports = get_unnotified_bug_reports_for_user(self.user_data['id'])
        if not unnotified_reports: return
        message_lines = ["Es gibt Neuigkeiten zu Ihren Fehlerberichten:"]
        notified_ids = [report['id'] for report in unnotified_reports]
        for report in unnotified_reports:
            title = report['title']
            status = report['status']
            message_lines.append(f"- Ihr Bericht '{title[:30]}...' hat jetzt den Status: {status}.")
        messagebox.showinfo("Status-Update für Fehlerberichte", "\n".join(message_lines), parent=self)
        mark_bug_reports_as_notified(notified_ids)

    def check_for_wunschfrei_notifications(self):
        unnotified = get_unnotified_requests(self.user_data['id'])
        if not unnotified: return
        message_lines = ["Sie haben Neuigkeiten zu Ihren 'Wunschfrei'-Anträgen:"]
        notified_ids = [req['id'] for req in unnotified]
        for req in unnotified:
            req_date = datetime.strptime(req['request_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            status_line = f"- Ihr Antrag für den {req_date} wurde {req['status']}."
            if req['status'] == 'Abgelehnt' and req.get('rejection_reason'):
                status_line += f" Grund: {req['rejection_reason']}"
            message_lines.append(status_line)
        messagebox.showinfo("Benachrichtigung", "\n".join(message_lines), parent=self)
        mark_requests_as_notified(notified_ids)

    def _load_holidays_for_year(self, year):
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

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
        if os.path.exists(STAFFING_RULES_FILE):
            try:
                with open(STAFFING_RULES_FILE, 'r') as f:
                    rules = json.load(f)
                    if 'Colors' not in rules:
                        rules['Colors'] = DEFAULT_RULES['Colors']
                    return rules
            except json.JSONDecodeError:
                return DEFAULT_RULES
        return DEFAULT_RULES