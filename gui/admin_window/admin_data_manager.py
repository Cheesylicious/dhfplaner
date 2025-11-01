# gui/admin_window/admin_data_manager.py
import tkinter as tk
from tkinter import messagebox
from datetime import date
from collections import defaultdict

from database.db_core import (
    load_config_json,
    save_config_json,
    load_shift_frequency,
    save_shift_frequency,
    reset_shift_frequency,
    MIN_STAFFING_RULES_CONFIG_KEY
)
from database.db_shifts import get_all_shift_types

# Manager für Feiertage und Events importieren
from ..holiday_manager import HolidayManager
from ..event_manager import EventManager


class AdminDataManager:
    def __init__(self, admin_window):
        """
        Manager für das Laden und Verwalten von Daten im Admin-Fenster.

        :param admin_window: Die Instanz von MainAdminWindow.
        """
        self.admin_window = admin_window

        # Initialisiere die Datenattribute im Hauptfenster
        self.admin_window.shift_types_data = {}
        self.admin_window.staffing_rules = {}
        # --- KORREKTUR: Diese Instanzvariablen werden nicht mehr benötigt ---
        # self.admin_window.events = {}
        # self.admin_window.current_year_holidays = {}
        # --- ENDE KORREKTUR ---
        self.admin_window.shift_frequency = self.load_shift_frequency()

    def load_all_data(self):
        """Lädt alle notwendigen Basisdaten (Schichtarten, Regeln, Feiertage, Events)."""
        print("[DEBUG] AdminDataManager.load_all_data gestartet.")
        # Lade Daten in Instanzvariablen des Hauptfensters
        try:
            self.load_shift_types()  # Lädt self.admin_window.shift_types_data
        except Exception as e_st:
            print(f"[FEHLER] Kritisch: Schichtarten konnten nicht geladen werden: {e_st}")
            messagebox.showerror("Kritischer Ladefehler",
                                 f"Schichtarten konnten nicht geladen werden:\n{e_st}\nEinige Funktionen sind möglicherweise beeinträchtigt.",
                                 parent=self.admin_window)
            self.admin_window.shift_types_data = {}  # Sicherer Fallback

        try:
            self.load_staffing_rules()  # Lädt self.admin_window.staffing_rules
        except Exception as e_sr:
            print(f"[FEHLER] Besetzungsregeln konnten nicht geladen werden: {e_sr}")
            messagebox.showwarning("Ladefehler",
                                   f"Besetzungsregeln konnten nicht geladen werden:\n{e_sr}\nVerwende Standardregeln.",
                                   parent=self.admin_window)
            # self.admin_window.staffing_rules wird in load_staffing_rules schon auf Default gesetzt

        # Lade Feiertage und Events für das *aktuelle* Kalenderjahr beim Start
        current_year = date.today().year
        try:
            self._load_holidays_for_year(current_year)  # Lädt Feiertage in den globalen Cache
        except Exception as e_ho:
            print(f"[FEHLER] Feiertage für {current_year} konnten nicht geladen werden: {e_ho}")
            messagebox.showwarning("Ladefehler", f"Feiertage für {current_year} konnten nicht geladen werden:\n{e_ho}",
                                   parent=self.admin_window)
            # self.admin_window.current_year_holidays = {} # Veraltet

        try:
            self._load_events_for_year(current_year)  # Lädt Events in den globalen Cache
        except Exception as e_ev:
            print(f"[FEHLER] Sondertermine für {current_year} konnten nicht geladen werden: {e_ev}")
            messagebox.showwarning("Ladefehler",
                                   f"Sondertermine für {current_year} konnten nicht geladen werden:\n{e_ev}",
                                   parent=self.admin_window)
            # self.admin_window.events = {} # Veraltet

        print(f"[DEBUG] Basisdaten für {current_year} initial geladen.")

    def load_shift_types(self):
        """Lädt alle Schichtarten aus der Datenbank."""
        try:
            all_types = get_all_shift_types()
            self.admin_window.shift_types_data = {st['abbreviation']: st for st in all_types}
            print(f"[DEBUG] {len(self.admin_window.shift_types_data)} Schichtarten geladen.")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Schichtarten: {e}")
            messagebox.showerror("Datenbankfehler", f"Schichtarten konnten nicht geladen werden:\n{e}",
                                 parent=self.admin_window)
            self.admin_window.shift_types_data = {}  # Sicherer Fallback

    def load_staffing_rules(self):
        """Lädt die Mindestbesetzungsregeln aus der Konfiguration (JSON in DB)."""
        try:
            rules = load_config_json(MIN_STAFFING_RULES_CONFIG_KEY)

            default_colors = {
                "alert_bg": "#FF5555",
                "overstaffed_bg": "#FFFF99",
                "success_bg": "#90EE90",
                "weekend_bg": "#EAF4FF",
                "holiday_bg": "#FFD700",
                "violation_bg": "#FF5555",
                "Ausstehend": "orange",
                "Admin_Ausstehend": "#E0B0FF"
            }
            defaults = {
                "Mo-Do": {}, "Fr": {}, "Sa-So": {}, "Holiday": {}, "Daily": {},
                "Colors": default_colors
            }

            if not rules or not isinstance(rules, dict):
                print("[WARNUNG] Besetzungsregeln nicht gefunden oder ungültig, verwende Standard.")
                self.admin_window.staffing_rules = defaults
            else:
                for key, default_val in defaults.items():
                    if key not in rules:
                        rules[key] = default_val
                    elif key == "Colors":
                        if isinstance(rules[key], dict):
                            for ckey, cval in default_colors.items():
                                if ckey not in rules["Colors"]:
                                    print(f"[DEBUG] Füge fehlende Standardfarbe hinzu: Colors['{ckey}'] = '{cval}'")
                                    rules["Colors"][ckey] = cval
                        else:
                            print("[WARNUNG] Ungültiger 'Colors'-Eintrag in Besetzungsregeln, verwende Standardfarben.")
                            rules["Colors"] = default_colors

                self.admin_window.staffing_rules = rules
                print("[DEBUG] Besetzungsregeln geladen und validiert.")

        except Exception as e:
            print(f"[FEHLER] beim Laden der Besetzungsregeln: {e}")
            messagebox.showerror("Ladefehler",
                                 f"Besetzungsregeln konnten nicht geladen werden:\n{e}\nVerwende Standardregeln.",
                                 parent=self.admin_window)
            self.admin_window.staffing_rules = defaults

    def _load_holidays_for_year(self, year):
        """
        Lädt die Feiertage für ein spezifisches Jahr in den globalen Cache
        des HolidayManagers.
        """
        try:
            # Ruft die statische Methode auf, um den Cache zu füllen
            holidays = HolidayManager.get_holidays_for_year(year)
            # --- KORREKTUR: Speichere nicht mehr in admin_window ---
            # self.admin_window.current_year_holidays = holidays
            print(f"[DEBUG] Feiertage für {year} in globalen Cache geladen ({len(holidays)} Einträge).")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Feiertage für {year}: {e}")
            messagebox.showwarning("Fehler Feiertage", f"Feiertage für {year} konnten nicht geladen werden:\n{e}",
                                   parent=self.admin_window)
            # self.admin_window.current_year_holidays = {} # Veraltet

    def _load_events_for_year(self, year):
        """
        Lädt die Sondertermine (Events) für ein spezifisches Jahr in den globalen
        Cache des EventManagers.
        """
        try:
            # Ruft die statische Methode auf, um den Cache zu füllen
            events = EventManager.get_events_for_year(year)
            # --- KORREKTUR: Speichere nicht mehr in admin_window ---
            # self.admin_window.events = events
            print(f"[DEBUG] Sondertermine für {year} in globalen Cache geladen ({len(events)} Einträge).")
        except Exception as e:
            print(f"[FEHLER] beim Laden der Sondertermine für {year}: {e}")
            messagebox.showwarning("Fehler Sondertermine",
                                   f"Sondertermine für {year} konnten nicht geladen werden:\n{e}",
                                   parent=self.admin_window)
            # self.admin_window.events = {} # Veraltet

    def is_holiday(self, check_date):
        """
        Prüft, ob ein gegebenes Datum ein Feiertag ist.
        Greift jetzt direkt auf die statische Methode des HolidayManagers zu.
        """
        # --- KORREKTUR: Direkter Aufruf der statischen Methode ---
        return HolidayManager.is_holiday(check_date)
        # --- ALTER CODE (fehlerhaft bei Jahreswechsel): ---
        # if not isinstance(check_date, date):
        #     try:
        #         if hasattr(check_date, 'date'):
        #             check_date = check_date.date()
        #         else:
        #             check_date = date.fromisoformat(str(check_date))
        #     except (TypeError, ValueError):
        #         print(f"[WARNUNG] is_holiday: Ungültiges Datumformat erhalten: {check_date}")
        #         return False
        #
        # # TODO: Dynamisches Nachladen implementieren, falls das Jahr nicht übereinstimmt
        # target_year = check_date.year
        # # Aktuell: Prüft nur im Dictionary des geladenen Jahres
        # return check_date in self.admin_window.current_year_holidays
        # --- ENDE KORREKTUR ---

    def get_event_type(self, current_date):
        """
        Gibt den Typ des Sondertermins für ein Datum zurück, falls vorhanden.
        Greift jetzt direkt auf die statische Methode des EventManagers zu.
        """
        # --- KORREKTUR: Direkter Aufruf der statischen Methode ---
        # Die EventManager.get_event_type Methode lädt das Jahr bei Bedarf
        # dynamisch nach (genau wie HolidayManager.is_holiday).
        return EventManager.get_event_type(current_date)
        # --- ALTER CODE (fehlerhaft bei Jahreswechsel): ---
        # if not isinstance(current_date, date):
        #     try:
        #         if hasattr(current_date, 'date'):
        #             current_date = current_date.date()
        #         else:
        #             current_date = date.fromisoformat(str(current_date))
        #     except (TypeError, ValueError):
        #         print(f"[WARNUNG] get_event_type: Ungültiges Datumformat erhalten: {current_date}")
        #         return None
        #
        # # TODO: Analog zu Feiertagen, ggf. dynamisches Nachladen
        # return EventManager.get_event_type(current_date, self.admin_window.events)
        # --- ENDE KORREKTUR ---


    def load_shift_frequency(self):
        """Lädt die Häufigkeit der zugewiesenen Schichten aus der DB-Konfiguration."""
        try:
            freq_data = load_shift_frequency()
            return defaultdict(int, freq_data if freq_data else {})
        except Exception as e:
            print(f"[FEHLER] beim Laden der Schichthäufigkeit: {e}")
            messagebox.showerror("Ladefehler", f"Die Schichthäufigkeit konnte nicht geladen werden:\n{e}",
                                 parent=self.admin_window)
            return defaultdict(int)

    def save_shift_frequency(self):
        """Speichert die aktuelle Schichthäufigkeit in die DB."""
        if not self.admin_window.shift_frequency:
            print("[DEBUG] Schichthäufigkeit ist leer, Speichern übersprungen.")
            return
        try:
            freq_to_save = dict(self.admin_window.shift_frequency)
            print(f"[DEBUG] Speichere Schichthäufigkeit: {len(freq_to_save)} Einträge.")
            if not save_shift_frequency(freq_to_save):
                messagebox.showwarning("Speicherfehler",
                                       "Die Schichthäufigkeit konnte nicht in der Konfiguration gespeichert werden (DB-Problem?).",
                                       parent=self.admin_window)
        except Exception as e:
            print(f"[FEHLER] beim Speichern der Schichthäufigkeit: {e}")
            messagebox.showerror("Schwerer Speicherfehler",
                                 f"Speichern der Schichthäufigkeit ist fehlgeschlagen:\n{e}",
                                 parent=self.admin_window)

    def reset_shift_frequency(self):
        """Setzt den Zähler für die Schichthäufigkeit in der DB und lokal zurück."""
        if messagebox.askyesno("Zähler zurücksetzen",
                               "Möchten Sie den Zähler für die Schichthäufigkeit wirklich für ALLE Mitarbeiter auf Null zurücksetzen?\nDiese Aktion kann nicht rückgängig gemacht werden!",
                               icon='warning', parent=self.admin_window):
            try:
                if reset_shift_frequency():
                    self.admin_window.shift_frequency.clear()
                    print("[DEBUG] Schichthäufigkeit erfolgreich zurückgesetzt.")
                    messagebox.showinfo("Erfolg", "Der Zähler für die Schichthäufigkeit wurde zurückgesetzt.",
                                        parent=self.admin_window)
                    # Der TabManager muss den Refresh des Schichtplans auslösen
                    if hasattr(self.admin_window, 'tab_manager'):
                        self.admin_window.tab_manager.refresh_specific_tab("Schichtplan")
                else:
                    messagebox.showerror("Fehler", "Fehler beim Zurücksetzen des Zählers in der Datenbank.",
                                         parent=self.admin_window)
            except Exception as e:
                print(f"[FEHLER] beim Zurücksetzen der Schichthäufigkeit: {e}")
                messagebox.showerror("Schwerer Fehler", f"Zurücksetzen des Zählers fehlgeschlagen:\n{e}",
                                     parent=self.admin_window)