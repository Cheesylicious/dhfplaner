# gui/shift_lock_manager.py
from database.db_locks import get_locked_shifts_for_month, set_shift_lock_status
# --- KORREKTUR: Import für defaultdict und calendar hinzugefügt ---
from collections import defaultdict
import calendar
# --- ENDE KORREKTUR ---
from datetime import date


class ShiftLockManager:
    """
    Verwaltet den Cache und den Status gesicherter Schichten.
    Diese Schichten dürfen vom Generator nicht angetastet werden.
    """

    def __init__(self, app):
        self.app = app
        self._locked_shifts_cache = {}  # {user_id_str: {date_str: shift_abbrev}}
        # --- KORREKTUR: current_year/month entfernt, wird nicht mehr benötigt ---
        # self._current_year = None
        # self._current_month = None
        # --- ENDE KORREKTUR ---

    def load_locks(self, year, month):
        """Lädt die Locks für den gegebenen Monat IMMER neu aus der Datenbank und aktualisiert den Cache."""
        # --- KORREKTUR: Cache-Prüfung entfernt ---
        # if self._current_year == year and self._current_month == month:
        #     return self._locked_shifts_cache
        # --- ENDE KORREKTUR ---

        print(f"[ShiftLockManager] Lade Locks für {year}-{month} neu...")
        try:
            # Holt die Daten IMMER neu aus der Datenbank
            self._locked_shifts_cache = get_locked_shifts_for_month(year, month)
            # --- KORREKTUR: Setzen von current_year/month entfernt ---
            # self._current_year = year
            # self._current_month = month
            # --- ENDE KORREKTUR ---
        except Exception as e:
            print(f"[FEHLER] Konnte Shift Locks nicht laden: {e}")
            self._locked_shifts_cache = {} # Bei Fehler leeren Cache setzen

        return self._locked_shifts_cache

    def get_lock_status(self, user_id_str, date_str):
        """Gibt die gesicherte Schicht (abbrev) oder None zurück."""
        # Stellt sicher, dass user_id_str ein String ist
        user_id_str = str(user_id_str)
        return self._locked_shifts_cache.get(user_id_str, {}).get(date_str)

    def set_lock_status(self, user_id, date_str, shift_abbrev, is_locked, admin_id):
        """
        Setzt den Lock-Status in der Datenbank und aktualisiert den lokalen Cache.
        """
        success, message = set_shift_lock_status(user_id, date_str, shift_abbrev, is_locked, admin_id)

        if success:
            user_id_str = str(user_id)
            # --- Cache-Aktualisierung bleibt ---
            if is_locked:
                # Füge zum Cache hinzu
                if user_id_str not in self._locked_shifts_cache:
                    self._locked_shifts_cache[user_id_str] = {}
                self._locked_shifts_cache[user_id_str][date_str] = shift_abbrev
                print(f"[ShiftLockManager] Cache Update: Lock hinzugefügt für U{user_id_str} an {date_str} -> {shift_abbrev}")
            else:
                # Entferne aus dem Cache
                if user_id_str in self._locked_shifts_cache and date_str in self._locked_shifts_cache[user_id_str]:
                    del self._locked_shifts_cache[user_id_str][date_str]
                    # Wenn der User keine Locks mehr hat, entferne den User-Eintrag
                    if not self._locked_shifts_cache[user_id_str]:
                        del self._locked_shifts_cache[user_id_str]
                    print(f"[ShiftLockManager] Cache Update: Lock entfernt für U{user_id_str} an {date_str}")
            # --- Ende Cache-Aktualisierung ---

            return True, message

        return False, message

    # --- Hinzugefügte Methode, um den Cache gezielt zu leeren (optional, aber gut für Tests) ---
    def clear_cache(self):
        """Leert den internen Cache für Schichtsicherungen."""
        print("[ShiftLockManager] Cache wird geleert.")
        self._locked_shifts_cache = {}