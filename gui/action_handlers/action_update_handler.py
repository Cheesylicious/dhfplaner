# gui/action_handlers/action_update_handler.py
#
# --- INNOVATION (Regel 2): Latenz beim Anzeigen von 'T.' final behoben ---
# Das Problem war, dass alle "schnellen" synchronen Updates (Cache,
# Stunden-UI, Tageszähl-UI) den Hauptthread blockiert haben, *bevor*
# Tkinter die Zelle ('T.') neu zeichnen konnte.
#
# LÖSUNG (Radikale Priorisierung):
# 1. Die Funktion wird komplett neu strukturiert.
# 2. ZUERST wird *nur* der Daten-Cache aktualisiert und die Zelle
#    gezeichnet (update_cell_display).
# 3. DANN wird Tkinter mit self.tab.update_idletasks() gezwungen,
#    diesen Frame *sofort* anzuzeigen. (DAS IST DER FIX)
# 4. ERST DANACH werden alle anderen Updates (Stunden-UI, Tageszähl-UI,
#    asynchrone Jobs) ausgeführt, jetzt, da der Benutzer 'T.' sieht.

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
import threading
from typing import List
import queue  # Beibehalten für Konflikt-Prüfung

# (Konstanten für Debouncing/Queueing bleiben unverändert)
CONFLICT_DEBOUNCE_TIME_MS = 300

# (Regel 2) Zeit für gebündelte sekundäre UI-Updates (Stunden, Zähler, Layout)
SECONDARY_UI_DEBOUNCE_MS = 100


class ActionUpdateHandler:
    """
    Kapselt die zentrale Update-Logik (_trigger_targeted_update)
    und die dazughörigen UI/DM-Helfer.
    """

    def __init__(self, tab, renderer, data_manager):
        self.tab = tab  # Referenz auf den Haupt-Tab (ShiftPlanTab)
        self.renderer = renderer
        self.dm = data_manager

        # --- System 1 (Konflikte): Producer/Consumer Queue ---
        # (Dies ist Ihre bereits implementierte Lösung aus dem letzten Schritt,
        #  sie ist gut und bleibt bestehen, um den "Thread-Sturm" zu verhindern)
        self.conflict_check_queue = queue.Queue()
        self.start_conflict_worker_thread()

        # --- System 2 (Layout & Sekundäre UI): Debouncer ---
        # (Dies behebt die Latenz beim Sehen von 'T.')
        self.secondary_ui_timer_id = None  # Speichert die ID des .after-Jobs
        self.secondary_ui_tasks = set()  # (NEU) Sammelt UI-Aufgaben für den Debouncer

    # --- System 1: Konflikt-Worker (Unverändert) ---
    def start_conflict_worker_thread(self):
        """ Startet den einzelnen, langlebigen Worker-Thread (Consumer). """
        print("[ActionUpdateHandler] Starte permanenten Konflikt-Worker-Thread...")
        worker_thread = threading.Thread(
            target=self._conflict_worker_loop,
            daemon=True
        )
        worker_thread.start()

    def _conflict_worker_loop(self):
        """ (Worker-Thread) Wartet auf Konflikt-Aufgaben und bündelt sie. """
        while True:
            try:
                first_task = self.conflict_check_queue.get()
                batch_to_process = [first_task]

                while not self.conflict_check_queue.empty():
                    try:
                        batch_to_process.append(self.conflict_check_queue.get_nowait())
                    except queue.Empty:
                        break

                print(
                    f" -> [Worker] Konflikt-Worker aufgewacht. Verarbeite Batch von {len(batch_to_process)} Änderungen...")
                self._task_update_violations_BATCHED(batch_to_process)

                for _ in batch_to_process:
                    self.conflict_check_queue.task_done()
            except Exception as e:
                # (Regel 1) Der Worker-Thread darf niemals sterben
                print(f"[FEHLER] Kritischer Fehler im Konflikt-Worker-Loop: {e}")

    # --- Ende System 1 ---

    # --- System 2: Layout/UI-Debouncer (MODIFIZIERT, Regel 4) ---
    def schedule_secondary_updates(self, user_id, date_obj, old_shift, new_shift):
        """
        Setzt den Timer für die sekundären (langsameren) DATEN- und UI-Updates
        (Stunden, Tageszähler, Layout).
        """
        day = date_obj.day

        # (Regel 1) Alten Timer abbrechen, falls vorhanden
        if self.secondary_ui_timer_id:
            self.tab.after_cancel(self.secondary_ui_timer_id)

        # (Regel 4) Aufgaben sammeln (User-spezifisch und Tag-spezifisch)
        # HINWEIS: Wir müssen die *Datenberechnung* (z.B. _update_user_shift_totals)
        # *vor* dem UI-Update (z.B. update_user_total_hours) ausführen.
        # Der Debouncer bündelt nur die Auslösung, nicht die Daten.

        # Wir fügen die *Parameter* hinzu, nicht nur die UI-Aufgabe
        self.secondary_ui_tasks.add(("user_data", user_id, old_shift, new_shift))
        self.secondary_ui_tasks.add(("day_data", date_obj, old_shift, new_shift))
        self.secondary_ui_tasks.add(("layout",))  # Allgemeine Layout-Aufgabe

        # Neuen Timer starten
        self.secondary_ui_timer_id = self.tab.after(
            SECONDARY_UI_DEBOUNCE_MS,
            self._run_secondary_updates
        )

    def _run_secondary_updates(self):
        """
        (Main-Thread) Wird EINMALIG 100ms nach der letzten Eingabe
        aufgerufen, um alle sekundären Daten- und UI-Aufgaben
        gebündelt auszuführen.
        """
        self.secondary_ui_timer_id = None
        if not self.tab.inner_frame.winfo_exists() or not self.tab.canvas.winfo_exists():
            return

        tasks_to_run = self.secondary_ui_tasks.copy()
        self.secondary_ui_tasks.clear()

        try:
            print(f"  -> [DEBOUNCE-UI] Führe {len(tasks_to_run)} sekundäre Daten/UI-Updates aus...")

            # (Regel 4) Wir müssen die Aufgaben intelligent aggregieren.
            # Wir wollen die Daten-Caches (Stunden, Zähler) nur einmal
            # für jeden betroffenen Benutzer/Tag aktualisieren.

            users_to_update_ui = set()
            days_to_update_ui = set()
            layout_needed = False

            for task in tasks_to_run:
                try:
                    if task[0] == "user_data":
                        # DATEN-Update (Cache)
                        self._update_user_shift_totals_incrementally(user_id=task[1], old_shift=task[2],
                                                                     new_shift=task[3])
                        # UI-Update (Merken)
                        users_to_update_ui.add(task[1])

                    elif task[0] == "day_data":
                        # DATEN-Update (Cache)
                        self.dm.recalculate_daily_counts_for_day(date_obj=task[1], old_shift=task[2], new_shift=task[3])
                        # UI-Update (Merken)
                        days_to_update_ui.add((task[1].day, task[1]))  # (day, date_obj)

                    elif task[0] == "layout":
                        layout_needed = True
                except Exception as e:
                    # (Regel 1) Fehler bei einer einzelnen Datenberechnung abfangen
                    print(f"[FEHLER] Fehler bei sekundärer Datenberechnung ({task[0]}): {e}")

            # Jetzt die UI-Updates gebündelt ausführen
            if not self.renderer:
                return

            for user_id in users_to_update_ui:
                self.renderer.update_user_total_hours(user_id)

            for (day, date_obj) in days_to_update_ui:
                self.renderer.update_daily_counts_for_day(day, date_obj)

            if layout_needed:
                self.tab.inner_frame.update_idletasks()
                self.tab.canvas.configure(scrollregion=self.tab.canvas.bbox("all"))

            print(f"  -> [DEBOUNCE-UI] Sekundäre Updates abgeschlossen.")
        except Exception as e:
            if "invalid command name" not in str(e):
                print(f"[FEHLER] Debounced UI-Update fehlgeschlagen: {e}")

    # --- Ende System 2 ---

    # --- ZENTRALE UPDATE FUNKTION (STARK MODIFIZIERT, Regel 2 & 3) ---
    def trigger_targeted_update(self, user_id, date_obj, old_shift, new_shift):
        """
        Führt Updates in priorisierter Reihenfolge aus, um
        die Latenz beim Anzeigen der Schicht ('T.') zu eliminieren.
        """
        day = date_obj.day
        user_id_str = str(user_id)
        date_str = date_obj.strftime('%Y-%m-%d')

        old_shift = old_shift if old_shift else ""
        new_shift = new_shift if new_shift else ""

        print(f"[_trigger_targeted_update] User: {user_id}, Date: {date_str}, Old: '{old_shift}', New: '{new_shift}'")

        if not self.dm or not self.renderer:
            messagebox.showerror("Interner Fehler",
                                 "DataManager oder Renderer nicht gefunden. Update abgebrochen.",
                                 parent=self.tab)
            return

        try:
            # --- SCHRITT 1: PRIMÄRER DATEN-CACHE UPDATE (SYNCHRON & SCHNELL) ---
            # (Dieser Block *muss* vor der UI-Zeichnung passieren)

            # 1a. Schichtplan-Cache aktualisieren
            if user_id_str not in self.dm.shift_schedule_data: self.dm.shift_schedule_data[user_id_str] = {}
            if not new_shift:
                if date_str in self.dm.shift_schedule_data[user_id_str]:
                    print(f"  -> Cache 1/1: Entferne '{old_shift}' aus shift_schedule_data")
                    del self.dm.shift_schedule_data[user_id_str][date_str]
            else:
                print(f"  -> Cache 1/1: Setze '{new_shift}' in shift_schedule_data")
                self.dm.shift_schedule_data[user_id_str][date_str] = new_shift

            # 1b. Renderer-Referenz aktualisieren (schnell)
            self.renderer.shifts_data = self.dm.shift_schedule_data
            self.renderer.wunschfrei_data = self.dm.wunschfrei_data
            self.renderer.processed_vacations = self.dm.processed_vacations
            self.renderer.daily_counts = self.dm.daily_counts

            # --- ENTFERNT (Regel 2): Diese Berechnungen sind zu langsam ---
            # self._update_user_shift_totals_incrementally(user_id, old_shift, new_shift)
            # self.dm.recalculate_daily_counts_for_day(date_obj, old_shift, new_shift)
            # --- ENDE ENTFERNT ---

        except Exception as e:
            print(f"[FEHLER] Fehler bei der primären Cache-Aktualisierung: {e}")
            messagebox.showwarning("Update-Fehler",
                                   f"Primärer Cache konnte nicht aktualisiert werden:\n{e}",
                                   parent=self.tab)
            return  # Harter Abbruch, wenn das schiefgeht

        try:
            # --- SCHRITT 2: PRIMÄRES UI-UPDATE (SYNCHRON & JETZT SCHNELL) ---
            # (Regel 2) Wir zeichnen NUR die Zelle, die sich geändert hat.
            print("[Action] Starte primäres UI-Update (Zelle)...")
            if day >= 0 and date_obj:  # Tag 0 ('Ü') ebenfalls einschließen
                self.renderer.update_cell_display(user_id, day, date_obj)  # <-- HIER ERSCHEINT 'T.'
            else:
                print(f"[FEHLER] Ungültiger Tag ({day}) oder Datum in _trigger_targeted_update.")

            # --- INNOVATION (Regel 2): Latenz-Fix ---
            # Wir zwingen Tkinter, die obige Änderung SOFORT auszuführen
            # und auf dem Bildschirm anzuzeigen.
            self.tab.update_idletasks()
            print("[Action] Primäres UI-Update (Zelle) abgeschlossen und gezeichnet.")  # <-- 'T.' IST JETZT SICHTBAR
            # --- ENDE Latenz-Fix ---

        except Exception as e:
            # (Regel 1) Abfangen von TclError, falls Fenster geschlossen wurde
            if "invalid command name" not in str(e):
                print(f"[FEHLER] Fehler bei primärem schnellen UI-Update (Zelle): {e}")
            # Nicht abbrechen, die restlichen Updates sind trotzdem wichtig

        # --- SCHRITT 3: ASYNCHRONE & DEBOUNCED UPDATES PLANEN ---
        # (Laufen, nachdem der Benutzer 'T.' bereits sieht)

        # 3a. System 1 (Konflikte): Aufgabe SOFORT in die Queue legen
        print(f"  -> Plane Konflikt-Neuberechnung (via Worker-Queue)...")
        self.conflict_check_queue.put(
            (user_id, date_obj, old_shift, new_shift)
        )

        # 3b. System 2 (Layout & sekundäre UI/DATEN): Debouncer starten/zurücksetzen
        print(f"  -> Plane sekundäre Daten- & UI-Updates (Stunden, Zähler, Layout)...")
        self.schedule_secondary_updates(user_id, date_obj, old_shift, new_shift)

    # --- (Unverändert) ---
    def _task_update_violations_BATCHED(self, changes_batch: List[tuple]):
        """ (Worker-Thread) Verarbeitet den Konflikt-Batch. """
        all_affected_conflict_cells = set()
        try:
            for (user_id, date_obj, old_shift, new_shift) in changes_batch:
                updates = self.dm.update_violations_incrementally(user_id, date_obj, old_shift, new_shift)
                if updates:
                    all_affected_conflict_cells.update(updates)
            print(
                f"  -> [Thread] Batch-Prüfung abgeschlossen. {len(all_affected_conflict_cells)} Konflikt-Zellen gefunden.")
        except Exception as e:
            print(f"[FEHLER] Schwerer Fehler im BATCH-Konflikt-Update-Thread: {e}")
        self.tab.after(0, self._callback_render_violations, all_affected_conflict_cells)

    # --- (Unverändert) ---
    def _callback_render_violations(self, affected_conflict_cells):
        """ (Main-Thread) Zeichnet die Konflikt-Marker. """
        if self.renderer:
            try:
                print(f"[Action] Zeichne {len(affected_conflict_cells)} Konfliktmarker (asynchron)...")
                self.renderer.update_conflict_markers(affected_conflict_cells)
                print("[Action] Asynchrone Konfliktmarker gezeichnet.")
            except Exception as e:
                # (Regel 1) Abfangen von TclError, falls Fenster geschlossen wurde
                if "invalid command name" not in str(e):
                    print(f"[FEHLER] Fehler beim asynchronen Zeichnen der Konfliktmarker: {e}")
        else:
            print("[WARNUNG] Renderer nicht verfügbar für asynchrones Konflikt-Update.")

    # --- HILFSFUNKTIONEN (Unverändert) ---

    def _get_shift_hours(self, shift_abbrev):
        """ Gibt die Stunden für eine Schicht-Abkürzung zurück, 0.0 wenn nicht gefunden. """
        if not shift_abbrev:
            return 0.0
        try:
            # (Regel 1) Greift auf die Property zu
            shift_data = self.tab.shift_types_data.get(shift_abbrev, {})
            return float(shift_data.get('hours', 0.0))
        except Exception as e:
            print(f"[FEHLER] Stundenabruf für '{shift_abbrev}' fehlgeschlagen: {e}")
            return 0.0

    def _update_user_shift_totals_incrementally(self, user_id, old_shift, new_shift):
        """
        Aktualisiert den user_shift_totals Cache inkrementell.
        (Wird jetzt asynchron/debounced aufgerufen)
        """
        user_id_str = str(user_id)
        old_hours = self._get_shift_hours(old_shift)
        new_hours = self._get_shift_hours(new_shift)
        hour_difference = new_hours - old_hours

        if hour_difference == 0.0:
            print(f"  -> Cache 2/3: Stunden-Cache: Keine Änderung ({old_shift} -> {new_shift})")
            return
        try:
            # (Regel 1) Greift auf die Property zu
            shift_totals_cache = self.tab.user_shift_totals
        except AttributeError:
            print(
                "[FEHLER] user_shift_totals Cache konnte über Tab/DM nicht abgerufen werden. Abbruch der inkrementellen Aktualisierung.")
            return

        if user_id_str in shift_totals_cache:
            current_total = shift_totals_cache[user_id_str].get('hours_total', 0.0)
            new_total = current_total + hour_difference
            shift_totals_cache[user_id_str]['hours_total'] = new_total
            print(
                f"  -> Cache 2/3: Stunden-Cache aktualisiert für {user_id_str}: {current_total:.2f} + {hour_difference:.2f} = {new_total:.2f}h")
        else:
            print(f"[WARNUNG] user_shift_totals Cache für {user_id_str} nicht gefunden. Erstelle Eintrag.")
            shift_totals_cache[user_id_str] = {'hours_total': new_hours,
                                               'shifts_total': 1}

    def get_old_shift_from_ui(self, user_id, date_str):
        """ Holt den normalisierten alten Schichtwert aus dem UI Label. """
        # (Unverändert)
        old_shift_abbrev = ""
        try:
            day = int(date_str.split('-')[2])
            if self.renderer and hasattr(self.renderer, 'grid_widgets') and 'cells' in self.renderer.grid_widgets:
                cell_widgets = self.renderer.grid_widgets['cells'].get(str(user_id), {}).get(day)
                if cell_widgets and cell_widgets.get('label'):
                    current_text_with_lock = cell_widgets['label'].cget("text")
                    current_text = current_text_with_lock.replace("🔒", "").strip()
                    normalized = current_text.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF",
                                                                                                                   "X")
                    if normalized not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?', '&nbsp;', '']:
                        old_shift_abbrev = normalized
        except Exception as e:
            print(f"[WARNUNG] _get_old_shift_from_ui: {e}")
        return old_shift_abbrev

    def update_dm_wunschfrei_cache(self, user_id, date_str, status, req_shift, req_by, reason=None):
        """ Aktualisiert den wunschfrei_data Cache im DataManager. """
        # (Unverändert)
        try:
            if self.dm:
                user_id_str = str(user_id)
                if user_id_str not in self.dm.wunschfrei_data: self.dm.wunschfrei_data[user_id_str] = {}
                self.dm.wunschfrei_data[user_id_str][date_str] = (status, req_shift, req_by,
                                                                  None)
                print(f"DM Cache für wunschfrei_data aktualisiert: {self.dm.wunschfrei_data[user_id_str][date_str]}")
            else:
                print("[FEHLER] DataManager nicht gefunden für wunschfrei_data Cache Update.")
        except Exception as e:
            print(f"[FEHLER] Fehler beim Aktualisieren des wunschfrei_data Cache: {e}")