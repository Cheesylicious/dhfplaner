# gui/shift_lock_manager.py
from database.db_locks import get_locked_shifts_for_month, set_shift_lock_status
from datetime import date


class ShiftLockManager:
    """
    Verwaltet den Cache und den Status gesicherter Schichten.
    Diese Schichten dürfen vom Generator nicht angetastet werden.
    """

    def __init__(self, app):
        self.app = app
        self._locked_shifts_cache = {}  # {user_id_str: {date_str: shift_abbrev}}
        self._current_year = None
        self._current_month = None

    def load_locks(self, year, month):
        """Lädt die Locks für den gegebenen Monat aus der Datenbank und aktualisiert den Cache."""
        if self._current_year == year and self._current_month == month:
            return self._locked_shifts_cache

        print(f"[ShiftLockManager] Lade Locks für {year}-{month} neu...")
        try:
            self._locked_shifts_cache = get_locked_shifts_for_month(year, month)
            self._current_year = year
            self._current_month = month
        except Exception as e:
            print(f"[FEHLER] Konnte Shift Locks nicht laden: {e}")
            self._locked_shifts_cache = {}

        return self._locked_shifts_cache

    def get_lock_status(self, user_id_str, date_str):
        """Gibt die gesicherte Schicht (abbrev) oder None zurück."""
        return self._locked_shifts_cache.get(user_id_str, {}).get(date_str)

    def set_lock_status(self, user_id, date_str, shift_abbrev, is_locked, admin_id):
        """
        Setzt den Lock-Status in der Datenbank und aktualisiert den lokalen Cache.
        """
        success, message = set_shift_lock_status(user_id, date_str, shift_abbrev, is_locked, admin_id)

        if success:
            user_id_str = str(user_id)
            if is_locked:
                # Füge zum Cache hinzu
                if user_id_str not in self._locked_shifts_cache:
                    self._locked_shifts_cache[user_id_str] = {}
                self._locked_shifts_cache[user_id_str][date_str] = shift_abbrev
            else:
                # Entferne aus dem Cache
                if user_id_str in self._locked_shifts_cache and date_str in self._locked_shifts_cache[user_id_str]:
                    del self._locked_shifts_cache[user_id_str][date_str]

            return True, message

        return False, message
