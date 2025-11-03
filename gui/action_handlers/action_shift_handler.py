# gui/action_handlers/action_shift_handler.py
# NEU: Ausgelagerte Logik für Schicht- und Lock-Aktionen (Regel 4)

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

# DB-Importe für Schichten und Locks
from database.db_shifts import save_shift_entry


# (Lock-DB-Aufrufe werden über den shift_lock_manager gehandhabt)

class ActionShiftHandler:
    """
    Verantwortlich für Aktionen, die Schichten direkt manipulieren:
    - Speichern / Auf "Frei" setzen
    - Schichten sichern (Lock)
    - Sicherung aufheben (Unlock)
    """

    def __init__(self, tab, app_instance, renderer, data_manager, update_handler):
        self.tab = tab
        self.app = app_instance
        self.renderer = renderer
        self.dm = data_manager
        self.updater = update_handler  # Referenz auf den ActionUpdateHandler

        # Direkter Zugriff auf den Lock Manager vom DataManager
        self.shift_lock_manager = self.dm.shift_lock_manager

    def save_shift_entry_and_refresh(self, user_id, date_str, shift_abbrev):
        """Speichert die Schicht und löst gezielte UI-Updates aus."""
        print(f"[ActionShift] Speichere: User {user_id}, Datum {date_str}, Schicht '{shift_abbrev}'")

        # Hole alten Schichtwert über den Update-Handler-Helfer
        old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)

        # 1. Speichern in DB
        actual_shift_to_save = shift_abbrev if shift_abbrev else ""

        # Sicherheitsregel: Gesperrte Schichten nicht überschreiben/löschen
        lock_status = self.shift_lock_manager.get_lock_status(user_id, date_str)
        if lock_status and actual_shift_to_save != lock_status:
            messagebox.showwarning("Gesperrte Schicht",
                                   f"Diese Zelle ist als '{lock_status}' gesichert und kann nicht manuell geändert werden, bevor die Sicherung aufgehoben wird.",
                                   parent=self.tab)
            return

        success, message = save_shift_entry(user_id, date_str, actual_shift_to_save)

        if success:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

                # Wunschfrei-Cache im DM leeren, wenn auf "FREI" gesetzt wird
                if actual_shift_to_save == "":
                    if self.dm:
                        user_id_str = str(user_id)
                        if user_id_str in self.dm.wunschfrei_data and date_str in self.dm.wunschfrei_data[user_id_str]:
                            del self.dm.wunschfrei_data[user_id_str][date_str]
                            print(
                                f"[ActionShift] 'FREI' gesetzt: Wunschfrei-Cache für {user_id_str} am {date_str} geleert.")

                # 2. Trigger die zentrale Update-Logik (via updater)
                self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, actual_shift_to_save)

            except ValueError:
                print(f"[FEHLER] Ungültiges Datum für Update-Trigger: {date_str}")
                messagebox.showerror("Fehler", "Interner Datumsfehler. UI wird nicht aktualisiert.", parent=self.tab)

            except Exception as e:
                print(f"[FEHLER] Fehler nach DB-Speicherung in save_shift_entry_and_refresh: {e}")
                messagebox.showerror("Fehler", f"Fehler nach Speicherung:\n{e}", parent=self.tab)

            # 3. Schichthäufigkeit in der App aktualisieren
            if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency:
                self.app.shift_frequency[old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)

            if actual_shift_to_save and actual_shift_to_save in self.app.shift_types_data and actual_shift_to_save not in [
                'U', 'X', 'EU']:
                # Sicherstellen, dass der Key existiert
                if actual_shift_to_save not in self.app.shift_frequency:
                    self.app.shift_frequency[actual_shift_to_save] = 0
                self.app.shift_frequency[actual_shift_to_save] += 1
        else:
            messagebox.showerror("Speicherfehler", message, parent=self.tab)

    # --- METHODEN ZUM SICHERN VON SCHICHTEN ---

    def _set_shift_lock_status(self, user_id, date_str, shift_abbrev, is_locked):
        """ Allgemeine Hilfsfunktion zum Sichern/Freigeben von Schichten. """
        admin_id = getattr(self.app, 'user_id', None) or getattr(self.app, 'current_user_id', None)

        if not admin_id:
            messagebox.showerror("Fehler", "Admin-ID nicht verfügbar. Bitte melden Sie sich erneut an.",
                                 parent=self.tab)
            return

        # Ruft die Methode im ShiftLockManager auf (der den DM-Cache aktualisiert)
        success, message = self.shift_lock_manager.set_lock_status(user_id, date_str, shift_abbrev, is_locked, admin_id)

        if success:
            # Führt ein UI-Update durch, um die Lock-Indikatoren anzuzeigen
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                # update_cell_display wird vom Renderer aufgerufen
                self.renderer.update_cell_display(user_id, date_obj.day, date_obj)
            except Exception as e:
                print(f"[FEHLER] Fehler bei UI-Update nach Lock-Status-Änderung: {e}")
                if hasattr(self.tab, 'refresh_plan'):
                    self.tab.refresh_plan()
        else:
            print(f"[FEHLER] Schicht sichern/freigeben fehlgeschlagen: {message}")

    def secure_shift(self, user_id, date_str, shift_abbrev):
        """ Sichert die aktuelle Schicht (T., N., 6). """
        self._set_shift_lock_status(user_id, date_str, shift_abbrev, is_locked=True)

    def unlock_shift(self, user_id, date_str):
        """ Gibt die gesicherte Schicht frei. """
        self._set_shift_lock_status(user_id, date_str, "", is_locked=False)