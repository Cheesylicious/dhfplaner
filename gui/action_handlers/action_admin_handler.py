# gui/action_handlers/action_admin_handler.py
# NEU: Ausgelagerte Logik für globale Admin-Aktionen (Plan löschen) (Regel 4)
#
# --- INNOVATION (Regel 2): Latenz behoben ---
# Die synchronen (blockierenden) DB-Aufrufe 'delete_all_shifts_for_month'
# und 'delete_all_locks_for_month' wurden in Hintergrund-Threads ausgelagert.
# Der Handler verwendet jetzt 'self.tab.show_progress_widgets', um die
# UI-Latenz zu eliminieren und dem Benutzer Feedback zu geben.

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
import threading  # NEU: Für asynchrone Operationen

# DB-Importe
from database.db_shifts import delete_all_shifts_for_month
from database.db_locks import delete_all_locks_for_month


class ActionAdminHandler:
    """
    Verantwortlich für globale Admin-Aktionen, die den
    gesamten Schichtplan betreffen (z.B. Löschen, alle Locks aufheben).
    """

    def __init__(self, tab, app_instance, renderer, data_manager):
        # self.tab ist die Instanz von ShiftPlanTab
        self.tab = tab
        self.app = app_instance
        self.renderer = renderer
        self.dm = data_manager  # DataManager (wird für Invalidate benötigt)

    # --- 1. PLAN LÖSCHEN (ASYNCHRON) ---

    def delete_shift_plan_by_admin(self, year, month):
        """
        Fragt den Benutzer (synchron), startet dann aber den Löschvorgang
        asynchron in einem Thread (Regel 2).
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

        # --- INNOVATION (Regel 2) ---
        # Zeige Ladebalken im ShiftPlanTab
        try:
            self.tab.show_progress_widgets(text="Plan-Daten werden gelöscht...")
        except AttributeError:
            print("[ActionAdmin] Warnung: 'show_progress_widgets' nicht in self.tab gefunden.")

        # Starte den langsamen DB-Aufruf in einem Worker-Thread
        threading.Thread(
            target=self._task_delete_plan,
            args=(year, month, current_admin_id),
            daemon=True
        ).start()
        # --- ENDE INNOVATION ---

    def _task_delete_plan(self, year, month, current_admin_id):
        """
        (Worker-Thread) Führt die langsame Datenbankoperation zum Löschen aus.
        """
        try:
            success, message = delete_all_shifts_for_month(year, month, current_admin_id)
        except Exception as e:
            success = False
            message = f"Unerwarteter Fehler im Lösch-Thread: {e}"

        # Sende das Ergebnis zurück an den Haupt-Thread
        self.tab.after(0, self._on_delete_plan_complete, year, month, success, message)

    def _on_delete_plan_complete(self, year, month, success, message):
        """
        (Main-Thread) Callback nach Abschluss des Lösch-Threads.
        Versteckt den Ladebalken, zeigt das Ergebnis an und lädt die UI neu.
        """
        try:
            self.tab.hide_progress_widgets()
        except AttributeError:
            pass  # Ignorieren, falls nicht gefunden

        if success:
            messagebox.showinfo("Erfolg", message)

            # P5-Cache invalidieren (WICHTIG!)
            if hasattr(self.dm, 'invalidate_month_cache'):
                print(f"[ActionAdmin] Invalidiere DM-Cache für {year}-{month} nach Löschung.")
                self.dm.invalidate_month_cache(year, month)

            # UI neu laden
            if hasattr(self.tab, 'build_shift_plan_grid'):
                self.tab.build_shift_plan_grid(year, month)
            else:
                self.tab.refresh_plan()  # Fallback
        else:
            messagebox.showerror("Fehler", f"Fehler beim Löschen des Plans:\n{message}")

    # --- 2. ALLE LOCKS AUFHEBEN (ASYNCHRON) ---

    def unlock_all_shifts_for_month(self, year, month):
        """
        Hebt alle Schichtsicherungen (Locks) asynchron auf (Regel 2).
        """
        admin_id = getattr(self.app, 'current_user_id', None)
        if not admin_id:
            messagebox.showerror("Fehler", "Admin-ID nicht gefunden. Aktion kann nicht geloggt werden.",
                                 parent=self.tab)
            return

        # Sicherheitsabfrage (NEU, aber empfohlen)
        if not messagebox.askyesno(
                "Alle Sicherungen aufheben",
                f"Wollen Sie wirklich ALLE Schichtsicherungen (Locks) für {month:02d}/{year} aufheben?\n\nDies betrifft alle Benutzer."
        ):
            return

        if not hasattr(self.dm, 'shift_lock_manager'):
            messagebox.showerror("Fehler", "ShiftLockManager nicht im DataManager gefunden.", parent=self.tab)
            return

        # --- INNOVATION (Regel 2) ---
        # Zeige Ladebalken
        try:
            self.tab.show_progress_widgets(text="Alle Sicherungen werden aufgehoben...")
        except AttributeError:
            print("[ActionAdmin] Warnung: 'show_progress_widgets' nicht in self.tab gefunden.")

        # Starte den langsamen DB-Aufruf in einem Worker-Thread
        threading.Thread(
            target=self._task_unlock_all,
            args=(year, month, admin_id),
            daemon=True
        ).start()
        # --- ENDE INNOVATION ---

    def _task_unlock_all(self, year, month, admin_id):
        """
        (Worker-Thread) Führt die langsame DB-Operation zum Löschen
        aller Locks aus.
        """
        try:
            # Der LockManager kümmert sich um DB-Aufruf UND Cache-Invalidierung
            success, message = self.dm.shift_lock_manager.delete_all_locks_for_month(year, month, admin_id)
        except Exception as e:
            success = False
            message = f"Unerwarteter Fehler im Unlock-Thread: {e}"

        # Sende das Ergebnis zurück an den Haupt-Thread
        self.tab.after(0, self._on_unlock_all_complete, year, month, success, message)

    def _on_unlock_all_complete(self, year, month, success, message):
        """
        (Main-Thread) Callback nach Abschluss des Unlock-All-Threads.
        """
        try:
            self.tab.hide_progress_widgets()
        except AttributeError:
            pass

        if success:
            messagebox.showinfo("Erfolg", message, parent=self.tab)

            # 3. UI komplett neu laden, um alle Lock-Icons zu entfernen
            if hasattr(self.tab, 'build_shift_plan_grid'):
                self.tab.build_shift_plan_grid(year, month)
            else:
                self.tab.refresh_plan()  # Fallback
        else:
            messagebox.showerror("Fehler", f"Fehler beim Aufheben der Sicherungen:\n{message}", parent=self.tab)