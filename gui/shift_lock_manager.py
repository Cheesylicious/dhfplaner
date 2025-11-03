# gui/shift_lock_manager.py
from datetime import date, datetime
from database.db_locks import (set_shift_lock_status as db_set_lock,
                               get_locked_shifts_for_month,
                               delete_all_locks_for_month)


# HINWEIS: Diese Klasse verwaltet NICHT mehr ihren eigenen Cache.
# Sie agiert als Schnittstelle zur DB und zum Cache des DataManagers.

class ShiftLockManager:
    """
    Verwaltet die Aktionen zum Sichern/Freigeben von Schichten.
    Greift für den Cache-Status direkt auf den ShiftPlanDataManager zu.
    """

    def __init__(self, app, data_manager):
        """
        Initialisiert den Manager.

        Args:
            app: Die Haupt-App-Instanz.
            data_manager: Die Instanz des ShiftPlanDataManager, die den Cache hält.
        """
        self.app = app
        # Der DataManager verwaltet den Cache für die Locks
        self.data_manager = data_manager
        # self.locked_shifts = {}  <-- ENTFERNT!

    def set_lock_status(self, user_id, date_str, shift_abbrev, is_locked, admin_id):
        """
        Speichert den Lock-Status in der DB UND aktualisiert den Cache
        im DataManager.
        """
        user_id_str = str(user_id)

        # 1. DB-Aufruf
        success, message = db_set_lock(user_id, date_str, shift_abbrev, is_locked, admin_id)

        if success:
            # 2. Cache im DataManager direkt aktualisieren
            # Wir greifen auf self.data_manager.locked_shifts_cache zu
            try:
                if is_locked:
                    if user_id_str not in self.data_manager.locked_shifts_cache:
                        self.data_manager.locked_shifts_cache[user_id_str] = {}
                    self.data_manager.locked_shifts_cache[user_id_str][date_str] = shift_abbrev
                    # Diese Meldung sollte jetzt das korrekte Verhalten widerspiegeln
                    print(
                        f"[ShiftLockManager] DataManager-Cache Update: Lock hinzugefügt für U{user_id_str} an {date_str} -> {shift_abbrev}")
                else:
                    if user_id_str in self.data_manager.locked_shifts_cache and date_str in \
                            self.data_manager.locked_shifts_cache[user_id_str]:
                        del self.data_manager.locked_shifts_cache[user_id_str][date_str]
                        if not self.data_manager.locked_shifts_cache[user_id_str]:
                            del self.data_manager.locked_shifts_cache[user_id_str]
                    print(
                        f"[ShiftLockManager] DataManager-Cache Update: Lock entfernt für U{user_id_str} an {date_str}")

                # 3. P5-Cache des DataManagers invalidieren (entscheidend!)
                lock_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if hasattr(self.data_manager, 'invalidate_month_cache'):
                    self.data_manager.invalidate_month_cache(lock_date.year, lock_date.month)
                else:
                    print("[FEHLER] ShiftLockManager konnte P5-Cache nicht invalidieren!")

            except Exception as e:
                print(f"[FEHLER] Fehler beim Aktualisieren des Lock-Cache im DataManager: {e}")
                # DB-Aufruf war erfolgreich, aber Cache ist inkonsistent
                return False, f"DB Erfolg, aber Cache-Fehler: {e}"

        return success, message

    def get_lock_status(self, user_id, date_str):
        """
        Holt den Lock-Status direkt aus dem Cache des DataManagers.
        """
        user_id_str = str(user_id)
        # Greift auf den Cache im DataManager zu
        if not hasattr(self.data_manager, 'locked_shifts_cache'):
            print("[FEHLER] DataManager hat keinen locked_shifts_cache!")
            return None

        return self.data_manager.locked_shifts_cache.get(user_id_str, {}).get(date_str)

    def get_locks_for_month_from_db(self, year, month):
        """
        (Wird nicht mehr primär genutzt)
        Holt alle gesicherten Schichten für den gegebenen Monat direkt aus der DB.
        """
        return get_locked_shifts_for_month(year, month)

    def delete_all_locks_for_month(self, year, month, admin_id):
        """
        Löscht alle Locks in der DB und invalidiert die Caches im DataManager.
        (Wird von ShiftPlanActionHandler aufgerufen)
        """
        success, message = delete_all_locks_for_month(year, month, admin_id)

        if success:
            # Cache im DataManager leeren (falls dieser Monat geladen ist)
            if self.data_manager.year == year and self.data_manager.month == month:
                if hasattr(self.data_manager, 'locked_shifts_cache'):
                    self.data_manager.locked_shifts_cache.clear()
                    print(f"[ShiftLockManager] DM-Cache für {year}-{month} nach globalem Unlock geleert.")

            # P5-Cache invalidieren
            if hasattr(self.data_manager, 'invalidate_month_cache'):
                self.data_manager.invalidate_month_cache(year, month)

        return success, message