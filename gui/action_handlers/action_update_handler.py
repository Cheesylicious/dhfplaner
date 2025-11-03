# gui/action_handlers/action_update_handler.py
# NEU: Ausgelagerte Kernlogik für DM- und UI-Updates (Regel 4)

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime


class ActionUpdateHandler:
    """
    Kapselt die zentrale Update-Logik (_trigger_targeted_update)
    und die dazugehörigen UI/DM-Helfer.
    Diese Klasse wird von anderen Action-Helfern verwendet.
    """

    def __init__(self, tab, renderer, data_manager):
        self.tab = tab
        self.renderer = renderer
        self.dm = data_manager

    # --- ZENTRALE UPDATE FUNKTION ---
    def trigger_targeted_update(self, user_id, date_obj, old_shift, new_shift):
        """Führt alle notwendigen Daten- und UI-Updates nach einer Änderung durch."""
        affected_conflict_cells = set()
        day = date_obj.day
        user_id_str = str(user_id)
        date_str = date_obj.strftime('%Y-%m-%d')  # Datum-String für Cache-Zugriff

        # Stelle sicher, dass old_shift und new_shift normalisiert sind (kein None)
        old_shift = old_shift if old_shift else ""
        new_shift = new_shift if new_shift else ""

        print(f"[_trigger_targeted_update] User: {user_id}, Date: {date_str}, Old: '{old_shift}', New: '{new_shift}'")

        try:
            # --- Daten im DM anpassen ---
            if not self.dm:
                print("[FEHLER] DataManager nicht verfügbar in _trigger_targeted_update.")
                raise Exception("DataManager nicht verfügbar.")

            # 1. Schichtplan-Cache aktualisieren
            if user_id_str not in self.dm.shift_schedule_data: self.dm.shift_schedule_data[user_id_str] = {}
            if not new_shift:  # FREI
                if date_str in self.dm.shift_schedule_data[user_id_str]:
                    print(f"  -> Entferne '{old_shift}' aus shift_schedule_data Cache für {user_id_str} am {date_str}")
                    del self.dm.shift_schedule_data[user_id_str][date_str]
            else:  # Neue Schicht eintragen/überschreiben
                print(f"  -> Setze '{new_shift}' in shift_schedule_data Cache für {user_id_str} am {date_str}")
                self.dm.shift_schedule_data[user_id_str][date_str] = new_shift

            # 3. Inkrementelles Konflikt-Update im DM
            print(f"  -> Rufe update_violations_incrementally auf...")
            updates = self.dm.update_violations_incrementally(user_id, date_obj, old_shift, new_shift)
            if updates: affected_conflict_cells.update(updates)

            # 4. Tageszählungen im DM aktualisieren
            print(f"  -> Rufe recalculate_daily_counts_for_day auf...")
            self.dm.recalculate_daily_counts_for_day(date_obj, old_shift, new_shift)


        except Exception as e:
            print(f"[FEHLER] Fehler bei Datenaktualisierung nach Speichern: {e}")
            messagebox.showwarning("Update-Fehler",
                                   f"Interne Daten konnten nicht vollständig aktualisiert werden:\n{e}\n\nUI wird möglicherweise inkonsistent.",
                                   parent=self.tab)

        # --- Gezielte UI-Updates über den Renderer ---
        if self.renderer:
            try:
                print("[Action] Starte gezielte UI-Updates...")
                if day > 0:
                    # Stelle sicher, dass die Daten für die Anzeige aktuell sind
                    self.renderer.shifts_data = self.dm.shift_schedule_data
                    self.renderer.wunschfrei_data = self.dm.wunschfrei_data
                    self.renderer.processed_vacations = self.dm.processed_vacations
                    self.renderer.daily_counts = self.dm.daily_counts

                    # Jetzt die UI-Updates
                    self.renderer.update_cell_display(user_id, day, date_obj)
                    self.renderer.update_user_total_hours(user_id)
                    self.renderer.update_daily_counts_for_day(day, date_obj)
                    self.renderer.update_conflict_markers(affected_conflict_cells)
                    print("[Action] Gezielte UI-Updates abgeschlossen.")
                    # Scrollregion neu berechnen
                    if self.tab.inner_frame.winfo_exists() and self.tab.canvas.winfo_exists():
                        self.tab.inner_frame.update_idletasks()
                        self.tab.canvas.configure(scrollregion=self.tab.canvas.bbox("all"))
                else:
                    # Spezieller Fall für Tag 0 (Vormonat "Ü")
                    if day == 0 and date_obj:
                        self.renderer.update_cell_display(user_id, day, date_obj)
                        self.renderer.update_user_total_hours(user_id)  # Stunden könnten sich ändern
                        print("[Action] Gezieltes UI-Update für 'Ü'-Zelle (Tag 0) abgeschlossen.")
                    else:
                        print(f"[FEHLER] Ungültiger Tag ({day}) oder Datum in _trigger_targeted_update.")

            except Exception as e:
                print(f"[FEHLER] Fehler bei gezieltem UI-Update: {e}")
                messagebox.showerror("UI Update Fehler",
                                     f"UI konnte nicht gezielt aktualisiert werden:\n{e}\n\nBitte manuell neu laden (Monat wechseln).",
                                     parent=self.tab)
        else:
            print("[FEHLER] Renderer nicht verfügbar für UI-Updates.")
            messagebox.showerror("Interner Fehler",
                                 "Renderer-Komponente nicht gefunden. UI kann nicht aktualisiert werden.",
                                 parent=self.tab)

    # --- HILFSFUNKTIONEN (von anderen Handlern genutzt) ---

    def get_old_shift_from_ui(self, user_id, date_str):
        """ Holt den normalisierten alten Schichtwert aus dem UI Label. """
        old_shift_abbrev = ""
        try:
            day = int(date_str.split('-')[2])
            if self.renderer and hasattr(self.renderer, 'grid_widgets') and 'cells' in self.renderer.grid_widgets:
                cell_widgets = self.renderer.grid_widgets['cells'].get(str(user_id), {}).get(day)
                if cell_widgets and cell_widgets.get('label'):
                    current_text_with_lock = cell_widgets['label'].cget("text")
                    # Entferne das Schloss-Symbol, falls vorhanden, für die Logik
                    current_text = current_text_with_lock.replace("🔒", "").strip()

                    # Normalisiere für Berechnungen
                    normalized = current_text.replace("?", "").replace(" (A)", "").replace("T./N.", "T/N").replace("WF",
                                                                                                                   "X")
                    if normalized not in ['U', 'X', 'EU', 'WF', 'U?', 'T./N.?', '&nbsp;', '']:
                        old_shift_abbrev = normalized
        except Exception as e:
            print(f"[WARNUNG] _get_old_shift_from_ui: {e}")
        return old_shift_abbrev

    def update_dm_wunschfrei_cache(self, user_id, date_str, status, req_shift, req_by, reason=None):
        """ Aktualisiert den wunschfrei_data Cache im DataManager. """
        try:
            if self.dm:
                user_id_str = str(user_id)
                if user_id_str not in self.dm.wunschfrei_data: self.dm.wunschfrei_data[user_id_str] = {}
                # Update Cache mit Status, Typ, requested_by, None für Timestamp
                self.dm.wunschfrei_data[user_id_str][date_str] = (status, req_shift, req_by, None)
                print(f"DM Cache für wunschfrei_data aktualisiert: {self.dm.wunschfrei_data[user_id_str][date_str]}")
            else:
                print("[FEHLER] DataManager nicht gefunden für wunschfrei_data Cache Update.")
        except Exception as e:
            print(f"[FEHLER] Fehler beim Aktualisieren des wunschfrei_data Cache: {e}")