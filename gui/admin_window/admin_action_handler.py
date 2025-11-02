# gui/admin_window/admin_action_handler.py
import tkinter as tk
from tkinter import messagebox
# --- KORREKTUR: datetime.date importieren ---
from datetime import datetime, date
# --- ENDE KORREKTUR ---


# Importiere die Dialog-Klassen
from ..dialogs.user_order_window import UserOrderWindow
from ..dialogs.shift_order_window import ShiftOrderWindow
from ..dialogs.min_staffing_window import MinStaffingWindow
from ..dialogs.holiday_settings_window import HolidaySettingsWindow
from ..dialogs.event_settings_window import EventSettingsWindow
from ..dialogs.request_settings_window import RequestSettingsWindow
from ..dialogs.planning_assistant_settings_window import PlanningAssistantSettingsWindow
from ..dialogs.color_settings_window import ColorSettingsWindow

# Importiere die Tab-Klassen, die dynamisch geladen werden
from ..tabs.request_lock_tab import RequestLockTab
from ..tabs.user_tab_settings_tab import UserTabSettingsTab
from ..tabs.password_reset_requests_window import PasswordResetRequestsWindow

# Import für Typenvergleich
from ..tabs.shift_plan_tab import ShiftPlanTab

# Importiere die DB-Funktionen, die hier benötigt werden
from database.db_core import save_config_json, MIN_STAFFING_RULES_CONFIG_KEY


class AdminActionHandler:
    def __init__(self, admin_window):
        """
        Manager für Aktionen (Menü-Klicks, Dialogöffner).

        :param admin_window: Die Instanz von MainAdminWindow.
        """
        self.admin_window = admin_window
        self.tab_manager = admin_window.tab_manager  # Referenz auf den TabManager

    # --- Dynamische Tab-Öffner ---
    # ... (open_request_lock_window bis open_shift_types_window unverändert) ...
    def open_request_lock_window(self):
        """Lädt oder wechselt zum 'Antragssperre'-Tab."""
        self.tab_manager._load_dynamic_tab("Antragssperre", RequestLockTab, self.admin_window)

    def open_user_tab_settings(self):
        """Lädt oder wechselt zum 'Benutzer-Reiter'-Einstellungstab."""
        all_user_tab_names = ["Schichtplan", "Meine Anfragen", "Mein Urlaub", "Bug-Reports", "Teilnahmen", "Chat"]
        self.tab_manager._load_dynamic_tab("Benutzer-Reiter", UserTabSettingsTab, all_user_tab_names)

    def open_password_resets_window(self):
        """Lädt oder wechselt zum 'Passwort-Resets'-Tab."""
        self.tab_manager._load_dynamic_tab("Passwort-Resets", PasswordResetRequestsWindow, self.admin_window)

    def open_shift_types_window(self):
        """Wechselt zum 'Schichtarten'-Tab."""
        print("[DEBUG] Wechsle/Lade Schichtarten-Tab...")
        self.tab_manager.switch_to_tab("Schichtarten")

    # --- Dialog-Öffner (aus dem Einstellungsmenü) ---

    def open_user_order_window(self):
        """
        Öffnet das Fenster zur Sortierung der Benutzer.
        Versucht, Jahr/Monat aus der zentralen Variable 'current_display_date'
        des Hauptfensters zu lesen, wenn der ShiftPlanTab aktiv ist.
        """
        for_date = datetime.now()  # Fallback-Datum
        callback = self.tab_manager.refresh_all_tabs  # Fallback-Callback
        show_info_message = True

        try:
            selected_tab_id = self.admin_window.notebook.select()
            if not selected_tab_id:
                raise tk.TclError("Kein Tab ausgewählt.")

            current_widget = self.admin_window.notebook.nametowidget(selected_tab_id)

            if isinstance(current_widget, ShiftPlanTab):
                print("[DEBUG] Aktiver Tab ist ein ShiftPlanTab.")
                # --- FINALE KORREKTUR: Direktes Lesen von self.admin_window.current_display_date ---
                # Diese Variable wird vom ShiftPlanTab selbst aktualisiert.
                current_display_date_obj = getattr(self.admin_window, 'current_display_date', None)

                # Prüfen, ob das Attribut existiert und ein date- oder datetime-Objekt ist
                if isinstance(current_display_date_obj, (date, datetime)):
                    # Nimm den 1. des Monats von diesem Datum für das UserOrderWindow
                    for_date = datetime(current_display_date_obj.year, current_display_date_obj.month, 1)

                    # Spezifischen Callback für DIESEN Tab setzen (wie vorher)
                    if hasattr(current_widget, 'refresh_plan'):
                        callback = current_widget.refresh_plan
                    elif hasattr(current_widget, 'refresh_data'):
                        callback = current_widget.refresh_data
                    # Wenn keine Refresh-Methode -> Behalte globalen Callback

                    show_info_message = False  # Keine Info-Nachricht nötig
                    print(
                        f"[DEBUG] Öffne UserOrderWindow für spezifischen Monat (aus admin_window.current_display_date): {for_date.strftime('%Y-%m')}")
                else:
                    # current_display_date war nicht gesetzt oder kein gültiges Datumsobjekt
                    print(
                        "[WARNUNG] ShiftPlanTab aktiv, aber admin_window.current_display_date ist ungültig oder nicht vorhanden. Verwende Fallback.")
                    # show_info_message bleibt True

                # --- ENDE FINALE KORREKTUR ---
            else:
                # Das aktuelle Widget ist kein ShiftPlanTab (oder noch der Platzhalter)
                print(
                    f"[DEBUG] Aktuelles Widget ist kein geladener ShiftPlanTab (Typ: {type(current_widget)}). Verwende Fallback.")
                # show_info_message bleibt True

        except tk.TclError as e_tcl:
            # Fängt Fehler beim Zugriff auf Notebook/Widget ab
            print(f"[WARNUNG] TclError beim Ermitteln des Tabs in open_user_order_window: {e_tcl}. Verwende Fallback.")
            # show_info_message bleibt True (Standard)
        except AttributeError as e_attr:
            # Fängt Fehler ab, wenn 'current_display_date' nicht existiert
            print(f"[WARNUNG] AttributeError in open_user_order_window: {e_attr}. Verwende Fallback.")
            # show_info_message bleibt True
        except ValueError as e_val:
            # Fängt Fehler bei der datetime-Erstellung ab
            print(f"[WARNUNG] ValueError in open_user_order_window (Datum ungültig?): {e_val}. Verwende Fallback.")
            # show_info_message bleibt True
        except Exception as e:
            # Andere unerwartete Fehler
            print(f"Unerwarteter Fehler beim Öffnen des UserOrderWindow: {e}")
            messagebox.showerror("Fehler", f"Konnte das Sortierfenster nicht korrekt vorbereiten:\n{e}",
                                 parent=self.admin_window)
            # Im Zweifel immer den Fallback verwenden, show_info_message bleibt True

        # Zeige die Info-Nachricht nur an, wenn wir den Fallback verwenden
        if show_info_message:
            messagebox.showinfo("Info",
                                "Sie bearbeiten die Standard-Sortierung (basierend auf heute).\n\n"
                                "Um die Sortierung für einen bestimmten Monat zu sehen (inkl. zukünftiger/archivierter Mitarbeiter), "
                                "wählen Sie bitte zuerst den entsprechenden Schichtplan-Tab aus und stellen Sie sicher, dass er vollständig geladen ist.",
                                parent=self.admin_window)

        # Öffne das Fenster mit dem ermittelten Datum und Callback
        # Der print-Befehl zeigt jetzt das Datum an, das tatsächlich verwendet wird
        print(
            f"[DEBUG] Rufe UserOrderWindow auf mit for_date={for_date.strftime('%Y-%m-%d')} und callback={getattr(callback, '__name__', 'lambda/unknown')}")
        UserOrderWindow(self.admin_window, callback=callback, for_date=for_date)

    # ... (Restliche Methoden open_shift_order_window bis open_planning_assistant_settings unverändert) ...
    def open_shift_order_window(self):
        """ Öffnet das Fenster zur Sortierung der Schichtarten. """
        ShiftOrderWindow(self.admin_window, callback=self.tab_manager.refresh_all_tabs)

    def open_staffing_rules_window(self):
        """Öffnet das Einstellungsfenster für die Mindestbesetzung."""

        def save_and_refresh(new_rules):
            print("[DEBUG] Speichere Besetzungsregeln...")
            try:
                if save_config_json(MIN_STAFFING_RULES_CONFIG_KEY, new_rules):
                    # Greife über data_manager auf die Regeln zu
                    self.admin_window.staffing_rules = new_rules
                    messagebox.showinfo("Gespeichert", "Die Besetzungsregeln wurden erfolgreich aktualisiert.",
                                        parent=self.admin_window)
                    self.tab_manager.refresh_specific_tab("Schichtplan")
                else:
                    messagebox.showerror("Fehler",
                                         "Die Besetzungsregeln konnten nicht in der Konfiguration gespeichert werden.",
                                         parent=self.admin_window)
            except Exception as e:
                print(f"[FEHLER] beim Speichern der Besetzungsregeln: {e}")
                messagebox.showerror("Schwerer Speicherfehler", f"Speichern der Besetzungsregeln fehlgeschlagen:\n{e}",
                                     parent=self.admin_window)

        staffing_window = MinStaffingWindow(self.admin_window, current_rules=self.admin_window.staffing_rules,
                                            callback=save_and_refresh)
        staffing_window.focus_force()

    def open_holiday_settings_window(self):
        """Öffnet die Feiertagseinstellungen."""
        # --- ROBUSTERER ZUGRIFF AUF DATUM ---
        year_to_edit = datetime.today().year  # Fallback
        try:
            # Prüfe, ob das Attribut existiert und ein Datum ist
            current_date_obj = getattr(self.admin_window, 'current_display_date', None)
            if isinstance(current_date_obj, (date, datetime)):
                year_to_edit = current_date_obj.year
        except Exception as e:  # Fange generische Fehler ab, falls etwas Unerwartetes passiert
            print(f"[WARNUNG] Fehler beim Zugriff auf current_display_date für HolidaySettingsWindow: {e}")
        # --- ENDE ---

        # --- KORREKTUR: Das 'app'-Argument (self.admin_window) wurde hinzugefügt ---
        HolidaySettingsWindow(
            self.admin_window,  # master
            self.admin_window,  # app (dieses Argument fehlte)
            year=year_to_edit,
            callback=self.tab_manager.refresh_all_tabs
        )
        # --- ENDE KORREKTUR ---

    def open_event_settings_window(self):
        """Öffnet die Einstellungen für Sondertermine."""
        # --- ROBUSTERER ZUGRIFF AUF DATUM ---
        year_to_edit = datetime.today().year  # Fallback
        try:
            # Prüfe, ob das Attribut existiert und ein Datum ist
            current_date_obj = getattr(self.admin_window, 'current_display_date', None)
            if isinstance(current_date_obj, (date, datetime)):
                year_to_edit = current_date_obj.year
        except Exception as e:
            print(f"[WARNUNG] Fehler beim Zugriff auf current_display_date für EventSettingsWindow: {e}")
        # --- ENDE ---

        # (Hier war der Aufruf bereits korrekt und enthielt 'app')
        EventSettingsWindow(self.admin_window, self.admin_window, year=year_to_edit,
                            callback=self.tab_manager.refresh_all_tabs)

    def open_color_settings_window(self):
        """Öffnet die Farbeinstellungen."""
        ColorSettingsWindow(self.admin_window, callback=self.tab_manager.refresh_all_tabs)

    def open_request_settings_window(self):
        """Öffnet die Einstellungen für Anfragetypen."""
        RequestSettingsWindow(self.admin_window)

    def open_planning_assistant_settings(self):
        """Öffnet die Einstellungen für den Planungs-Helfer."""
        PlanningAssistantSettingsWindow(self.admin_window)