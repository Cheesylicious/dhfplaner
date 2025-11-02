# gui/holiday_manager.py
import os
import json
from datetime import date, datetime
from database.db_core import create_connection, save_config_json, load_config_json
import mysql.connector

# --- NEU: Import für die automatische Feiertagsgenerierung ---
# (Stellen Sie sicher, dass 'holidays' installiert ist: pip install holidays)
try:
    import holidays
except ImportError:
    print("[FEHLER] 'holidays'-Bibliothek nicht gefunden. Automatische Feiertagsgenerierung schlägt fehl.")
    print("Bitte installieren Sie sie: pip install holidays")
    holidays = None
# -------------------------------------------------------------

# Globaler Cache (unverändert)
_holidays_cache = {}

# Der Dateiname der alten JSON-Datei (nur für Migration)
HOLIDAY_JSON_FILE = 'holidays.json'


class HolidayManager:
    """
    Verwaltet Feiertage durch Laden und Speichern in der Datenbank (config_storage).
    NEU: Generiert automatisch fehlende Feiertage für Mecklenburg-Vorpommern (MV).
    """

    CONFIG_KEY = "HOLIDAYS_NEW"
    STATE_CODE = "MV"  # Bundesland-Code für 'holidays'-Bibliothek (Mecklenburg-Vorpommern)

    @staticmethod
    def _generate_holidays_for_year(year_int):
        """
        NEUE FUNKTION: Generiert Feiertage für MV für ein bestimmtes Jahr.
        """
        if holidays is None:
            print(f"[FEHLER] 'holidays'-Bibliothek fehlt. Kann Feiertage für {year_int} nicht generieren.")
            return {}

        try:
            # Nutzt die 'holidays'-Bibliothek für Deutschland (DE) und das Bundesland (STATE_CODE)
            mv_holidays = holidays.DE(state=HolidayManager.STATE_CODE, years=year_int)
            year_data = {}
            for date_obj, name in mv_holidays.items():
                year_data[date_obj.strftime('%Y-%m-%d')] = name

            print(
                f"[HolidayManager] {len(year_data)} Feiertage für {year_int} ({HolidayManager.STATE_CODE}) erfolgreich generiert.")
            return year_data
        except Exception as e:
            print(f"[FEHLER] Bei der Generierung der Feiertage für {year_int}: {e}")
            return {}

    @staticmethod
    def _migrate_json_to_db():
        """
        Versucht, die alte holidays.json-Datei zu lesen und in die Datenbank
        zu migrieren.
        KORREKTUR: Speichert KEINEN leeren Eintrag mehr, wenn die Datei fehlt.
        """
        print(f"[Migration] Prüfe auf alte {HOLIDAY_JSON_FILE}...")
        all_holidays = {}  # Beginne mit einem leeren Diktat

        # Pfad relativ zu dieser Datei finden
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, HOLIDAY_JSON_FILE)

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    all_holidays = json.load(f)
                print(f"[Migration] Alte {HOLIDAY_JSON_FILE} gefunden. Migriere nach DB...")

                # Ruft die save_holidays-Methode auf (leert auch den Cache)
                if HolidayManager.save_holidays(all_holidays):
                    print(f"[Migration] Erfolgreich zu DB-Key '{HolidayManager.CONFIG_KEY}' migriert.")
                    os.rename(json_path, json_path + '.migrated')
                    print(f"[Migration] Alte Datei zu '{json_path}.migrated' umbenannt.")
                else:
                    print(f"[Migration] FEHLER beim Speichern der migrierten Daten in der DB.")
            except (IOError, json.JSONDecodeError) as e:
                print(f"[Migration] FEHLER beim Lesen der {HOLIDAY_JSON_FILE}: {e}")
        else:
            print(f"[Migration] Keine alte {HOLIDAY_JSON_FILE} gefunden. Starte mit leerer Konfiguration.")
            # --- KORREKTUR: "POISON PILL" ENTFERNT ---
            # Das Speichern eines leeren Eintrags wird verhindert.
            # save_config_json(HolidayManager.CONFIG_KEY, {}) # ENTFERNT
            # --- ENDE KORREKTUR ---

        return all_holidays  # Gibt {} zurück, wenn nichts gefunden wurde, sonst den Inhalt der JSON

    @staticmethod
    def get_holidays_for_year(year_int):
        """
        Gibt ein Dictionary der Feiertage für ein bestimmtes Jahr zurück.
        Format: {"YYYY-MM-DD": "Feiertagsname"}
        NEU: Generiert das Jahr automatisch, falls es in der DB fehlt.
        """
        global _holidays_cache
        year_str = str(year_int)

        # 1. Prüfe den Cache (Unverändert)
        if year_str in _holidays_cache:
            # print(f"[DEBUG] Lade Feiertage für {year_str} aus dem Cache.") # <--- KORREKTUR: Entfernt redundantes Logging (Regel 2)
            return _holidays_cache[year_str]

        # 2. Lade aus DB (Unverändert)
        print(f"[DEBUG] Lade Feiertage für {year_str} aus der DB (Key: {HolidayManager.CONFIG_KEY}).")
        all_holidays = load_config_json(HolidayManager.CONFIG_KEY)

        # 3. KORRIGIERTE LOGIK: DB-Eintrag existiert nicht? -> Migration versuchen
        if all_holidays is None:
            print(
                f"[HolidayManager] DB-Key '{HolidayManager.CONFIG_KEY}' nicht gefunden. Versuche Migration von JSON...")
            all_holidays = HolidayManager._migrate_json_to_db()
            # all_holidays ist jetzt entweder {} (wenn keine JSON) oder {json_inhalt} (und wurde gespeichert)

        # 4. NEUE LOGIK: Prüfe, ob das JAHR im (geladenen oder migrierten) Diktat fehlt
        #    ODER ob der Eintrag für das Jahr leer ist (alte "Poison Pill")
        if year_str not in all_holidays or not all_holidays.get(year_str):
            if year_str in all_holidays and not all_holidays[year_str]:
                print(f"[HolidayManager] Leeren Eintrag für {year_str} gefunden. Überschreibe...")

            print(f"[HolidayManager] Feiertage für {year_str} nicht in DB/Migration gefunden. Generiere (MV)...")

            # Generiere die Daten für das fehlende Jahr
            year_holidays = HolidayManager._generate_holidays_for_year(year_int)

            # Füge die neuen Daten zur Gesamtstruktur hinzu
            all_holidays[year_str] = year_holidays

            print(f"[HolidayManager] Speichere aktualisierte Feiertage (inkl. {year_str}) in DB...")
            # Speichere die *gesamte* Struktur (inkl. neuer Daten) zurück in die DB
            if not HolidayManager.save_holidays(all_holidays):
                print(f"[FEHLER] Konnte neu generierte Feiertage für {year_str} nicht in DB speichern.")
                # (Fahre trotzdem fort, um die Daten zumindest im Cache zu haben)

        # 5. Das Jahr ist jetzt definitiv in all_holidays (entweder geladen or generiert)
        year_holidays = all_holidays.get(year_str, {})  # .get() zur Sicherheit

        # 6. Speichere im Cache und gib zurück
        _holidays_cache[year_str] = year_holidays
        return year_holidays

    @staticmethod
    def get_all_holidays():
        """Lädt alle Feiertage aus der DB. (Unverändert, aber profitiert von neuer Logik)"""
        all_holidays = load_config_json(HolidayManager.CONFIG_KEY)
        if all_holidays is None:
            all_holidays = HolidayManager._migrate_json_to_db()

        # --- NEU: Sicherstellen, dass das aktuelle Jahr geladen/generiert ist ---
        # Dies füllt das Fenster "Feiertage verwalten" beim ersten Öffnen
        current_year = date.today().year
        if all_holidays is None or str(current_year) not in all_holidays:
            print("[HolidayManager] get_all_holidays: Aktuelles Jahr fehlt, lade/generiere...")
            # Ruft get_holidays_for_year auf, was die Generierung und Speicherung auslöst
            # (und die Daten in all_holidays lädt)
            HolidayManager.get_holidays_for_year(current_year)
            # Lade die (jetzt aktualisierten) Daten erneut
            all_holidays = load_config_json(HolidayManager.CONFIG_KEY)

        if all_holidays is None: all_holidays = {}  # Fallback
        # --- ENDE NEU ---

        return all_holidays

    @staticmethod
    def save_holidays(all_holidays_data):
        """
        Speichert die komplette Feiertagsstruktur in der DB.
        Leert jetzt den globalen Cache. (Unverändert)
        """
        if save_config_json(HolidayManager.CONFIG_KEY, all_holidays_data):
            HolidayManager.clear_cache()
            return True
        return False

    @staticmethod
    def clear_cache():
        """Externe Methode, um den globalen Cache bei Bedarf zu leeren."""
        global _holidays_cache
        _holidays_cache.clear()
        print("[DEBUG] Feiertags-Cache (Global) geleert.")

    @staticmethod
    def is_holiday(date_obj):
        """
        Prüft, ob ein gegebenes date-Objekt ein Feiertag ist.
        (Profitiert jetzt von der automatischen Generierung)
        """
        global _holidays_cache
        if not isinstance(date_obj, date):
            try:
                # Versuch, das Objekt in ein Datum umzuwandeln (z.B. von datetime)
                date_obj = date_obj.date()
            except Exception:
                print(f"[FEHLER] is_holiday erhielt ungültiges Objekt: {type(date_obj)}")
                return False

        year_str = str(date_obj.year)
        date_str = date_obj.strftime('%Y-%m-%d')

        # 1. Prüfen, ob das Jahr bereits im Cache ist. Wenn nicht, laden.
        if year_str not in _holidays_cache:
            print(f"[HolidayManager] Lade Feiertage für {year_str} (on-demand für is_holiday).")
            # Ruft die STATISCHE Methode auf (die jetzt Ggf. generiert)
            HolidayManager.get_holidays_for_year(date_obj.year)

        # 2. Im Cache für das Jahr nach dem Datum-String suchen
        year_holidays = _holidays_cache.get(year_str, {})
        return date_str in year_holidays