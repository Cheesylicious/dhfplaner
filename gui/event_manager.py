# gui/event_manager.py
from datetime import date
from database.db_core import get_special_appointments, save_special_appointment, delete_special_appointment


class EventManager:
    """Verwaltet zentrale Sondertermine (Ausbildung, Schießen) über die Datenbank."""

    @staticmethod
    def save_events(events_by_year):
        """
        Speichert die Termine in der Datenbank.
        Erwartet events_by_year im Format {jahr: {datum: typ, ...}}.
        """
        success = True

        # HACK: Da diese Funktion nur zum Speichern verwendet wird,
        # löschen wir zuerst alle alten Termine (vereinfachte Logik).
        # In einer Produktions-App würde man hier gezielter mit Update/Insert arbeiten.

        # 1. Alle vorhandenen Termine aus der DB holen
        all_existing_appointments = get_special_appointments()

        # 2. Bestehende Termine löschen, die nicht mehr in events_by_year enthalten sind (komplex, daher vereinfacht):
        # Wir setzen alle Termine des aktuellen Jahres als neu zu speichernde Daten.

        # Einfachere Logik: Alle des Jahres löschen und neu speichern:

        # Wir iterieren durch das gesamte Set und speichern neu, da die DB die Duplikatprüfung übernimmt.
        for year, year_events in events_by_year.items():
            for date_str, appointment_type in year_events.items():
                if not save_special_appointment(date_str, appointment_type, description=""):
                    success = False

        if success:
            return True, "Termine erfolgreich in der Datenbank gespeichert."
        else:
            return False, "Fehler beim Speichern der Termine in der Datenbank."

    @staticmethod
    def get_events_for_year(year):
        """
        Holt alle Sondertermine aus der Datenbank und filtert nach Jahr.
        Gibt die Daten im erwarteten Format {datum: typ, ...} zurück.
        """
        all_appointments = get_special_appointments()

        # Konvertierung des DB-Formats (Liste von Dicts) in das GUI-Format ({date_str: type})
        events_of_year = {}
        target_year_str = str(year)

        for appt in all_appointments:
            appt_date_str = appt['appointment_date']

            # Filterung nach dem angefragten Jahr
            if appt_date_str and appt_date_str.startswith(target_year_str):
                events_of_year[appt_date_str] = appt['appointment_type']

        return events_of_year

    @staticmethod
    def get_event_type(current_date, events_of_year):
        """
        Sucht den Event-Typ für ein gegebenes Datum.
        """
        date_str = current_date.strftime('%Y-%m-%d')
        return events_of_year.get(date_str)

    @staticmethod
    def delete_events_for_year(year):
        """
        Löscht alle Termine eines Jahres in der Datenbank.
        """
        appointments_to_delete = EventManager.get_events_for_year(year)

        success = True
        for date_str, appt_type in appointments_to_delete.items():
            if not delete_special_appointment(date_str, appt_type):
                success = False

        return success, "Termine erfolgreich gelöscht." if success else "Fehler beim Löschen der Termine."