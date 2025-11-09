# gui/tabs/tab_components/shift_plan_events.py
# KORRIGIERT: Behebt, dass "Schichtplan prüfen" Schichten ignoriert hat (z.B. "6"),
#             obwohl diese als unterbesetzt (rot) markiert wurden.
#             Die Prüfung iteriert jetzt über die SOLL-Stärken (min_staffing)
#             statt über die DB-Liste (get_ordered_shift_abbrevs).
#
# --- INNOVATION (Regel 2): Latenz bei Shortcuts behoben ---
# Die synchrone, blockierende Konfliktprüfung (get_conflicts_for_shift)
# in der '_on_key_press'-Methode wurde entfernt. Shortcuts rufen jetzt
# sofort den asynchronen 'save_shift_entry_and_refresh'-Handler auf,
# was die Latenz eliminiert. Visuelle Konflikte werden (wie gewünscht)
# NACH der Eingabe angezeigt.

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date, timedelta, datetime, time
import calendar
import threading

# Importiere die Helfer-Module
from database.db_users import get_ordered_users_for_schedule
from gui.request_lock_manager import RequestLockManager
from database.db_shifts import get_ordered_shift_abbrevs  # Bleibt für andere Funktionen (z.B. Generator)
from ...dialogs.generator_settings_window import \
    GeneratorSettingsWindow
# --- Import des Generators ---
from gui.shift_plan_generator import ShiftPlanGenerator


class ShiftPlanEvents:
    """
    Diese Klasse kapselt die gesamte Event-Logik (Callbacks)
    für den ShiftPlanTab. Sie agiert als "Controller" für die UI
    und interagiert mit dem DataManager, Renderer und ActionHandler,
    die in der Haupt-ShiftPlanTab-Instanz gehalten werden.
    """

    def __init__(self, master_tab):
        """
        Initialisiert die Event-Handler.
        :param master_tab: Die ShiftPlanTab-Instanz, die als
                           Orchestrator dient und Referenzen auf
                           app, ui, data_manager etc. hält.
        """
        self.tab = master_tab
        # Zugriff auf die Hauptkomponenten über die master_tab-Instanz
        # self.tab.app -> MainAdminWindow
        # self.tab.ui -> ShiftPlanUISetup
        # self.tab.data_manager
        # self.tab.renderer
        # self.tab.action_handler

    # --- UI-Interaktionen (Buttons & Klicks) ---

    def _open_generator_settings(self):
        """Öffnet das Einstellungsfenster für den Planungsassistenten."""
        GeneratorSettingsWindow(self.tab.app, self.tab, self.tab.data_manager)

    def _on_month_label_click(self, event):
        """Zeigt den Monatsauswahl-Dialog an."""
        self._show_month_chooser_dialog()

    def print_shift_plan(self):
        """Startet den Druckvorgang über den Renderer."""
        year, month = self.tab.app.current_display_date.year, self.tab.app.current_display_date.month
        month_name = self.tab.ui.month_label_var.get()
        if self.tab.renderer:
            self.tab.renderer.print_shift_plan(year, month, month_name)
        else:
            messagebox.showerror("Fehler", "Druckfunktion nicht bereit.", parent=self.tab)

    def _on_delete_month(self):
        """Startet den Admin-Prozess zum Löschen aller Schichten des Monats."""
        year = self.tab.app.current_display_date.year
        month = self.tab.app.current_display_date.month
        month_str = self.tab.ui.month_label_var.get()
        msg1 = f"Möchten Sie wirklich **ALLE** planbaren Schichteinträge für\n\n{month_str}\n\nlöschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden!"
        if not messagebox.askyesno("WARNUNG: Schichtplan löschen", msg1, icon='warning', parent=self.tab):
            return
        prompt = f"Um den Löschvorgang für {month_str} zu bestätigen, geben Sie bitte 'LÖSCHEN' in das Feld ein und klicken Sie OK."
        confirmation_text = simpledialog.askstring("Endgültige Bestätigung", prompt, parent=self.tab)
        if confirmation_text != "LÖSCHEN":
            messagebox.showinfo("Abgebrochen",
                                "Eingabe war ungültig. Der Löschvorgang wurde abgebrochen.",
                                parent=self.tab)
            return
        try:
            # Ruft den (jetzt asynchronen) Admin-Handler auf
            self.tab.action_handler.delete_shift_plan_by_admin(year, month)
        except Exception as e:
            messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}",
                                 parent=self.tab)
            import traceback
            traceback.print_exc()

    def _on_unlock_all_shifts(self):
        """Startet den Admin-Prozess zum Aufheben aller Schichtsicherungen."""
        year = self.tab.app.current_display_date.year
        month = self.tab.app.current_display_date.month
        month_str = self.tab.ui.month_label_var.get()
        msg = f"Möchten Sie wirklich **ALLE** Schichtsicherungen (Locks 🔒) für\n\n{month_str}\n\naufheben?\n\nDie eingetragenen Schichten selbst bleiben erhalten."
        if not messagebox.askyesno("WARNUNG: Alle Sicherungen aufheben", msg, icon='warning', parent=self.tab):
            return
        try:
            # Ruft den (jetzt asynchronen) Admin-Handler auf
            self.tab.action_handler.unlock_all_shifts_for_month(year, month)
        except Exception as e:
            messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}",
                                 parent=self.tab)
            import traceback
            traceback.print_exc()

    def show_previous_month(self):
        """Wechselt zur Ansicht des Vormonats."""
        self.clear_understaffing_results()
        current_date = self.tab.app.current_display_date
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        self.tab.app.current_display_date = last_day_of_previous_month
        new_year, new_month = self.tab.app.current_display_date.year, self.tab.app.current_display_date.month
        self.tab.app.current_display_date = self.tab.app.current_display_date.replace(day=1)
        if current_date.year != new_year:
            if hasattr(self.tab.app.app, 'load_holidays_for_year'): self.tab.app.app.load_holidays_for_year(new_year)
            if hasattr(self.tab.app.app, 'load_events_for_year'): self.tab.app.app.load_events_for_year(new_year)

        if hasattr(self.tab.app, 'trigger_shift_plan_preload'):
            self.tab.app.trigger_shift_plan_preload(new_year, new_month)

        self.tab.build_shift_plan_grid(new_year, new_month)

    def show_next_month(self):
        """Wechselt zur Ansicht des Folgemonats."""
        self.clear_understaffing_results()
        current_date = self.tab.app.current_display_date
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        first_day_of_next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        self.tab.app.current_display_date = first_day_of_next_month
        new_year, new_month = self.tab.app.current_display_date.year, self.tab.app.current_display_date.month
        if current_date.year != new_year:
            if hasattr(self.tab.app.app, 'load_holidays_for_year'): self.tab.app.app.load_holidays_for_year(new_year)
            if hasattr(self.tab.app.app, 'load_events_for_year'): self.tab.app.app.load_events_for_year(new_year)

        if hasattr(self.tab.app, 'trigger_shift_plan_preload'):
            self.tab.app.trigger_shift_plan_preload(new_year, new_month)

        self.tab.build_shift_plan_grid(new_year, new_month)

    def toggle_month_lock(self):
        """Sperrt oder entsperrt den Monat für Anträge."""
        year = self.tab.app.current_display_date.year
        month = self.tab.app.current_display_date.month
        is_locked = RequestLockManager.is_month_locked(year, month)
        locks = RequestLockManager.load_locks()
        lock_key = f"{year}-{month:02d}"
        if is_locked:
            if lock_key in locks: del locks[lock_key]
        else:
            locks[lock_key] = True
        if RequestLockManager.save_locks(locks):
            self.tab.update_lock_status()  # update_lock_status ist in ShiftPlanTab
            if hasattr(self.tab.app, 'refresh_antragssperre_views'): self.tab.app.refresh_antragssperre_views()
        else:
            messagebox.showerror("Fehler", "Der Status konnte nicht gespeichert werden.", parent=self.tab)

    # --- Logik für Plan-Prüfung ---

    def check_understaffing(self):
        """Prüft den aktuellen Plan auf Unterbesetzung und zeigt Ergebnisse an."""
        self.clear_understaffing_results()
        year, month = self.tab.app.current_display_date.year, self.tab.app.current_display_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        print("[Check Understaffing] Verwende aktuelle Live-Daten aus dem DataManager...")
        try:
            daily_counts = self.tab.data_manager.daily_counts
        except AttributeError:
            messagebox.showerror("Fehler",
                                 "Tageszählungen (daily_counts) nicht im DataManager gefunden.\nBitte warten Sie, bis der Plan geladen ist.",
                                 parent=self.tab)
            return

        understaffing_found = False

        # UI-Element aus der ui-Instanz holen
        result_frame = self.tab.ui.understaffing_result_frame
        result_frame.pack(fill="x", pady=5, before=self.tab.ui.lock_button.master)

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            date_str = current_date.strftime('%Y-%m-%d')
            min_staffing = self.tab.data_manager.get_min_staffing_for_date(current_date)

            for shift, min_req in min_staffing.items():

                if min_req is not None and min_req > 0:
                    count = daily_counts.get(date_str, {}).get(shift, 0)
                    if count < min_req:
                        understaffing_found = True
                        shift_name = self.tab.app.app.shift_types_data.get(shift, {}).get('name', shift)
                        ttk.Label(result_frame,
                                  text=f"Unterbesetzung am {current_date.strftime('%d.%m.%Y')}: Schicht '{shift_name}' ({shift}) - {count} von {min_req} anwesend.",
                                  foreground="red", font=("Segoe UI", 10)).pack(anchor="w")

        if not understaffing_found:
            ttk.Label(result_frame, text="Keine Unterbesetzungen gefunden.",
                      foreground="green", font=("Segoe UI", 10, "bold")).pack(anchor="w")

    def clear_understaffing_results(self):
        """Entfernt die Ergebnisse der Unterbesetzungsprüfung."""
        result_frame = self.tab.ui.understaffing_result_frame
        result_frame.pack_forget()
        for widget in result_frame.winfo_children():
            widget.destroy()

    # --- Tastatur-Shortcut-Logik ---

    def _on_key_press(self, event):
        """Verarbeitet einen Tastendruck als Schicht-Shortcut ODER Lock-Toggle."""
        key = event.keysym.lower()

        # 1. Renderer fragen, wo die Maus ist
        if not self.tab.renderer:
            return
        coords = self.tab.renderer.get_hovered_cell_coords()
        if not coords:
            return  # Maus ist nicht über einer gültigen Zelle

        user_id, day = coords

        # 2. Datum ermitteln
        try:
            if day == 0:  # "Ü"-Zelle
                date_obj = date(self.tab.renderer.year, self.tab.renderer.month, 1) - timedelta(days=1)
            else:
                date_obj = date(self.tab.renderer.year, self.tab.renderer.month, day)
            date_str = date_obj.strftime('%Y-%m-%d')
        except ValueError:
            return  # Ungültiges Datum

        # 3. Aktion basierend auf der Taste bestimmen

        # --- Lock/Unlock-Logik (Leertaste) ---
        if key == 'space':
            try:
                current_shift = self.tab.data_manager.shift_schedule_data.get(str(user_id), {}).get(date_str)
                lock_status = self.tab.data_manager.shift_lock_manager.get_lock_status(str(user_id), date_str)
            except Exception as e:
                print(f"[FEHLER] Lock-Daten für Shortcut nicht abrufbar: {e}")
                self.tab.bell()
                return

            if lock_status:
                print(f"[Shortcut] Entsichere: U:{user_id} D:{day}")
                # Ruft den (jetzt asynchronen) ActionHandler auf
                self.tab.action_handler.unlock_shift(user_id, date_str)
            else:
                securable_shifts = ["T.", "N.", "6"]
                is_securable_or_fixed = current_shift in securable_shifts or current_shift in ["X", "QA", "S", "U",
                                                                                               "EU", "WF", "U?"]
                if is_securable_or_fixed and current_shift:
                    print(f"[Shortcut] Sichere: U:{user_id} D:{day} -> '{current_shift}'")
                    # Ruft den (jetzt asynchronen) ActionHandler auf
                    self.tab.action_handler.secure_shift(user_id, date_str, current_shift)
                else:
                    self.tab.bell()
            return  # Verarbeitung hier beenden

        # --- Schicht-Eintrag-Logik (andere Tasten) ---
        if key in self.tab.shortcut_map:
            target_shift_abbrev = self.tab.shortcut_map[key]

            # --- INNOVATION (Regel 2): Blockierende Prüfung entfernt ---
            # Die synchrone Konfliktprüfung wurde entfernt, um die Latenz
            # bei der Shortcut-Nutzung zu beseitigen.
            #
            # ALTE (BLOCKIERENDE) PRÜFUNG:
            # if not hasattr(self.tab.data_manager, 'get_conflicts_for_shift'):
            #     print("[FEHLER] PlanningAssistant-Funktion nicht im DataManager gefunden.")
            #     return
            #
            # conflicts = self.tab.data_manager.get_conflicts_for_shift(user_id, date_obj, target_shift_abbrev)
            #
            # if conflicts:
            #     print(f"Shortcut blockiert: {conflicts[0]}")
            #     self.tab.bell()
            #     return
            # --- ENDE INNOVATION ---

            # Aktion AUSFÜHREN (ruft den asynchronen Handler auf)
            print(f"[Shortcut] Weise zu: U:{user_id} D:{day} -> '{target_shift_abbrev}'")
            self.tab.action_handler.save_shift_entry_and_refresh(
                user_id,
                date_str,
                target_shift_abbrev
            )

    # --- Plan-Generator ---

    def _on_generate_plan(self):
        """Startet den Schichtplan-Generator."""
        year = self.tab.app.current_display_date.year
        month = self.tab.app.current_display_date.month
        month_str = self.tab.ui.month_label_var.get()
        if RequestLockManager.is_month_locked(year, month):
            messagebox.showwarning("Gesperrt",
                                   f"Der Monat {month_str} ist für Anträge gesperrt.\nEine automatische Generierung ist nicht möglich, bitte erst entsperren.",
                                   parent=self.tab)
            return
        msg = (f"Dies generiert automatisch 'T.', 'N.' und '6' Dienste für {month_str}.\n\n"
               "Bestehende Einträge (auch Urlaub, Wunschfrei etc.) werden NICHT überschrieben.\n"
               "Hundekonflikte, Urlaube, Ruhezeiten und Mindestbesetzung werden berücksichtigt.\n\n"
               "Fortfahren?")
        if not messagebox.askyesno("Schichtplan generieren", msg, parent=self.tab): return

        # UI für Ladeanzeige vorbereiten (über Haupt-Tab)
        self.tab.show_progress_widgets()

        try:
            # Daten für Generator sammeln
            vacation_requests = self.tab.data_manager.processed_vacations
            wunschfrei_requests = self.tab.data_manager.wunschfrei_data
            current_shifts = self.tab.data_manager.shift_schedule_data
            locked_shifts = self.tab.data_manager.locked_shifts_cache
            live_shifts_data = {uid: day_data.copy() for uid, day_data in current_shifts.items()}
            first_day_of_target_month = date(year, month, 1)
            date_for_user_filter = datetime.combine(first_day_of_target_month, time(0, 0, 0))
            all_users = get_ordered_users_for_schedule(for_date=date_for_user_filter)
            if not all_users:
                messagebox.showerror("Fehler", f"Keine aktiven Benutzer für die Planung im {month_str} gefunden.",
                                     parent=self.tab)
                self.tab.hide_progress_widgets()
                return
            user_data_map = {user['id']: user for user in all_users}
            self.tab.data_manager.user_data_map = user_data_map

            holidays_in_month = set()
            if hasattr(self.tab.app.app, 'holiday_manager'):
                year_holidays = self.tab.app.app.holiday_manager.holidays.get(str(year), {})
                for date_str, holiday_name in year_holidays.items():
                    try:
                        h_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        if h_date.year == year and h_date.month == month: holidays_in_month.add(h_date)
                    except ValueError:
                        print(f"[WARNUNG] Ungültiges Feiertagsdatum ignoriert: {date_str}")

        except AttributeError as ae:
            messagebox.showerror("Fehler",
                                 f"Benötigte Plandaten nicht gefunden:\n{ae}\nBitte warten Sie, bis der Plan vollständig geladen ist, oder laden Sie ihn neu.",
                                 parent=self.tab)
            self.tab.hide_progress_widgets()
            return
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Vorbereiten der Generierung:\n{e}", parent=self.tab)
            self.tab.hide_progress_widgets()
            return

        generator = ShiftPlanGenerator(
            app=self.tab.app.app,  # Bootloader
            data_manager=self.tab.data_manager,
            year=year, month=month, all_users=all_users, user_data_map=user_data_map,
            vacation_requests=vacation_requests, wunschfrei_requests=wunschfrei_requests,
            live_shifts_data=live_shifts_data,
            locked_shifts_data=locked_shifts,
            holidays_in_month=holidays_in_month,
            # (Callbacks zeigen auf Methoden im Haupt-Tab)
            progress_callback=self.tab._safe_update_progress,
            completion_callback=self.tab._on_generation_complete
        )
        threading.Thread(target=generator.run_generation, daemon=True).start()

    # --- Monatsauswahl-Dialog (komplexe UI-Logik, bleibt hier) ---

    def _show_month_chooser_dialog(self):
        """Zeigt einen Dialog zur Auswahl von Monat und Jahr an."""
        dialog = tk.Toplevel(self.tab)
        dialog.title("Monatsauswahl")
        dialog.transient(self.tab.master.master)
        dialog.grab_set()
        dialog.focus_set()

        current_date = self.tab.app.current_display_date
        current_year = current_date.year
        current_month = current_date.month
        month_names_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                          "August", "September", "Oktober", "November", "Dezember"]
        start_year = date.today().year - 5
        end_year = date.today().year + 5
        years = [str(y) for y in range(start_year, end_year + 1)]
        selected_month_var = tk.StringVar(value=month_names_de[current_month - 1])
        selected_year_var = tk.StringVar(value=str(current_year))

        ttk.Label(dialog, text="Monat auswählen:").pack(padx=10, pady=(10, 0))
        month_combo = ttk.Combobox(dialog, textvariable=selected_month_var, values=month_names_de, state="readonly",
                                   width=15)
        month_combo.pack(padx=10, pady=(0, 10))
        ttk.Label(dialog, text="Jahr auswählen:").pack(padx=10, pady=(10, 0))
        year_combo = ttk.Combobox(dialog, textvariable=selected_year_var, values=years, state="readonly", width=15)
        year_combo.pack(padx=10, pady=(0, 10))

        def on_ok():
            try:
                new_month_index = month_names_de.index(selected_month_var.get())
                new_month = new_month_index + 1
                new_year = int(selected_year_var.get())
                new_date = date(new_year, new_month, 1)

                if new_date.year != current_date.year or new_date.month != current_date.month:
                    self.tab.app.current_display_date = new_date
                    if current_year != new_year:
                        if hasattr(self.tab.app.app, '_load_holidays_for_year'):
                            self.tab.app.app._load_holidays_for_year(new_year)
                        if hasattr(self.tab.app.app, '_load_events_for_year'):
                            self.tab.app.app._load_events_for_year(new_year)

                    if hasattr(self.tab.app, 'trigger_shift_plan_preload'):
                        self.tab.app.trigger_shift_plan_preload(new_year, new_month)

                    # Starte das Neuladen im Haupt-Tab (asynchron)
                    self.tab.build_shift_plan_grid(new_year, new_month, data_ready=False)

                dialog.destroy()

            except ValueError:
                messagebox.showerror("Fehler", "Ungültige Monats- oder Jahresauswahl.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Schwerer Fehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=dialog)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=10, pady=10)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=5)
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side="left", padx=5)

        # Dialog zentrieren
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        main_window = self.tab.master.master if self.tab.master and self.tab.master.master else self.tab
        x = main_window.winfo_x() + (main_window.winfo_width() // 2) - (width // 2)
        y = main_window.winfo_y() + (main_window.winfo_height() // 2) - (height // 2)
        dialog.geometry(f'+{x}+{y}')
        dialog.wait_window()