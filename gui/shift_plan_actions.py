# gui/shift_plan_actions.py
# REFRACTORED (Regel 4): Dient als Fassade und delegiert
# die Logik an spezialisierte Helfer-Klassen.
# KORRIGIERT: Behebt "Renderer nicht verfügbar" durch spätere Initialisierung.
# KORRIGIERT (Regel 4): Behebt "Menü kann nicht erstellt werden",
# indem die Menü-Erstellung hierher verschoben wird (Just-in-Time).

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

# DB-Importe (nur noch für die Menü-Erstellung benötigt)
from database.db_core import load_config_json

# --- NEUE IMPORTE (Refactoring Regel 4) ---
from .action_handlers.action_update_handler import ActionUpdateHandler
from .action_handlers.action_shift_handler import ActionShiftHandler
from .action_handlers.action_request_handler import ActionRequestHandler
from .action_handlers.action_admin_handler import ActionAdminHandler

# --- ENDE NEUE IMPORTE ---

SHIFT_MENU_CONFIG_KEY = "SHIFT_DISPLAY_CONFIG"


class ShiftPlanActionHandler:
    """
    Verarbeitet Klicks und Aktionen im Dienstplan-Grid.
    Delegiert die eigentliche Logik an Helferklassen im
    /action_handlers/ Verzeichnis.
    """

    def __init__(self, master_tab, app_instance, shift_plan_tab_oder_dm, renderer_instance_none):
        # HINWEIS: renderer_instance_none ist beim Start 'None'.
        # Die Helfer werden erst initialisiert, wenn set_renderer aufgerufen wird.

        self.tab = master_tab
        self.app = app_instance  # MainAdminWindow

        # Kompatibilität für alte Init-Signatur in ShiftPlanTab
        # In unserem Fall ist shift_plan_tab_oder_dm der data_manager
        self.data_manager = shift_plan_tab_oder_dm

        self.renderer = renderer_instance_none  # Wird später gesetzt

        # Lade Menü-Config
        self._menu_config_cache = self._load_menu_config()

        # Helfer sind noch nicht initialisiert
        self.updater = None
        self.shift_handler = None
        self.request_handler = None
        self.admin_handler = None

    def set_renderer_and_init_helpers(self, renderer_instance):
        """
        Wird von ShiftPlanTab aufgerufen, NACHDEM der Renderer erstellt wurde.
        Initialisiert alle Helferklassen mit der korrekten Renderer-Referenz.
        """
        print("[ActionHandler] Renderer gesetzt und Helfer werden initialisiert...")
        self.renderer = renderer_instance

        # 1. Der Update-Handler
        self.updater = ActionUpdateHandler(
            tab=self.tab,
            renderer=self.renderer,
            data_manager=self.data_manager
        )

        # 2. Die spezialisierten Handler
        self.shift_handler = ActionShiftHandler(
            tab=self.tab,
            app_instance=self.app,
            renderer=self.renderer,
            data_manager=self.data_manager,
            update_handler=self.updater
        )

        self.request_handler = ActionRequestHandler(
            tab=self.tab,
            app_instance=self.app,
            renderer=self.renderer,
            data_manager=self.data_manager,
            update_handler=self.updater
        )

        self.admin_handler = ActionAdminHandler(
            tab=self.tab,
            app_instance=self.app,
            renderer=self.renderer,
            data_manager=self.data_manager
        )

    def _load_menu_config(self):
        """Lädt die Konfiguration für das Schicht-Kontextmenü."""
        config = load_config_json(SHIFT_MENU_CONFIG_KEY)
        return config if config is not None else {}

    # --- NEUE METHODE (Refactoring Regel 4) ---
    def _build_shift_menu_items(self):
        """
        Erstellt die Menü-Einträge "Just-in-Time", um Start-Fehler zu vermeiden.
        (Ehemals in ShiftPlanTab._prepare_shift_menu_items)
        """
        try:
            # self.app = MainAdminWindow, self.app.app = BootLoader

            # Schicht-Definitionen kommen vom Bootloader (self.app.app)
            all_abbrevs = list(self.app.app.shift_types_data.keys())
            menu_config = self._menu_config_cache  # Bereits in __init__ geladen

            # --- KORREKTUR: shift_frequency kommt von MainAdminWindow (self.app) ---
            shift_frequency = self.app.shift_frequency
            # --- ENDE KORREKTUR ---

        except AttributeError as e:
            print(f"[FEHLER] ActionHandler kann Menü nicht bauen, App-Daten fehlen: {e}")
            # Fallback, falls App-Daten noch nicht geladen sind (sollte nie passieren)
            return [("Fehler: App-Daten nicht geladen", None)]

        sorted_abbrevs = sorted(all_abbrevs, key=lambda s: shift_frequency.get(s, 0), reverse=True)
        prepared_items = []

        for abbrev in sorted_abbrevs:
            if menu_config.get(abbrev, True):  # Prüft die Menü-Config
                shift_info = self.app.app.shift_types_data.get(abbrev)
                if shift_info:
                    name = shift_info.get('name', abbrev)
                    count = shift_frequency.get(abbrev, 0)
                    label_text = f"{abbrev} ({name})" + (f"  (Bisher {count}x)" if count > 0 else "")
                    prepared_items.append((abbrev, label_text))
        return prepared_items

    # --- ENDE NEUE METHODE ---

    # --- Prüf- und Delegationsmethoden ---

    def _check_helpers_initialized(self):
        """Prüft, ob der Renderer und die Helfer initialisiert wurden."""
        if not self.updater or not self.shift_handler or not self.request_handler or not self.admin_handler:
            print("[FEHLER] ActionHandler-Helfer sind nicht initialisiert! Renderer wurde nie gesetzt.")
            # Verhindere weitere Aktionen, wenn der Klick zu früh erfolgt
            return False
        return True

    def save_shift_entry_and_refresh(self, user_id, date_str, shift_abbrev):
        """Delegiert das Speichern einer Schicht an den ShiftHandler."""
        if self._check_helpers_initialized():
            self.shift_handler.save_shift_entry_and_refresh(user_id, date_str, shift_abbrev)

    def secure_shift(self, user_id, date_str, shift_abbrev):
        """Delegiert das Sichern einer Schicht an den ShiftHandler."""
        if self._check_helpers_initialized():
            self.shift_handler.secure_shift(user_id, date_str, shift_abbrev)

    def unlock_shift(self, user_id, date_str):
        """Delegiert das Entsichern einer Schicht an den ShiftHandler."""
        if self._check_helpers_initialized():
            self.shift_handler.unlock_shift(user_id, date_str)

    def admin_add_wunschfrei(self, user_id, date_str, request_type):
        """Delegiert das Admin-Erstellen von Wünschen an den RequestHandler."""
        if self._check_helpers_initialized():
            self.request_handler.admin_add_wunschfrei(user_id, date_str, request_type)

    def show_wunschfrei_context_menu(self, event, user_id, date_str):
        """Delegiert die Anzeige des Wunsch-Kontextmenüs an den RequestHandler."""
        if self._check_helpers_initialized():
            self.request_handler.show_wunschfrei_context_menu(event, user_id, date_str)

    def delete_shift_plan_by_admin(self, year, month):
        """Delegiert das Löschen des Plans an den AdminHandler."""
        if self._check_helpers_initialized():
            self.admin_handler.delete_shift_plan_by_admin(year, month)

    def unlock_all_shifts_for_month(self, year, month):
        """Delegiert das globale Entsichern an den AdminHandler."""
        if self._check_helpers_initialized():
            self.admin_handler.unlock_all_shifts_for_month(year, month)

    # --- Haupt-Kontextmenü (verbleibt hier als Orchestrator) ---

    def on_grid_cell_click(self, event, user_id, day, year, month):
        """
        Orchestriert das Klick-Event und baut das Kontextmenü dynamisch auf,
        indem es die Shift- und Request-Handler nutzt.
        """
        if not self._check_helpers_initialized():
            print("[WARNUNG] Klick empfangen, aber Helfer sind noch nicht bereit.")
            return

        # --- KORREKTUR: Tag 0 (Ü-Zelle) abfangen ---
        if day == 0:
            print("[ActionHandler] Klick auf 'Ü'-Zelle ignoriert.")
            return
        # --- ENDE KORREKTUR ---

        date_obj = date(year, month, day);
        date_str = date_obj.strftime('%Y-%m-%d')
        context_menu = tk.Menu(self.tab, tearoff=0)

        # 1. Daten sammeln
        current_shift = self.data_manager.shift_schedule_data.get(str(user_id), {}).get(date_str)
        lock_status = self.data_manager.shift_lock_manager.get_lock_status(str(user_id), date_str)

        # 2. Normale Schicht-Auswahl (Nur wenn nicht gesperrt)
        if not lock_status:
            # --- KORREKTUR (Regel 4): Menü "Just-in-Time" erstellen ---
            # Entfernt die alte, fehlerhafte Cache-Prüfung von ShiftPlanTab

            menu_items = self._build_shift_menu_items()  # Ruft die NEUE interne Methode auf

            if not menu_items:
                context_menu.add_command(label="Fehler Schichtladen", state="disabled")

            for abbrev, label_text in menu_items:
                # Prüfe, ob ein Fehler beim Laden aufgetreten ist (Fallback)
                if abbrev == "Fehler: App-Daten nicht geladen":
                    context_menu.add_command(label=abbrev, state="disabled")
                    break

                context_menu.add_command(label=label_text,
                                         # Ruft den ShiftHandler auf
                                         command=lambda u=user_id, d=date_str,
                                                        s=abbrev: self.shift_handler.save_shift_entry_and_refresh(u,
                                                                                                                  d,
                                                                                                                  s))
            # --- ENDE KORREKTUR ---

            context_menu.add_separator();
            context_menu.add_command(label="FREI",
                                     # Ruft den ShiftHandler auf
                                     command=lambda u=user_id,
                                                    d=date_str: self.shift_handler.save_shift_entry_and_refresh(u, d,
                                                                                                                ""))

        # 3. Admin-Optionen (Wunschfrei)
        context_menu.add_separator()
        context_menu.add_command(label="Admin: Wunschfrei (WF)",
                                 # Ruft den RequestHandler auf
                                 command=lambda u=user_id, d=date_str: self.request_handler.admin_add_wunschfrei(u, d,
                                                                                                                 'WF'))
        context_menu.add_command(label="Admin: Wunschschicht (T/N)",
                                 # Ruft den RequestHandler auf
                                 command=lambda u=user_id, d=date_str: self.request_handler.admin_add_wunschfrei(u, d,
                                                                                                                 'T/N'))
        context_menu.add_separator()

        # 4. Lock/Unlock Optionen
        securable_shifts = ["T.", "N.", "6"]
        is_securable_or_fixed = current_shift in securable_shifts or current_shift in ["X", "QA", "S", "U", "EU", "WF",
                                                                                       "U?"]

        if lock_status:
            context_menu.add_command(label=f"🔓 Sicherung aufheben (war: {lock_status})", foreground="#007700",
                                     # Ruft den ShiftHandler auf
                                     command=lambda u=user_id, d=date_str: self.shift_handler.unlock_shift(u, d))
        elif is_securable_or_fixed:
            shift_to_secure = current_shift if current_shift else ""
            if shift_to_secure:
                context_menu.add_command(label=f"🔒 Schicht sichern ({shift_to_secure})", foreground="#CC0000",
                                         # Ruft den ShiftHandler auf
                                         command=lambda u=user_id, d=date_str,
                                                        s=shift_to_secure: self.shift_handler.secure_shift(u,
                                                                                                           d,
                                                                                                           s))
            else:
                context_menu.add_command(label="🔒 Schicht sichern", state="disabled")

        context_menu.tk_popup(event.x_root, event.y_root)

    # --- Alte, jetzt ausgelagerte Methoden (wurden entfernt) ---
    # _trigger_targeted_update -> ActionUpdateHandler
    # _get_old_shift_from_ui -> ActionUpdateHandler
    # _update_dm_wunschfrei_cache -> ActionUpdateHandler
    # _set_shift_lock_status -> ActionShiftHandler
    # handle_request_... (alle) -> ActionRequestHandler

