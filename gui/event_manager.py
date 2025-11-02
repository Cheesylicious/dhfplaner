# gui/event_manager.py
import os
import json
from datetime import date
from database.db_core import create_connection, save_config_json, load_config_json
import mysql.connector

# --- NEU: Cache für Events ---
# Speichert Events pro Jahr: {2024: {"2024-01-10": "Ausbildung", ...}, 2025: {...}}
_events_cache = {}
# -------------------------------

# Der Dateiname der alten JSON-Datei (nur für Migration)
EVENT_JSON_FILE = 'events.json'


class EventManager:
    """
    Verwaltet Events (Ausbildung, Schießen etc.) durch Laden und Speichern
    in der Datenbank (app_config).
    Nutzt jetzt Caching.
    """

    CONFIG_KEY = "EVENTS_NEW"

    @staticmethod
    def _migrate_json_to_db():
        """
        Versucht, die alte events.json-Datei zu lesen und in die Datenbank
        zu migrieren, falls der DB-Eintrag nicht existiert.
        """
        print(f"[Migration] Prüfe auf alte {EVENT_JSON_FILE}...")
        all_events = {}

        # Finde die JSON-Datei (im Hauptverzeichnis, nicht im gui-Verzeichnis)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, EVENT_JSON_FILE)

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    all_events = json.load(f)
                print(f"[Migration] Alte {EVENT_JSON_FILE} gefunden. Migriere nach DB...")
                # Speichere die geladenen Daten in der DB
                if save_config_json(EventManager.CONFIG_KEY, all_events):
                    print(f"[Migration] Erfolgreich zu DB-Key '{EventManager.CONFIG_KEY}' migriert.")
                    # Alte Datei umbenennen, um erneute Migration zu verhindern
                    os.rename(json_path, json_path + '.migrated')
                    print(f"[Migration] Alte Datei zu '{json_path}.migrated' umbenannt.")
                else:
                    print(f"[Migration] FEHLER beim Speichern der migrierten Daten in der DB.")
            except (IOError, json.JSONDecodeError) as e:
                print(f"[Migration] FEHLER beim Lesen der {EVENT_JSON_FILE}: {e}")

        else:
            print(f"[Migration] Keine alte {EVENT_JSON_FILE} gefunden. Starte mit leerer Konfiguration.")
            # Erstelle einen leeren Eintrag, um dies nicht erneut zu versuchen
            save_config_json(EventManager.CONFIG_KEY, {})

        return all_events

    @staticmethod
    def get_events_for_year(year_int):
        """
        Gibt ein Dictionary der Events für ein bestimmtes Jahr zurück.
        Format: {"YYYY-MM-DD": "Eventtyp"}
        Nutzt jetzt einen Cache.
        """
        global _events_cache
        year_str = str(year_int)

        # 1. Prüfe den Cache
        if year_str in _events_cache:
            # print(f"[DEBUG] Lade Events für {year_str} aus dem Cache.") # <--- KORREKTUR: Entfernt redundantes Logging (Regel 2)
            return _events_cache[year_str]

        # 2. Lade aus DB (oder migriere)
        print(f"[DEBUG] Lade Events für {year_str} aus der DB.")
        all_events = load_config_json(EventManager.CONFIG_KEY)
        if all_events is None:
            # Eintrag existiert nicht in der DB, versuche Migration
            all_events = EventManager._migrate_json_to_db()

        # 3. Filtere das gewünschte Jahr
        year_events = {}
        if all_events and year_str in all_events:
            year_events = all_events[year_str]

        # 4. Speichere im Cache
        _events_cache[year_str] = year_events
        return year_events

    @staticmethod
    def get_all_events():
        """Lädt alle Events aus der DB."""
        all_events = load_config_json(EventManager.CONFIG_KEY)
        if all_events is None:
            all_events = EventManager._migrate_json_to_db()
        return all_events

    @staticmethod
    def save_events(all_events_data):
        """
        Speichert die komplette Event-Struktur in der DB.
        Leert jetzt den Cache.
        """
        global _events_cache
        if save_config_json(EventManager.CONFIG_KEY, all_events_data):
            # 5. Cache leeren
            _events_cache.clear()
            print("[DEBUG] Event-Cache geleert.")
            return True
        return False

    @staticmethod
    def get_event_type(current_date, events_dict=None):
        """
        Prüft, ob an einem Datum ein Event stattfindet.
        Akzeptiert optional ein vorausgefülltes Dictionary.
        """
        date_str = current_date.strftime('%Y-%m-%d')

        # Wenn kein Dictionary übergeben wurde, hole es für das Jahr
        if events_dict is None:
            # Der Aufruf hier führt jetzt nicht mehr zu Log-Spam, da die Print-Anweisung oben entfernt wurde.
            events_dict = EventManager.get_events_for_year(current_date.year)

        return events_dict.get(date_str)

    @staticmethod
    def clear_cache():
        """Externe Methode, um den Cache bei Bedarf zu leeren."""
        global _events_cache
        _events_cache.clear()
        print("[DEBUG] Event-Cache (extern) geleert.")