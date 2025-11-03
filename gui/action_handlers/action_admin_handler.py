# gui/action_handlers/action_admin_handler.py
# NEU: Ausgelagerte Logik für globale Admin-Aktionen (Plan löschen) (Regel 4)

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

# DB-Importe
from database.db_shifts import delete_all_shifts_for_month
from database.db_locks import delete_all_locks_for_month


class ActionAdminHandler:
    """
    Verantwortlich für globale Admin-Aktionen, die den
    gesamten Schichtplan betreffen (z.B. Löschen, alle Locks aufheben).
    """

    def __init__(self, tab, app_instance, renderer, data_manager):
        self.tab = tab
        self.app = app_instance
        self.renderer = renderer
        self.dm = data_manager  # DataManager (wird für Invalidate benötigt)

    def delete_shift_plan_by_admin(self, year, month):
        """
        Fragt den Benutzer, ob der Schichtplan gelöscht werden soll und ruft die
        DB-Funktion auf, die bestimmte Schichten ausschließt.
        """
        try:
            excluded_shifts_str = ", ".join(delete_all_shifts_for_month.EXCLUDED_SHIFTS_ON_DELETE)
        except AttributeError:
            excluded_shifts_str = "X, S, QA, EU, WF"  # Fallback

        if not messagebox.askyesno(
                "Schichtplan löschen",
                f"Wollen Sie alle planbaren Schichten für {month:02d}/{year} wirklich löschen?\n\n"
                f"ACHTUNG: Genehmigte Schichten/Termine wie Urlaube, Wünsche und fixe Einträge "
                f"({excluded_shifts_str}) sowie Urlaubs- und Wunschanfragen werden NICHT gelöscht!"
        ):
            return

        current_admin_id = getattr(self.app, 'current_user_id', None)
        if not current_admin_id:
            messagebox.showerror("Fehler", "Admin-ID nicht gefunden. Aktion kann nicht geloggt werden.",
                                 parent=self.tab)
            return

        success, message = delete_all_shifts_for_month(year, month, current_admin_id)

        if success:
            messagebox.showinfo("Erfolg", message)

            # P5-Cache invalidieren (WICHTIG!)
            if hasattr(self.dm, 'invalidate_month_cache'):
                print(f"[ActionAdmin] Invalidiere DM-Cache für {year}-{month} nach Löschung.")
                self.dm.invalidate_month_cache(year, month)
            else:
                print("[WARNUNG] DataManager oder invalidate_month_cache nicht gefunden. Cache nicht invalidiert.")

            # UI neu laden
            if hasattr(self.tab, 'build_shift_plan_grid'):
                self.tab.build_shift_plan_grid(year, month)
            else:
                self.tab.refresh_plan()  # Fallback
        else:
            messagebox.showerror("Fehler", f"Fehler beim Löschen des Plans:\n{message}")

    def unlock_all_shifts_for_month(self, year, month):
        """
        Hebt alle Schichtsicherungen (Locks) für den angegebenen Monat auf.
        """
        admin_id = getattr(self.app, 'current_user_id', None)
        if not admin_id:
            messagebox.showerror("Fehler", "Admin-ID nicht gefunden. Aktion kann nicht geloggt werden.",
                                 parent=self.tab)
            return

        # 1. DB-Aufruf (geht jetzt über den shift_lock_manager, der den Cache-Clear handhabt)
        if not hasattr(self.dm, 'shift_lock_manager'):
            messagebox.showerror("Fehler", "ShiftLockManager nicht im DataManager gefunden.", parent=self.tab)
            return

        # Der LockManager kümmert sich um DB-Aufruf UND Cache-Invalidierung
        success, message = self.dm.shift_lock_manager.delete_all_locks_for_month(year, month, admin_id)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self.tab)

            # 3. UI komplett neu laden, um alle Lock-Icons zu entfernen
            if hasattr(self.tab, 'build_shift_plan_grid'):
                self.tab.build_shift_plan_grid(year, month)
            else:
                self.tab.refresh_plan()  # Fallback
        else:
            messagebox.showerror("Fehler", f"Fehler beim Aufheben der Sicherungen:\n{message}", parent=self.tab)