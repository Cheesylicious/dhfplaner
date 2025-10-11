# gui/event_manager.py
import json
from datetime import date

class EventManager:
    CONFIG_FILE = 'events_config.json'

    @staticmethod
    def load_events():
        try:
            with open(EventManager.CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def save_events(events):
        try:
            with open(EventManager.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(events, f, indent=4, sort_keys=True)
            return True, "Termine erfolgreich gespeichert."
        except Exception as e:
            return False, f"Fehler beim Speichern der Termine: {e}"

    @staticmethod
    def get_events_for_year(year):
        events = EventManager.load_events()
        return events.get(str(year), {})

    @staticmethod
    def get_event_type(current_date, events_of_year):
        date_str = current_date.strftime('%Y-%m-%d')
        return events_of_year.get(date_str)