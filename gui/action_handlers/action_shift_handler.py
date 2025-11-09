# gui/action_handlers/action_shift_handler.py
# NEU: Ausgelagerte Logik für Schicht- und Lock-Aktionen (Regel 4)
# KORRIGIERT (Regel 2): Speichern erfolgt jetzt asynchron (Optimistic UI Update),
# um UI-Lag zu verhindern.
# KORRIGIERT (AttributeError): Greift auf self.app.shift_frequency zu (nicht self.app.app)
#
# --- INNOVATION (Regel 2): Latenz beim Sperren behoben ---
# Die Methoden secure_shift und unlock_shift wurden ebenfalls
# auf asynchrones "Optimistic Update" umgestellt, um UI-Latenz
# bei langsamen Verbindungen zu eliminieren.

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
import threading  # NEU: Für asynchrones Speichern

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
        self.app = app_instance  # MainAdminWindow (hat .shift_frequency)
        self.renderer = renderer
        self.dm = data_manager
        self.updater = update_handler  # Referenz auf den ActionUpdateHandler

        # Direkter Zugriff auf den Lock Manager vom DataManager
        self.shift_lock_manager = self.dm.shift_lock_manager

    def save_shift_entry_and_refresh(self, user_id, date_str, shift_abbrev):
        """
        Speichert die Schicht ASYNCHRON und löst SOFORT gezielte UI-Updates aus
        (Optimistic UI Update, Regel 2).
        """
        print(f"[ActionShift] Optimistic UI Update: User {user_id}, Datum {date_str}, Schicht '{shift_abbrev}'")

        # Hole alten Schichtwert über den Update-Handler-Helfer
        old_shift_abbrev = self.updater.get_old_shift_from_ui(user_id, date_str)
        actual_shift_to_save = shift_abbrev if shift_abbrev else ""

        # Sicherheitsregel: Gesperrte Schichten nicht überschreiben/löschen
        lock_status = self.shift_lock_manager.get_lock_status(user_id, date_str)
        if lock_status and actual_shift_to_save != lock_status:
            messagebox.showwarning("Gesperrte Schicht",
                                   f"Diese Zelle ist als '{lock_status}' gesichert und kann nicht manuell geändert werden, bevor die Sicherung aufgehoben wird.",
                                   parent=self.tab)
            return

        # --- KORREKTUR (Regel 2): Asynchrone Ausführung ---

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

            # 1. OPTIMISTIC UI UPDATE (SOFORT)
            # Wir tun so, als ob die Speicherung erfolgreich war

            # Wunschfrei-Cache im DM leeren, wenn auf "FREI" gesetzt wird
            if actual_shift_to_save == "":
                if self.dm:
                    user_id_str = str(user_id)
                    if user_id_str in self.dm.wunschfrei_data and date_str in self.dm.wunschfrei_data[user_id_str]:
                        del self.dm.wunschfrei_data[user_id_str][date_str]
                        print(
                            f"[ActionShift] 'FREI' gesetzt: Wunschfrei-Cache für {user_id_str} am {date_str} geleert.")

            # 2. Trigger die ZENTRALE (schnelle) Update-Logik (via updater)
            self.updater.trigger_targeted_update(user_id, date_obj, old_shift_abbrev, actual_shift_to_save)

            # 3. Schichthäufigkeit in der App (UI-Cache) aktualisieren
            # --- KORREKTUR (AttributeError): .app.shift_frequency (nicht .app.app) ---
            if old_shift_abbrev and old_shift_abbrev in self.app.shift_frequency:
                self.app.shift_frequency[old_shift_abbrev] = max(0, self.app.shift_frequency[old_shift_abbrev] - 1)

            if actual_shift_to_save and actual_shift_to_save in self.app.app.shift_types_data and actual_shift_to_save not in [
                'U', 'X', 'EU']:
                # Sicherstellen, dass der Key existiert
                if actual_shift_to_save not in self.app.shift_frequency:
                    self.app.shift_frequency[actual_shift_to_save] = 0
                self.app.shift_frequency[actual_shift_to_save] += 1
            # --- ENDE KORREKTUR ---

            # 4. ASYNCHRONES SPEICHERN (Hintergrund)
            # Starte den DB-Aufruf in einem separaten Thread
            threading.Thread(
                target=self._save_shift_in_thread,
                args=(user_id, date_str, actual_shift_to_save, old_shift_abbrev, date_obj),
                daemon=True
            ).start()

        except ValueError:
            print(f"[FEHLER] Ungültiges Datum für Update-Trigger: {date_str}")
            messagebox.showerror("Fehler", "Interner Datumsfehler. UI wird nicht aktualisiert.", parent=self.tab)
        except Exception as e:
            print(f"[FEHLER] Kritischer Fehler im Optimistic UI Update: {e}")
            messagebox.showerror("Fehler", f"Fehler vor Speicherung:\n{e}", parent=self.tab)

    def _save_shift_in_thread(self, user_id, date_str, new_shift, old_shift, date_obj):
        """
        Führt den langsamen DB-Aufruf in einem Thread aus.
        Ruft im Fehlerfall ein Rollback auf.
        """
        success, message = save_shift_entry(user_id, date_str, new_shift)

        if not success:
            print(f"[FEHLER] Asynchrones Speichern fehlgeschlagen: {message}")
            # Sende den Fehler zurück an den Haupt-Thread (Tkinter)
            self.tab.after(0, self._handle_save_failure,
                           user_id, date_obj, new_shift, old_shift, message)

    def _handle_save_failure(self, user_id, date_obj, failed_new_shift, old_shift, error_message):
        """
        Wird im Haupt-Thread aufgerufen, wenn _save_shift_in_thread fehlschlägt.
        Führt ein UI-Rollback durch.
        """
        print(f"[ActionShift] ROLLBACK wird ausgeführt: '{failed_new_shift}' -> '{old_shift}'")
        messagebox.showerror("Speicherfehler (Rollback)",
                             f"Die Schicht '{failed_new_shift}' konnte nicht gespeichert werden.\n"
                             f"Fehler: {error_message}\n\n"
                             f"Die Ansicht wird auf '{old_shift}' zurückgesetzt.",
                             parent=self.tab)

        try:
            # 1. Trigger das Update zurück zum *alten* Wert
            self.updater.trigger_targeted_update(user_id, date_obj, failed_new_shift, old_shift)

            # 2. Schichthäufigkeit in der App (UI-Cache) zurücksetzen
            # --- KORREKTUR (AttributeError): .app.shift_frequency (nicht .app.app) ---
            if failed_new_shift and failed_new_shift in self.app.shift_frequency:
                self.app.shift_frequency[failed_new_shift] = max(0, self.app.shift_frequency[failed_new_shift] - 1)

            if old_shift and old_shift in self.app.app.shift_types_data and old_shift not in [
                'U', 'X', 'EU']:
                if old_shift not in self.app.shift_frequency:
                    self.app.shift_frequency[old_shift] = 0
                self.app.shift_frequency[old_shift] += 1
            # --- ENDE KORREKTUR ---

        except Exception as e:
            print(f"[FEHLER] KRITISCHER FEHLER im Rollback: {e}")
            messagebox.showerror("Kritischer Rollback-Fehler",
                                 f"Das Rollback ist fehlgeschlagen: {e}\n"
                                 "Die Ansicht ist möglicherweise nicht mehr synchron mit der Datenbank.\n"
                                 "Bitte laden Sie den Monat neu (z.B. Monat wechseln).",
                                 parent=self.tab)

    # --- METHODEN ZUM SICHERN VON SCHICHTEN (JETZT ASYNCHRON, Regel 2) ---

    def _set_shift_lock_status_async(self, user_id, date_str, shift_abbrev, is_locked):
        """
        Interne Hilfsfunktion, die den asynchronen DB-Aufruf startet
        und das UI-Rollback im Fehlerfall behandelt.
        """
        admin_id = getattr(self.app, 'user_id', None) or getattr(self.app, 'current_user_id', None)
        if not admin_id:
            messagebox.showerror("Fehler", "Admin-ID nicht verfügbar. Bitte melden Sie sich erneut an.",
                                 parent=self.tab)
            return

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messagebox.showerror("Fehler", f"Ungültiges Datum für Lock: {date_str}", parent=self.tab)
            return

        # 1. OPTIMISTIC UI UPDATE (SOFORT)
        # Wir aktualisieren den Lock-Status in der UI *sofort*.
        # (Wir müssen den DM-Cache hier nicht manuell aktualisieren,
        #  da der LockManager dies im Hintergrund tut und die UI
        #  sich (bisher) auf den Renderer verlässt)

        # Der Updater (ActionUpdateHandler) sollte eine Methode haben,
        # um den Lock-Status im DM *und* in der UI zu aktualisieren.
        # Wir nehmen an, der Renderer wird durch den Updater benachrichtigt,
        # oder wir rufen ihn direkt auf.

        # Wir rufen die UI-Update-Funktion des Renderers direkt auf.
        # (Dies ist der schnellste Weg, die UI zu aktualisieren)
        try:
            # Wir simulieren den neuen Status für das UI-Update
            # (Der LockManager muss den *echten* Cache im Hintergrund-Thread aktualisieren)

            # Temporäres Setzen im Cache für sofortige UI-Aktualisierung
            # (Der LockManager wird dies im Hintergrund-Thread überschreiben)
            self.shift_lock_manager.update_local_cache(user_id, date_str, shift_abbrev if is_locked else None)

            # UI sofort neu zeichnen
            self.renderer.update_cell_display(user_id, date_obj.day, date_obj)
            print(f"[ActionShift] Optimistic UI Lock Update für {user_id}@{date_str}")

        except Exception as e:
            print(f"[FEHLER] Fehler beim sofortigen Lock-UI-Update: {e}")
            # Bei Fehler UI nicht stoppen, DB-Aufruf trotzdem starten

        # 2. ASYNCHRONER DB-AUFRUF
        threading.Thread(
            target=self._lock_shift_in_thread,
            args=(user_id, date_str, shift_abbrev, is_locked, admin_id, date_obj),
            daemon=True
        ).start()

    def _lock_shift_in_thread(self, user_id, date_str, shift_abbrev, is_locked, admin_id, date_obj):
        """
        Worker-Thread: Führt den langsamen DB-Lock-Aufruf aus.
        """
        # Ruft die Methode im ShiftLockManager auf
        success, message = self.shift_lock_manager.set_lock_status(
            user_id, date_str, shift_abbrev, is_locked, admin_id
        )

        if not success:
            print(f"[FEHLER] Asynchrones Sichern/Freigeben fehlgeschlagen: {message}")
            # Sende den Fehler zurück an den Haupt-Thread (Tkinter) für UI-Rollback
            self.tab.after(0, self._handle_lock_failure,
                           user_id, date_obj, is_locked, message)

    def _handle_lock_failure(self, user_id, date_obj, failed_lock_state, error_message):
        """
        Wird im Haupt-Thread aufgerufen, wenn _lock_shift_in_thread fehlschlägt.
        Führt ein UI-Rollback für den Lock-Status durch.
        """
        action_str = "Sichern" if failed_lock_state else "Entsichern"
        print(f"[ActionShift] ROLLBACK für Lock-Status wird ausgeführt.")
        messagebox.showerror("Fehler beim Sichern (Rollback)",
                             f"Die Aktion '{action_str}' konnte nicht gespeichert werden.\n"
                             f"Fehler: {error_message}\n\n"
                             "Die Ansicht wird zurückgesetzt.",
                             parent=self.tab)

        try:
            # 1. Lokalen Cache zurücksetzen
            # (Wir müssen den *vorherigen* Status wiederherstellen.
            #  Das ist schwierig, ohne den alten Status zu speichern.
            #  Einfacher: Wir lesen den Status aus der DB neu,
            #  aber das wäre wieder ein blockierender Aufruf.)

            # Einfaches Rollback: Wir setzen den Cache auf den entgegengesetzten Status
            # (true -> false, false -> true)
            # Dies ist nicht perfekt, aber besser als ein inkonsistenter Zustand.

            # BESSERE LÖSUNG: Wir invalidieren den Cache und laden neu.
            # Für den Moment machen wir ein "best-effort" Rollback der UI:

            current_shift = self.dm.shift_schedule_data.get(str(user_id), {}).get(date_obj.strftime('%Y-%m-%d'))

            if failed_lock_state:
                # Sperren schlug fehl -> UI "entsperren"
                self.shift_lock_manager.update_local_cache(user_id, date_obj.strftime('%Y-%m-%d'), None)
            else:
                # Entsperren schlug fehl -> UI wieder "sperren"
                # (Wir nehmen an, die Schicht ist noch die, die gesperrt war)
                self.shift_lock_manager.update_local_cache(user_id, date_obj.strftime('%Y-%m-%d'), current_shift)

            # 2. UI neu zeichnen
            self.renderer.update_cell_display(user_id, date_obj.day, date_obj)

        except Exception as e:
            print(f"[FEHLER] KRITISCHER FEHLER im Lock-Rollback: {e}")
            messagebox.showerror("Kritischer Rollback-Fehler",
                                 f"Das Lock-Rollback ist fehlgeschlagen: {e}\n"
                                 "Die Ansicht ist möglicherweise nicht mehr synchron.\n"
                                 "Bitte laden Sie den Monat neu.",
                                 parent=self.tab)

    def secure_shift(self, user_id, date_str, shift_abbrev):
        """ Sichert die aktuelle Schicht (T., N., 6) - JETZT ASYNCHRON. """
        self._set_shift_lock_status_async(user_id, date_str, shift_abbrev, is_locked=True)

    def unlock_shift(self, user_id, date_str):
        """ Gibt die gesicherte Schicht frei - JETZT ASYNCHRON. """
        self._set_shift_lock_status_async(user_id, date_str, "", is_locked=False)