# gui/main_admin_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta, datetime  # NEU: datetime importieren
import calendar
from collections import defaultdict

# --- KEIN THREADING ---

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
# SettingsTab Import entfernt

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
    run_db_update_add_archived_date  # NEUER IMPORT
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
            "Wunschanfragen": RequestsTab,
            "Urlaubsanträge": VacationRequestsTab,
            "Bug-Reports": BugReportsTab,
            "Logs": LogTab,
            "Protokoll": ProtokollTab,
            "Dummy": None

        }

        self.tab_frames = {}
        self.loaded_tabs = set()
        self.loading_tabs = set()  # Für Re-Entrancy-Schutz

        self.setup_lazy_tabs()
        print("[DEBUG] MainAdminWindow.__init__: Lazy Tabs (Platzhalter) erstellt.")


        self.setup_footer()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.after(1000, self.check_for_updates)
        self.after(2000, self.check_chat_notifications)

        if self.notebook.tabs():
            first_tab_name = list(self.tab_definitions.keys())[0]
            self._load_tab_directly(first_tab_name, 0)

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        print("[DEBUG] MainAdminWindow.__init__: Initialisierung abgeschlossen.")


    # --- Restliche Methoden (__init__ bis _load_dynamic_tab) bleiben unverändert ---
    def _load_tab_directly(self, tab_name, tab_index):
        # ... (unverändert) ...
        if tab_name in self.loaded_tabs or tab_name in self.loading_tabs: return
        if tab_name not in self.tab_definitions:
            print(f"[GUI - direct load] FEHLER: Tab '{tab_name}' nicht definiert.")
            return
        self.loading_tabs.add(tab_name)
        print(f"[GUI - direct load] Lade initialen Tab: {tab_name}")
        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames[tab_name]
        loading_label = ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16),
                                  name="loading_label")
        loading_label.pack(expand=True, anchor="center")
        self.update_idletasks()
        real_tab, tab_options = None, None
        try:
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            else:
                try:
                    real_tab = TabClass(self.notebook, self)
                except Exception as e1:
                    print(
                        f"[GUI - direct load] Warnung: {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:
                        real_tab = TabClass(self.notebook)
                    except Exception as e2:
                        print(f"[GUI - direct load] FEHLER: {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise Exception(f"Fehler bei (master, self): {e1}\nFehler bei (master): {e2}")
            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)
                self.notebook.forget(placeholder_frame)
                self.notebook.insert(tab_index, real_tab, **tab_options)
                self.notebook.select(real_tab)
                placeholder_frame.destroy()
                self.loaded_tabs.add(tab_name)
                self.tab_frames[tab_name] = real_tab
                print(f"[GUI - direct load] Tab '{tab_name}' erfolgreich eingesetzt.")
            else:
                raise tk.TclError(f"Platzhalter für {tab_name} (initial) existierte nicht mehr.")
        except Exception as e:
            print(f"[GUI - direct load] FEHLER beim Laden von initialem Tab '{tab_name}': {e}")
            if placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
        finally:
            if tab_name in self.loading_tabs: self.loading_tabs.remove(tab_name)

    def on_tab_changed(self, event):
        # ... (unverändert) ...
        try:
            tab_id = self.notebook.select()
            if not tab_id: return
            tab_index = self.notebook.index(tab_id)
            tab_name_with_count = self.notebook.tab(tab_index, "text")
            tab_name = tab_name_with_count.split(" (")[0]
        except (tk.TclError, IndexError):
            print("[GUI] Fehler beim Ermitteln des Tabs in on_tab_changed.")
            return
        if tab_name in self.loaded_tabs: return
        if tab_name in self.loading_tabs:
            print(f"[GUI] WARNUNG: {tab_name} lädt bereits. Breche (doppelten) Ladevorgang ab.")
            return
        if tab_name not in self.tab_definitions: return
        self.loading_tabs.add(tab_name)
        print(f"[GUI] on_tab_changed: Starte Ladevorgang für {tab_name} (im GUI-Thread)")
        TabClass = self.tab_definitions[tab_name]
        placeholder_frame = self.tab_frames.get(tab_name)
        if not placeholder_frame or not placeholder_frame.winfo_exists():
            print(f"[GUI] FEHLER: Platzhalter-Frame für '{tab_name}' nicht gefunden oder bereits zerstört.")
            if tab_name in self.loading_tabs: self.loading_tabs.remove(tab_name)
            return
        for widget in placeholder_frame.winfo_children(): widget.destroy()
        loading_label = ttk.Label(placeholder_frame, text=f"Lade {tab_name}...", font=("Segoe UI", 16),
                                  name="loading_label")
        loading_label.pack(expand=True, anchor="center")
        self.update_idletasks()
        real_tab, tab_options = None, None
        try:
            if TabClass.__name__ == "UserTabSettingsTab":
                all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen",
                                      "Chat"]
                real_tab = TabClass(self.notebook, all_user_tab_names)
            else:
                try:
                    real_tab = TabClass(self.notebook, self)
                    print(f"[GUI] {tab_name} erfolgreich mit (master, admin_window) geladen.")
                except Exception as e1:
                    print(
                        f"[GUI] Warnung: Konstruktor für {tab_name} mit (master, admin_window) fehlgeschlagen: {e1}. Versuche (master)...")
                    try:
                        real_tab = TabClass(self.notebook)
                        print(f"[GUI] {tab_name} erfolgreich mit (master) geladen.")
                    except Exception as e2:
                        print(f"[GUI] FEHLER: Konstruktor für {tab_name} auch mit (master) fehlgeschlagen: {e2}")
                        raise Exception(f"Fehler bei (master, self): {e1}\nFehler bei (master): {e2}")
            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)
            else:
                raise tk.TclError(f"Platzhalter für {tab_name} existierte nicht mehr vor dem Holen der Optionen.")
            if real_tab and tab_options:
                try:
                    self.notebook.unbind("<<NotebookTabChanged>>")
                    self.notebook.forget(placeholder_frame)
                    self.notebook.insert(tab_index, real_tab, **tab_options)
                    self.notebook.select(real_tab)
                    placeholder_frame.destroy()
                finally:
                    self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
                self.loaded_tabs.add(tab_name)
                self.tab_frames[tab_name] = real_tab
                print(f"[GUI] Tab '{tab_name}' erfolgreich eingesetzt.")
            else:
                raise Exception("Tab-Objekt oder Tab-Optionen konnten nicht ermittelt werden.")
        except Exception as e:
            print(f"[GUI] FEHLER beim Laden von Tab '{tab_name}': {e}")
            if placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
            else:
                print(f"[GUI] FEHLER: Platzhalter für {tab_name} existierte nicht mehr bei Fehlerbehandlung.")
        finally:
            if tab_name in self.loading_tabs: self.loading_tabs.remove(tab_name)

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
        # ... (unverändert) ...
        print("[DEBUG] setup_lazy_tabs: Erstelle Platzhalter...")
        for tab_name in self.tab_definitions.keys():
            placeholder_frame = ttk.Frame(self.notebook, padding=20)
            self.notebook.add(placeholder_frame, text=tab_name)
            self.tab_frames[tab_name] = placeholder_frame

            # --- NEU: Prüfen, ob es der Dummy-Tab ist und ihn deaktivieren ---
            if tab_name == "Dummy":
                try:
                    # Setze den Status des gerade hinzugefügten Tabs auf 'disabled'
                    self.notebook.tab(placeholder_frame, state='disabled')
                    print(f"[DEBUG] setup_lazy_tabs: Tab '{tab_name}' deaktiviert.")
                except tk.TclError:
                    # Fallback, falls der Frame aus irgendeinem Grund nicht gefunden wird
                    print(f"[FEHLER] setup_lazy_tabs: Konnte Tab '{tab_name}' nicht deaktivieren.")
            # --- ENDE NEU ---

        self.update_tab_titles()

    def update_single_tab_text(self, tab_name, new_text):
        # ... (unverändert) ...
        frame = self.tab_frames.get(tab_name)
        if frame:
            try:
                parent_notebook = self.notebook.nametowidget(frame.winfo_parent())
                if frame.winfo_exists() and parent_notebook == self.notebook:
                    self.notebook.tab(frame, text=new_text)
            except (tk.TclError, KeyError):
                print(f"[DEBUG] Fehler beim Aktualisieren des Tab-Titels für {tab_name} (Widget ungültig/zerstört)")

    def update_tab_titles(self):
        # ... (unverändert) ...
        pending_wunsch_count = len(get_pending_wunschfrei_requests())
        tab_text_wunsch = "Wunschanfragen";
        if pending_wunsch_count > 0: tab_text_wunsch += f" ({pending_wunsch_count})"
        self.update_single_tab_text("Wunschanfragen", tab_text_wunsch)
        pending_urlaub_count = get_pending_vacation_requests_count()
        tab_text_urlaub = "Urlaubsanträge";
        if pending_urlaub_count > 0: tab_text_urlaub += f" ({pending_urlaub_count})"
        self.update_single_tab_text("Urlaubsanträge", tab_text_urlaub)
        open_bug_count = get_open_bug_reports_count()
        tab_text_bugs = "Bug-Reports";
        if open_bug_count > 0: tab_text_bugs += f" ({open_bug_count})"
        self.update_single_tab_text("Bug-Reports", tab_text_bugs)

    def switch_to_tab(self, tab_name):
        # ... (unverändert) ...
        frame = self.tab_frames.get(tab_name)
        if frame and frame.winfo_exists():
            try:
                if self.notebook.nametowidget(frame.winfo_parent()) == self.notebook:
                    self.notebook.select(frame)
                else:
                    print(f"[DEBUG] switch_to_tab: Frame für '{tab_name}' ist kein Tab mehr.")
            except (tk.TclError, KeyError):
                print(f"[DEBUG] switch_to_tab: Fehler beim Auswählen von '{tab_name}' (Widget ungültig).")
        else:
            print(f"[DEBUG] switch_to_tab: Tab/Frame '{tab_name}' nicht gefunden oder zerstört.")

    def _load_dynamic_tab(self, tab_name, TabClass, *args):
        # ... (unverändert) ...
        if tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists(): self.notebook.select(frame)
            return
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
        real_tab, tab_options = None, None
        try:
            real_tab = TabClass(self.notebook, *args)
            if placeholder_frame.winfo_exists():
                tab_options = self.notebook.tab(placeholder_frame)
            else:
                raise tk.TclError(f"Platzhalter für dyn. Tab {tab_name} existierte nicht mehr vor Optionen.")
            if real_tab and tab_options and tab_index != -1:
                try:
                    self.notebook.unbind("<<NotebookTabChanged>>")
                    self.notebook.forget(placeholder_frame)
                    self.notebook.insert(tab_index, real_tab, **tab_options)
                    self.notebook.select(real_tab)
                    placeholder_frame.destroy()
                finally:
                    self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
                self.loaded_tabs.add(tab_name)
                self.tab_frames[tab_name] = real_tab
                print(f"[GUI] Dynamischer Tab '{tab_name}' erfolgreich eingesetzt.")
            else:
                raise Exception("Dyn. Tab-Objekt, Optionen oder Index konnten nicht ermittelt werden.")
        except Exception as e:
            print(f"[GUI] FEHLER beim Laden/Einfügen von dynamischem Tab '{tab_name}': {e}")
            if placeholder_frame.winfo_exists():
                for widget in placeholder_frame.winfo_children(): widget.destroy()
                ttk.Label(placeholder_frame, text=f"Fehler beim Laden:\n{e}", font=("Segoe UI", 12),
                          foreground="red").pack(expand=True, anchor="center")
            else:
                print(
                    f"[GUI] FEHLER: Platzhalter für {tab_name} existierte nicht mehr bei Fehlerbehandlung (dyn. Tab).")
        finally:
            if tab_name in self.loading_tabs: self.loading_tabs.remove(tab_name)

    def open_request_lock_window(self):
        self._load_dynamic_tab("Antragssperre", RequestLockTab, self)

    def open_user_tab_settings(self):
        all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen", "Chat"]
        self._load_dynamic_tab("Benutzer-Reiter", UserTabSettingsTab, all_user_tab_names)

    def open_password_resets_window(self):
        self._load_dynamic_tab("Passwort-Resets", PasswordResetRequestsWindow, self)

    def open_shift_types_window(self):
        # ... (unverändert) ...
        print("[DEBUG] Öffne Schichtarten-Dialog...")
        try:
            from .dialogs.shift_type_dialog import ShiftTypeDialog
            ShiftTypeDialog(self, self.refresh_all_tabs)
        except ImportError:
            print("[FEHLER] ShiftTypeDialog nicht gefunden, versuche 'alten' ShiftTypesTab als Dialog")
            try:
                from .tabs.shift_types_tab import ShiftTypesTab
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
        self.notification_frame = ttk.Frame(self.header_frame)
        self.notification_frame.pack(side="left", fill="x", expand=True)
        settings_menubutton = ttk.Menubutton(self.header_frame, text="⚙️ Einstellungen", style='Settings.TMenubutton')
        settings_menubutton.pack(side="right", padx=5)
        settings_menu = tk.Menu(settings_menubutton, tearoff=0)
        settings_menubutton["menu"] = settings_menu

        # --- Standard Menüpunkte ---
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

        # --- Datenbank Updates / Fixes ---
        settings_menu.add_separator()
        db_menu = tk.Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="Datenbank Wartung", menu=db_menu)
        db_menu.add_command(label="⚠️ FIX: ALLE ALTEN USER FREISCHALTEN", command=self.apply_all_users_approval_fix)
        db_menu.add_separator()
        db_menu.add_command(label="Update: Freischaltung Spalte ('is_approved')", command=self.apply_is_approved_fix)
        db_menu.add_command(label="Update: Archivierung Spalte ('is_archived')", command=self.apply_is_archived_fix)
        # NEUER EINTRAG HIER
        db_menu.add_command(label="Update: Archivierungsdatum Spalte ('archived_date')",
                            command=self.apply_archived_date_fix)
        db_menu.add_separator()
        db_menu.add_command(label="Update für Chat ausführen", command=self.apply_database_fix)

    # NEUE FUNKTION
    def apply_archived_date_fix(self):
        """Fügt die 'archived_date' Spalte zur Users-Tabelle hinzu."""
        if messagebox.askyesno("Bestätigung",
                               "Dies fügt die Spalte 'archived_date' zur Benutzer-Tabelle hinzu, um das Archivierungsdatum zu speichern. Fortfahren?",
                               parent=self):
            success, message = run_db_update_add_archived_date()
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def apply_is_archived_fix(self):
        # ... (unverändert) ...
        if messagebox.askyesno("Bestätigung",
                               "Dies fügt die Spalte 'is_archived' zur Benutzer-Tabelle hinzu, um Mitarbeiter zu archivieren. Fortfahren?",
                               parent=self):
            success, message = run_db_update_add_is_archived()
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def apply_all_users_approval_fix(self):
        # ... (unverändert) ...
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
        # ... (unverändert) ...
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
        for widget in self.chat_notification_frame.winfo_children(): widget.destroy()
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
            notification_label.pack(side='left', padx=15, pady=5);
            notification_label.bind("<Button-1>", action)
            show_button = ttk.Button(self.chat_notification_frame, text="Anzeigen", command=action)
            show_button.pack(side='right', padx=15)
        else:
            self.chat_notification_frame.pack_forget()
        self.after(10000, self.check_chat_notifications)

    def go_to_chat(self, user_id):
        # ... (unverändert) ...
        self.switch_to_tab("Chat")
        if "Chat" in self.loaded_tabs and hasattr(self.tab_frames["Chat"], "select_user"):
            if self.tab_frames["Chat"].winfo_exists():
                self.tab_frames["Chat"].select_user(user_id)
            else:
                print("[DEBUG] go_to_chat: Chat-Tab existiert nicht mehr.")
        else:
            print("[DEBUG] go_to_chat: Chat-Tab ist noch nicht geladen oder 'select_user' fehlt.")

    def check_for_updates(self):
        # ... (unverändert) ...
        self.update_tab_titles()
        self.update_header_notifications()
        if "Mitarbeiter" in self.loaded_tabs:
            frame = self.tab_frames.get("Mitarbeiter")
            if frame and frame.winfo_exists() and hasattr(frame,
                                                          'check_pending_approvals'): frame.check_pending_approvals()
        self.after(60000, self.check_for_updates)

    def open_bug_report_dialog(self):
        BugReportDialog(self, self.user_data['id'], self.check_for_updates)

    def refresh_antragssperre_views(self):
        # ... (unverändert) ...
        if "Schichtplan" in self.loaded_tabs and self.tab_frames["Schichtplan"].winfo_exists(): self.tab_frames[
            "Schichtplan"].update_lock_status()
        if "Antragssperre" in self.loaded_tabs and self.tab_frames["Antragssperre"].winfo_exists(): self.tab_frames[
            "Antragssperre"].load_locks_for_year()

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
                command = None
                if "action" in notif:
                    command = notif["action"]
                else:
                    tab_name = notif.get("tab")
                    if tab_name: command = lambda tab=tab_name: self.switch_to_tab(tab)
                if command:
                    btn = ttk.Button(self.notification_frame, text=notif["text"], style=f'Notif{i}.TButton',
                                     command=command)
                    btn.pack(side="left", padx=5, fill="x", expand=True)

    def load_all_data(self):
        # ... (unverändert) ...
        self.load_shift_types();
        self.load_staffing_rules()
        self._load_holidays_for_year(self.current_display_date.year)
        self._load_events_for_year(self.current_display_date.year)

    def refresh_all_tabs(self):
        # ... (unverändert) ...
        print("[DEBUG] Aktualisiere alle *geladenen* Tabs...")
        self.load_all_data()
        for tab_name in self.loaded_tabs:
            frame = self.tab_frames.get(tab_name)
            if frame and frame.winfo_exists():
                if hasattr(frame, 'refresh_data'):
                    print(f"[DEBUG] rufe refresh_data() für {tab_name} auf"); frame.refresh_data()
                elif hasattr(frame, 'refresh_plan'):
                    print(f"[DEBUG] rufe refresh_plan() für {tab_name} auf"); frame.refresh_plan()
        self.check_for_updates()

    def load_shift_types(self):
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
        self.current_year_holidays = HolidayManager.get_holidays_for_year(year)

    def _load_events_for_year(self, year):
        self.events = EventManager.get_events_for_year(year)

    def is_holiday(self, check_date):
        return check_date in self.current_year_holidays

    def get_event_type(self, current_date):
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
        return defaultdict(int, load_shift_frequency())

    def save_shift_frequency(self):
        if not save_shift_frequency(self.shift_frequency): messagebox.showwarning("Speicherfehler",
                                                                                  "Die Schichthäufigkeit konnte nicht in der Datenbank gespeichert werden.",
                                                                                  parent=self)

    def reset_shift_frequency(self):
        if messagebox.askyesno("Bestätigen", "Möchten Sie den Zähler für die Schichthäufigkeit wirklich zurücksetzen?",
                               parent=self):
            if reset_shift_frequency():
                self.shift_frequency.clear(); messagebox.showinfo("Erfolg", "Der Zähler wurde zurückgesetzt.",
                                                                  parent=self)
            else:
                messagebox.showerror("Fehler", "Fehler beim Zurücksetzen in der Datenbank.", parent=self)

    def get_allowed_roles(self):
        # ... (unverändert) ...
        admin_level = ROLE_HIERARCHY.get(self.user_data['role'], 0)
        allowed_roles = [role for role, level in ROLE_HIERARCHY.items() if level < admin_level]
        if self.user_data['role'] == "SuperAdmin": allowed_roles.append("SuperAdmin")
        return allowed_roles

    def open_user_order_window(self):
        UserOrderWindow(self, callback=self.refresh_all_tabs)

    def open_shift_order_window(self):
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
        # ... (unverändert) ...
        if "Schichtplan" in self.loaded_tabs:
            frame = self.tab_frames.get("Schichtplan")
            if frame and frame.winfo_exists(): frame.refresh_plan()

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