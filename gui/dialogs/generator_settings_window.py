# gui/dialogs/generator_settings_window.py
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import traceback
from collections import defaultdict
# Import der Datenbank-Funktion, um Benutzerdaten zu laden
from database.db_users import get_ordered_users_for_schedule


class GeneratorSettingsWindow(simpledialog.Dialog):
    """
    Dialog zur Konfiguration des automatischen Schichtplangenerators.
    Enthält Soft Limits, priorisierte Mitarbeiter-Präferenzen und benutzerspezifische Sonderfaktoren.
    """

    def __init__(self, app, parent, data_manager):
        self.app = app
        self.data_manager = data_manager
        if self.data_manager:
            print("[DEBUG] DataManager Instanz in GeneratorSettingsWindow ERFOLGREICH übergeben.")  # DEBUG
        else:
            print("[FEHLER] DataManager Instanz wurde NICHT an GeneratorSettingsWindow übergeben!")  # DEBUG

        # Konfiguration laden
        self.config = {}
        if self.data_manager and hasattr(self.data_manager, 'get_generator_config'):
            try:
                loaded_config = self.data_manager.get_generator_config()
                print(f"[DEBUG] Geladene Konfiguration: {loaded_config}")
                if isinstance(loaded_config, dict):
                    self.config = loaded_config
                else:
                    print("[WARNUNG] get_generator_config hat kein Dictionary zurückgegeben, verwende Standard.")
                    self.config = {}
            except Exception as e:
                print(f"[FEHLER] Kritischer Fehler beim Laden der Generator-Konfiguration: {e}")
                traceback.print_exc()
                self.config = {}
        else:
            print("[WARNUNG] DataManager nicht verfügbar oder get_generator_config Methode fehlt.")

        # Initialisiere Variablen (Algorithmus-Parameter)
        self.max_same_shift_var = tk.IntVar(value=self.config.get('max_consecutive_same_shift', 4))
        self.enable_24h_planning_var = tk.BooleanVar(value=self.config.get('enable_24h_planning', False))
        # Min. freie Tage nach max. Arbeitstagen
        self.mandatory_rest_days_after_max_shifts_var = tk.IntVar(
            value=self.config.get('mandatory_rest_days_after_max_shifts', 2))

        # Generator Prioritäten
        self.avoid_understaffing_hard_var = tk.BooleanVar(value=self.config.get('avoid_understaffing_hard', True))
        self.ensure_one_weekend_off_var = tk.BooleanVar(value=self.config.get('ensure_one_weekend_off', False))
        self.wunschfrei_respect_level_var = tk.IntVar(value=self.config.get('wunschfrei_respect_level', 75))

        # Score Multiplier und Thresholds
        self.fairness_threshold_hours_var = tk.DoubleVar(value=self.config.get('fairness_threshold_hours', 10.0))
        self.min_hours_fairness_threshold_var = tk.DoubleVar(
            value=self.config.get('min_hours_fairness_threshold', 20.0))

        # NEU: Multiplikatoren für Scores
        self.min_hours_score_multiplier_var = tk.DoubleVar(value=self.config.get('min_hours_score_multiplier', 5.0))
        self.fairness_score_multiplier_var = tk.DoubleVar(value=self.config.get('fairness_score_multiplier', 1.0))
        self.isolation_score_multiplier_var = tk.DoubleVar(value=self.config.get('isolation_score_multiplier', 1.0))
        # Ende NEU

        # Partner-Liste mit Prioritäten laden
        raw_partners = self.config.get('preferred_partners_prioritized', [])
        print(f"[DEBUG] Raw Prioritized Partners aus Konfig: {raw_partners}")
        self.preferred_partners = []

        for p in raw_partners:
            # Prüft defensiv, ob der Eintrag gültig ist
            if isinstance(p, dict) and 'id_a' in p and 'id_b' in p and 'priority' in p:
                try:
                    id_a = int(p['id_a'])
                    id_b = int(p['id_b'])
                    priority = int(p['priority'])
                    # Normalisieren (kleinere ID zuerst) und hinzufügen
                    self.preferred_partners.append({
                        'id_a': min(id_a, id_b),
                        'id_b': max(id_a, id_b),
                        'priority': priority
                    })
                except (ValueError, TypeError):
                    print(f"[WARNUNG] Ungültiger priorisierter Partnereintrag ignoriert (Typfehler): {p}")
                    continue
            else:
                print(f"[WARNUNG] Ungültiges priorisiertes Partnerdatenformat ignoriert (Strukturfehler): {p}")

        # Sortieren nach User A, dann Priorität
        self.preferred_partners.sort(key=lambda x: (x['id_a'], x['priority']))
        print(f"[DEBUG] Verarbeitete preferred_partners beim Init: {self.preferred_partners}")

        # Benutzer-spezifische Präferenzen laden
        default_user_pref = {
            'min_monthly_hours': None,
            'max_monthly_hours': None,
            'shift_exclusions': [],
            'ratio_preference_scale': 50,
            'max_consecutive_same_shift_override': None
        }
        raw_user_preferences = self.config.get('user_preferences', {})
        self.user_preferences = defaultdict(lambda: default_user_pref.copy())
        for user_id_str, prefs in raw_user_preferences.items():
            if 'ratio_preference_scale' not in prefs:
                prefs['ratio_preference_scale'] = 50
            self.user_preferences[user_id_str].update(prefs)

        # Benutzer-Map und Combobox-Optionen laden
        self.user_map = {};
        self.user_options = []
        try:
            all_users = get_ordered_users_for_schedule()
            self.user_map = {user.get('id'): user for user in all_users if user.get('id') is not None}
            sorted_users = sorted(all_users, key=lambda u: u.get('lastname', str(u.get('id', 0))))
            for user in sorted_users:
                user_id = user.get('id');
                name = user.get('lastname', user.get('name', f"ID {user_id}"))
                if user_id is not None: self.user_options.append(f"{user_id} ({name})")
        except Exception as e:
            print(f"[FEHLER] Kritischer Fehler beim Laden der Benutzerdaten für Comboboxen: {e}")
            traceback.print_exc()

        # Variablen für UI-Elemente
        self.partner_a_var = tk.StringVar(value="")
        self.partner_b_var = tk.StringVar(value="")
        self.priority_var = tk.StringVar(value="1")

        # Variablen für User-Präferenzen UI
        self.selected_user_id_var = tk.StringVar(value="")
        self.min_hours_var = tk.StringVar(value="")
        self.max_hours_var = tk.StringVar(value="")
        self.ratio_pref_scale_var = tk.IntVar(value=50)
        self.ratio_pref_label_var = tk.StringVar(value="Neutral (0% Bias)")
        self.max_same_shift_override_var = tk.StringVar(value="")
        self.shift_exclusions_list_var = tk.StringVar(value="")
        self.all_shift_abbrevs = sorted(list(self.app.shift_types_data.keys())) if self.app and hasattr(self.app,
                                                                                                        'shift_types_data') else [
            "T.", "N.", "6", "24", "U", "EU"]

        self.treeview_prefs = None

        super().__init__(parent, title="Generator-Einstellungen")

    def _get_user_info(self, user_id):
        user = self.user_map.get(user_id)
        name_parts = [user.get('vorname')] if user and user.get('vorname') else []
        name_parts.append(user.get('lastname', user.get('name', 'Unbekannt')) if user else 'Unbekannt')
        full_name = " ".join(filter(None, name_parts))

        return f"{user_id} ({full_name})" if user else f"ID {user_id} (Unbekannt)"

    def _load_preferred_partners(self):
        self.listbox.delete(0, tk.END)
        display_list = sorted(self.preferred_partners, key=lambda x: (x['id_a'], x['priority']))
        for p in display_list:
            user_a_info = self._get_user_info(p['id_a'])
            user_b_info = self._get_user_info(p['id_b'])
            self.listbox.insert(tk.END, f"{user_a_info} | {user_b_info} | Prio: {p['priority']}")

    def _add_partner(self):
        selection_a = self.partner_a_var.get()
        selection_b = self.partner_b_var.get()
        priority_str = self.priority_var.get()

        if not selection_a or not selection_b:
            messagebox.showerror("Fehler", "Bitte wählen Sie beide Mitarbeiter aus.", parent=self)
            return

        try:
            priority = int(priority_str)
            if priority <= 0:
                messagebox.showerror("Fehler", "Priorität muss eine positive Zahl sein.", parent=self)
                return
        except ValueError:
            messagebox.showerror("Fehler", "Priorität muss eine gültige Zahl sein.", parent=self)
            return

        try:
            def extract_id(selection):
                return int(selection.split('(')[0].strip())

            id_a = extract_id(selection_a)
            id_b = extract_id(selection_b)

            if id_a == id_b:
                messagebox.showerror("Fehler", "Die Mitarbeiter A und B müssen sich unterscheiden.", parent=self)
                return

            if id_a not in self.user_map or id_b not in self.user_map:
                messagebox.showerror("Fehler", "Mindestens eine der Benutzer-IDs ist nicht aktiv oder ungültig.",
                                     parent=self)
                return

            user1_id = min(id_a, id_b)
            user2_id = max(id_a, id_b)

            existing_entry_index = -1
            for i, entry in enumerate(self.preferred_partners):
                if entry['id_a'] == user1_id and entry['id_b'] == user2_id:
                    existing_entry_index = i
                    break

            new_partner_entry = {'id_a': user1_id, 'id_b': user2_id, 'priority': priority}

            if existing_entry_index != -1:
                if self.preferred_partners[existing_entry_index]['priority'] == priority:
                    messagebox.showwarning("Duplikat",
                                           "Diese Partnerkombination mit dieser Priorität existiert bereits.",
                                           parent=self)
                    return
                else:
                    if messagebox.askyesno("Aktualisieren?",
                                           f"Diese Partnerkombination existiert bereits mit Priorität {self.preferred_partners[existing_entry_index]['priority']}.\nMöchten Sie die Priorität auf {priority} aktualisieren?",
                                           parent=self):
                        self.preferred_partners[existing_entry_index]['priority'] = priority
                    else:
                        return
            else:
                self.preferred_partners.append(new_partner_entry)

            self.preferred_partners.sort(key=lambda x: (x['id_a'], x['priority']))
            self._load_preferred_partners()

            self.partner_a_var.set("")
            self.partner_b_var.set("")
            self.priority_var.set("1")

        except ValueError:
            messagebox.showerror("Fehler", "Interner Fehler beim Parsen der Benutzer-ID.", parent=self)
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self)

    def _remove_partner(self):
        try:
            selected_index_listbox = self.listbox.curselection()[0]
            selected_text = self.listbox.get(selected_index_listbox)

            parts = selected_text.split('|')
            id_a_str = parts[0].split('(')[0].strip()
            id_b_str = parts[1].split('(')[0].strip()
            prio_str = parts[2].split(':')[1].strip()

            id_a = int(id_a_str)
            id_b = int(id_b_str)
            prio = int(prio_str)

            user1_id = min(id_a, id_b)
            user2_id = max(id_a, id_b)

            entry_to_remove = None
            for entry in self.preferred_partners:
                if entry['id_a'] == user1_id and entry['id_b'] == user2_id and entry['priority'] == prio:
                    entry_to_remove = entry
                    break

            if entry_to_remove:
                self.preferred_partners.remove(entry_to_remove)
                print(f"[DEBUG] Partner entfernt: {entry_to_remove}. Aktuell: {self.preferred_partners}")
                self._load_preferred_partners()
            else:
                messagebox.showerror("Fehler", "Konnte den ausgewählten Eintrag intern nicht finden.", parent=self)

        except IndexError:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Eintrag zum Entfernen aus.", parent=self)
        except (ValueError, IndexError) as e:
            messagebox.showerror("Fehler", f"Fehler beim Parsen der Auswahl zum Entfernen: {e}", parent=self)

    # --- T./N. Scale Helfer ---
    def _update_ratio_label(self, val):
        """ Aktualisiert den Label-Text basierend auf dem Scale-Wert. """
        try:
            scale_val = int(float(val))
        except ValueError:
            scale_val = 50

        if scale_val == 50:
            text = "Neutral (0% Bias)"
        elif scale_val < 50:
            bias_perc = 50 - scale_val
            text = f"Nachtdienst Bias ({bias_perc * 2}%)"
        else:
            bias_perc = scale_val - 50
            text = f"Tagesdienst Bias ({bias_perc * 2}%)"

        self.ratio_pref_label_var.set(text)

    # --- Methoden für User-Präferenzen ---
    def _clear_input_fields(self):
        """ Setzt die Eingabefelder für Präferenzen zurück. """
        self.selected_user_id_var.set("")
        self.user_pref_combo.set("")
        self.min_hours_var.set("")
        self.max_hours_var.set("")
        self.ratio_pref_scale_var.set(50)
        self._update_ratio_label(50)
        self.max_same_shift_override_var.set("")
        self.shift_exclusions_list_var.set("")
        if self.treeview_prefs and self.treeview_prefs.selection():
            self.treeview_prefs.selection_remove(self.treeview_prefs.selection())

    def _load_selected_user_pref_from_combobox(self, event=None):
        """ Lädt die Einstellungen des ausgewählten Benutzers (aus Combobox) in die Eingabefelder."""

        selected_user_str = self.user_pref_combo.get()
        if not selected_user_str: return

        self._clear_input_fields()

        try:
            self.user_pref_combo.set(selected_user_str)

            user_id = int(selected_user_str.split('(')[0].strip())
            user_id_str = str(user_id)

            user_config = self.user_preferences[user_id_str]

            self.selected_user_id_var.set(user_id_str)
            self.min_hours_var.set(str(user_config.get('min_monthly_hours', "")) if user_config.get(
                'min_monthly_hours') is not None else "")
            self.max_hours_var.set(str(user_config.get('max_monthly_hours', "")) if user_config.get(
                'max_monthly_hours') is not None else "")

            scale_val = user_config.get('ratio_preference_scale', 50)
            self.ratio_pref_scale_var.set(scale_val)
            self._update_ratio_label(scale_val)

            self.max_same_shift_override_var.set(
                str(user_config.get('max_consecutive_same_shift_override', "")) if user_config.get(
                    'max_consecutive_same_shift_override') is not None else "")
            self.shift_exclusions_list_var.set(", ".join(user_config.get('shift_exclusions', [])))

        except ValueError:
            messagebox.showerror("Fehler", "Ungültige Benutzer-ID-Formatierung.", parent=self)
            self._clear_input_fields()
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self)
            self._clear_input_fields()

    def _load_selected_user_pref_from_treeview(self, event=None):
        """ Lädt die Präferenzen des im Treeview ausgewählten Benutzers in die Eingabefelder. """
        try:
            selected_item = self.treeview_prefs.focus()
            if not selected_item:
                self._clear_input_fields()
                return

            user_id_str = selected_item
            user_id = int(user_id_str)

            user_config = self.user_preferences[user_id_str]
            user_info_str = self._get_user_info(user_id)

            self._clear_input_fields()

            if user_info_str in self.user_options:
                self.user_pref_combo.set(user_info_str)
            else:
                self.user_pref_combo.set("")

            self.selected_user_id_var.set(user_id_str)
            self.min_hours_var.set(str(user_config.get('min_monthly_hours', "")) if user_config.get(
                'min_monthly_hours') is not None else "")
            self.max_hours_var.set(str(user_config.get('max_monthly_hours', "")) if user_config.get(
                'max_monthly_hours') is not None else "")

            scale_val = user_config.get('ratio_preference_scale', 50)
            self.ratio_pref_scale_var.set(scale_val)
            self._update_ratio_label(scale_val)

            self.max_same_shift_override_var.set(
                str(user_config.get('max_consecutive_same_shift_override', "")) if user_config.get(
                    'max_consecutive_same_shift_override') is not None else "")
            self.shift_exclusions_list_var.set(", ".join(user_config.get('shift_exclusions', [])))

        except ValueError as e:
            print(f"[FEHLER] Fehler beim Laden der Präferenzen aus Treeview (ValueError): {e}")
            messagebox.showerror("Fehler", "Interner Fehler beim Laden der Benutzerdaten.", parent=self)
        except Exception as e:
            print(f"[FEHLER] Unerwarteter Fehler beim Laden der Präferenzen aus Treeview: {e}")
            messagebox.showerror("Fehler", f"Unerwarteter Fehler: {e}", parent=self)

    def _load_user_preferences_overview(self):
        """ Lädt alle gespeicherten Benutzer-Sonderfaktoren in das Treeview. """
        if not self.treeview_prefs: return

        self.treeview_prefs.delete(*self.treeview_prefs.get_children())

        sorted_user_ids = sorted(self.user_preferences.keys(),
                                 key=lambda uid_str: self.user_map.get(int(uid_str), {}).get('lastname', 'Z' * 20))

        for user_id_str in sorted_user_ids:
            prefs = self.user_preferences[user_id_str]
            has_pref = any(v is not None and v != [] for k, v in prefs.items() if k != 'ratio_preference_scale')
            if prefs.get('ratio_preference_scale') != 50:
                has_pref = True

            if not has_pref:
                continue

            user_id = int(user_id_str)
            user_info = self._get_user_info(user_id)

            min_hrs_display = f"{prefs['min_monthly_hours']:.1f}" if prefs['min_monthly_hours'] is not None else ""
            max_hrs_display = f"{prefs['max_monthly_hours']:.1f}" if prefs['max_monthly_hours'] is not None else ""
            exclusions_display = ", ".join(prefs['shift_exclusions'])

            scale_val = prefs.get('ratio_preference_scale', 50)
            ratio_pref_display = ""
            if scale_val == 50:
                ratio_pref_display = "Neutral (50)"
            elif scale_val < 50:
                bias_perc = 50 - scale_val
                ratio_pref_display = f"Nacht (+{bias_perc * 2}%)"
            else:
                bias_perc = scale_val - 50
                ratio_pref_display = f"Tag (+{bias_perc * 2}%)"

            max_same_display = str(prefs['max_consecutive_same_shift_override']) if prefs[
                                                                                        'max_consecutive_same_shift_override'] is not None else ""

            self.treeview_prefs.insert("", tk.END, iid=user_id_str,
                                       values=(user_info, min_hrs_display, max_hrs_display, exclusions_display,
                                               ratio_pref_display, max_same_display))

    def _save_user_preferences(self):
        """ Speichert die aktuellen Einstellungen für den ausgewählten Benutzer. """
        user_id_str = self.selected_user_id_var.get()
        if not user_id_str:
            messagebox.showerror("Fehler", "Bitte wählen Sie zuerst einen Mitarbeiter aus.", parent=self)
            return

        try:
            # 1. Min Stunden
            min_hours_raw = self.min_hours_var.get().strip()
            min_hours = None
            if min_hours_raw:
                min_hours = float(min_hours_raw)
                if min_hours < 0: raise ValueError("Min. Stunden darf nicht negativ sein.")

            # 2. Max Stunden
            max_hours_raw = self.max_hours_var.get().strip()
            max_hours = None
            if max_hours_raw:
                max_hours = float(max_hours_raw)
                if max_hours <= 0: raise ValueError("Max. Stunden muss positiv sein.")

            if min_hours is not None and max_hours is not None and min_hours > max_hours:
                raise ValueError("Min. Stunden muss kleiner oder gleich Max. Stunden sein.")

            # 3. Ratio-Präferenz (Skala)
            ratio_pref_scale = self.ratio_pref_scale_var.get()
            if ratio_pref_scale < 0 or ratio_pref_scale > 100:
                raise ValueError("T./N. Skala muss zwischen 0 und 100 liegen.")

            # 4. Max gleiche Schichten Override
            max_same_shift_raw = self.max_same_shift_override_var.get().strip()
            max_same_shift_override = None
            if max_same_shift_raw:
                max_same_shift_override = int(max_same_shift_raw)
                if max_same_shift_override <= 0: raise ValueError("Max. gleiche Schichten muss positiv sein.")

            # 5. Schicht-Ausschlüsse
            exclusions_raw = self.shift_exclusions_list_var.get().upper().replace(' ', '')
            shift_exclusions = [abbr.strip() for abbr in exclusions_raw.split(',') if abbr.strip()]

            # Speichern
            self.user_preferences[user_id_str]['min_monthly_hours'] = min_hours
            self.user_preferences[user_id_str]['max_monthly_hours'] = max_hours
            self.user_preferences[user_id_str]['shift_exclusions'] = shift_exclusions
            self.user_preferences[user_id_str]['ratio_preference_scale'] = ratio_pref_scale
            self.user_preferences[user_id_str]['max_consecutive_same_shift_override'] = max_same_shift_override

            messagebox.showinfo("Erfolg", f"Präferenzen für Benutzer {user_id_str} gespeichert.", parent=self)

            self._load_user_preferences_overview()
            self._clear_input_fields()

        except ValueError as e:
            messagebox.showerror("Eingabefehler", f"Ungültige Eingabe: {e}", parent=self)
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self)

    def _delete_user_preferences(self):
        """ Löscht die Einstellungen für den ausgewählten Benutzer. """
        user_id_str = self.selected_user_id_var.get()
        if not user_id_str:
            messagebox.showerror("Fehler", "Bitte wählen Sie zuerst einen Mitarbeiter aus.", parent=self)
            return

        if messagebox.askyesno("Löschen bestätigen",
                               f"Möchten Sie alle benutzerdefinierten Präferenzen für Benutzer {user_id_str} wirklich löschen?",
                               parent=self):
            if user_id_str in self.user_preferences:
                self.user_preferences[user_id_str]['min_monthly_hours'] = None
                self.user_preferences[user_id_str]['max_monthly_hours'] = None
                self.user_preferences[user_id_str]['shift_exclusions'] = []
                self.user_preferences[user_id_str]['ratio_preference_scale'] = 50
                self.user_preferences[user_id_str]['max_consecutive_same_shift_override'] = None

                messagebox.showinfo("Erfolg",
                                    f"Präferenzen für Benutzer {user_id_str} gelöscht (auf Standard zurückgesetzt).",
                                    parent=self)

                self._load_user_preferences_overview()
                self._clear_input_fields()
            else:
                messagebox.showwarning("Warnung", f"Keine Präferenzen für Benutzer {user_id_str} gefunden.",
                                       parent=self)

    def _create_general_tab(self, master):
        """ Erstellt den ursprünglichen Tab für allgemeine Einstellungen und Partnerpräferenzen. """
        tab = ttk.Frame(master)

        # --- Algorithmus-Parameter ---
        general_frame = ttk.LabelFrame(tab, text="Algorithmus-Parameter")
        general_frame.pack(padx=10, pady=5, fill="x")

        # Max. gleiche Schichten nacheinander
        ttk.Label(general_frame, text="Max. gleiche Schichten nacheinander (Soft Limit):").grid(row=0, column=0, padx=5,
                                                                                                pady=5, sticky="w")
        self.max_same_shift_entry = ttk.Entry(general_frame, textvariable=self.max_same_shift_var, width=5)
        self.max_same_shift_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Min. freie Tage nach max. Arbeitstagen
        ttk.Label(general_frame, text="Min. freie Tage nach max. Arbeitstagen (Hard Rule):").grid(row=1, column=0,
                                                                                                  padx=5, pady=5,
                                                                                                  sticky="w")
        self.mandatory_rest_entry = ttk.Entry(general_frame, textvariable=self.mandatory_rest_days_after_max_shifts_var,
                                              width=5)
        self.mandatory_rest_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # 24h Planung
        ttk.Checkbutton(general_frame, text="24-Stunden-Schicht in Planung berücksichtigen (Vorerst inaktiv)",
                        variable=self.enable_24h_planning_var, state=tk.DISABLED).grid(row=2, column=0, columnspan=2,
                                                                                       padx=5, pady=5, sticky="w")

        # --- NEU: Score Konfiguration (Thresholds und Multiplikatoren) ---
        score_config_frame = ttk.LabelFrame(tab, text="Score-Konfiguration (Gewichtung und Schwellenwerte)")
        score_config_frame.pack(padx=10, pady=5, fill="x")

        # Score Multiplikatoren
        ttk.Label(score_config_frame, text="Gewichtungs-Multiplikatoren (Beeinflusst die Sortierung in Runde 1):",
                  font=("", 9, "bold")).grid(row=0, column=0, columnspan=3, padx=5, pady=(5, 0), sticky="w")

        row_idx = 1

        # PartnerScore Hinweis
        ttk.Label(score_config_frame, text="PartnerScore:", font=("", 9, "bold")).grid(row=row_idx, column=0, padx=5,
                                                                                       pady=2, sticky="w")
        ttk.Label(score_config_frame,
                  text="""Gewichtung ist **direkt** die Prioritäts-Zahl (1=höchste Prio) aus der Sektion 'Mitarbeiter-Präferenzen' (immer Faktor 1).""",
                  foreground="blue").grid(row=row_idx, column=1, columnspan=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # MinHrsScore Multiplier
        ttk.Label(score_config_frame, text="MinHrsScore Multiplikator:", font=("", 9, "bold")).grid(row=row_idx,
                                                                                                    column=0, padx=5,
                                                                                                    pady=2, sticky="w")
        ttk.Entry(score_config_frame, textvariable=self.min_hours_score_multiplier_var, width=5).grid(row=row_idx,
                                                                                                      column=1, padx=5,
                                                                                                      pady=2,
                                                                                                      sticky="w")
        ttk.Label(score_config_frame,
                  text="""Gewichtung, wenn Mitarbeiter die pers. Min. Stunden **deutlich** verfehlt. (Wird negativ gewichtet, höhere Zahl = höhere Chance, Dienst zu bekommen.)""").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # FairScore Multiplier
        ttk.Label(score_config_frame, text="FairScore Multiplikator:", font=("", 9, "bold")).grid(row=row_idx, column=0,
                                                                                                  padx=5, pady=2,
                                                                                                  sticky="w")
        ttk.Entry(score_config_frame, textvariable=self.fairness_score_multiplier_var, width=5).grid(row=row_idx,
                                                                                                     column=1, padx=5,
                                                                                                     pady=2, sticky="w")
        ttk.Label(score_config_frame,
                  text="""Gewichtung, wenn Mitarbeiter **deutlich** unter dem Durchschnitt liegt. (Wird negativ gewichtet, höhere Zahl = höhere Chance, Dienst zu bekommen.)""").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # IsoScore Multiplier
        ttk.Label(score_config_frame, text="IsoScore Multiplikator:", font=("", 9, "bold")).grid(row=row_idx, column=0,
                                                                                                 padx=5, pady=2,
                                                                                                 sticky="w")
        ttk.Entry(score_config_frame, textvariable=self.isolation_score_multiplier_var, width=5).grid(row=row_idx,
                                                                                                      column=1, padx=5,
                                                                                                      pady=2,
                                                                                                      sticky="w")
        ttk.Label(score_config_frame,
                  text="""Gewichtung des **Bestrafungs**-Scores für isolierte Dienste (z.B. F-F-D-F). (Wird positiv gewichtet, höhere Zahl = geringere Chance, Dienst zu bekommen.)""").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # RatioScore Hinweis
        ttk.Label(score_config_frame, text="RatioScore:", font=("", 9, "bold")).grid(row=row_idx, column=0, padx=5,
                                                                                     pady=(5, 2), sticky="w")
        ttk.Label(score_config_frame,
                  text="""Gewichtung erfolgt **automatisch** über die T./N. Präferenzen (Skala 0-100) im Tab 'Benutzer-Sonderfaktoren'.""",
                  foreground="blue").grid(row=row_idx, column=1, columnspan=2, padx=5, pady=(5, 2), sticky="w")
        row_idx += 1

        # Score Schwellenwerte (Thresholds)
        ttk.Label(score_config_frame, text="Stunden-Schwellenwerte (Löst die Scores aus):", font=("", 9, "bold")).grid(
            row=row_idx, column=0, columnspan=3, padx=5, pady=(10, 0), sticky="w")
        row_idx += 1

        # Fairness Threshold Hours
        ttk.Label(score_config_frame, text="Fairness Stunden-Schwelle (FairScore):").grid(row=row_idx, column=0, padx=5,
                                                                                          pady=2, sticky="w")
        ttk.Entry(score_config_frame, textvariable=self.fairness_threshold_hours_var, width=5).grid(row=row_idx,
                                                                                                    column=1, padx=5,
                                                                                                    pady=2, sticky="w")
        ttk.Label(score_config_frame,
                  text="* Ab dieser Differenz (Durchschnitt - User-Stunden) wird **FairScore 1** vergeben.").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # Min Hours Fairness Threshold
        ttk.Label(score_config_frame, text="Min. Stunden-Schwelle (MinHrsScore):").grid(row=row_idx, column=0, padx=5,
                                                                                        pady=2, sticky="w")
        self.min_hours_fairness_threshold_entry = ttk.Entry(score_config_frame,
                                                            textvariable=self.min_hours_fairness_threshold_var, width=5)
        self.min_hours_fairness_threshold_entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky="w")
        ttk.Label(score_config_frame,
                  text="* Ab dieser Differenz (MinHrs - User-Stunden) wird **MinHrsScore 5** vergeben.").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        score_config_frame.columnconfigure(2, weight=1)
        # --- ENDE Score Konfiguration ---

        # --- Generator Prioritäten und Regeln ---
        priority_rules_frame = ttk.LabelFrame(tab, text="Generator Prioritäten und Regeln")
        priority_rules_frame.pack(padx=10, pady=5, fill="x")

        # 1. Unterbesetzung vermeiden (Hard Limit-Regime in Runde 2)
        ttk.Checkbutton(priority_rules_frame,
                        text="Unterbesetzung um jeden Preis vermeiden (Ignoriert einige Soft Limits in Runde 2)",
                        variable=self.avoid_understaffing_hard_var).grid(row=0, column=0, columnspan=3, padx=5, pady=2,
                                                                         sticky="w")

        # 2. Ein Wochenende frei
        ttk.Checkbutton(priority_rules_frame,
                        text="Mindestens ein freies WE pro Monat gewährleisten (Hard Rule, nur wenn möglich)",
                        variable=self.ensure_one_weekend_off_var).grid(row=1, column=0, columnspan=3, padx=5, pady=2,
                                                                       sticky="w")

        # 3. Wunschfrei-Priorität (Scale)
        ttk.Label(priority_rules_frame, text="Wunschfrei-Respekt-Level (0=Ignorieren, 100=Sehr Hohe Prio):").grid(row=2,
                                                                                                                  column=0,
                                                                                                                  padx=5,
                                                                                                                  pady=5,
                                                                                                                  sticky="w")

        # Slider für die Priorität
        self.wunschfrei_scale = ttk.Scale(priority_rules_frame,
                                          from_=0, to=100,
                                          orient="horizontal",
                                          command=lambda v: self.wunschfrei_respect_level_var.set(round(float(v))),
                                          variable=self.wunschfrei_respect_level_var)
        self.wunschfrei_scale.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Anzeige des aktuellen Werts
        self.wunschfrei_display = ttk.Label(priority_rules_frame, textvariable=self.wunschfrei_respect_level_var)
        self.wunschfrei_display.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        priority_rules_frame.columnconfigure(1, weight=1)
        # --- ENDE Generator Prioritäten ---

        # --- Mitarbeiter-Präferenzen mit Priorität ---
        pref_frame = ttk.LabelFrame(tab, text="Mitarbeiter-Präferenzen (Priorisierte Zusammenarbeit)")
        pref_frame.pack(padx=10, pady=5, fill="both", expand=True)

        ttk.Label(pref_frame, text="Bevorzugte Arbeits-Partner auswählen und Priorität festlegen (1=höchste):").pack(
            padx=5, pady=5, anchor="w")

        # Frame für die Eingabe
        input_frame = ttk.Frame(pref_frame)
        input_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(input_frame, text="Mitarbeiter A:").grid(row=0, column=0, padx=(0, 5), pady=2, sticky='w')
        self.combo_a = ttk.Combobox(input_frame, textvariable=self.partner_a_var, values=self.user_options,
                                    state="readonly", width=20)
        self.combo_a.grid(row=0, column=1, padx=(0, 10), pady=2, sticky='ew')
        ttk.Label(input_frame, text="Mitarbeiter B:").grid(row=1, column=0, padx=(0, 5), pady=2, sticky='w')
        self.combo_b = ttk.Combobox(input_frame, textvariable=self.partner_b_var, values=self.user_options,
                                    state="readonly", width=20)
        self.combo_b.grid(row=1, column=1, padx=(0, 10), pady=2, sticky='ew')
        ttk.Label(input_frame, text="Priorität (Zahl):").grid(row=0, column=2, padx=(10, 5), pady=2, sticky='w')
        self.prio_entry = ttk.Entry(input_frame, textvariable=self.priority_var, width=5)
        self.prio_entry.grid(row=0, column=3, pady=2, sticky='w')
        input_frame.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ttk.Frame(pref_frame)
        btn_frame.pack(fill='x', padx=5, pady=(10, 5))
        ttk.Button(btn_frame, text="Priorisierte Partner hinzufügen", command=self._add_partner).pack(side='left',
                                                                                                      padx=(0, 5))
        ttk.Button(btn_frame, text="Auswahl entfernen", command=self._remove_partner).pack(side='left')

        # Liste
        ttk.Label(pref_frame, text="Aktuelle Präferenzen (Mitarbeiter A | Mitarbeiter B | Priorität):").pack(padx=5,
                                                                                                             pady=5,
                                                                                                             anchor="w")
        self.listbox = tk.Listbox(pref_frame, height=8)
        self.listbox.pack(padx=5, pady=5, fill="both", expand=True)
        self._load_preferred_partners()

        return tab

    def _create_user_preferences_tab(self, master):
        """ Erstellt den neuen Tab für benutzerspezifische Einstellungen mit Treeview-Übersicht. """
        tab = ttk.Frame(master)

        # Frame für Mitarbeiter-Auswahl & Eingabe (oben)
        input_controls_frame = ttk.LabelFrame(tab, text="Mitarbeiter-Präferenzen bearbeiten")
        input_controls_frame.pack(padx=10, pady=5, fill="x")

        # Auswahl des Mitarbeiters (Combobox)
        select_frame = ttk.Frame(input_controls_frame)
        select_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(select_frame, text="Mitarbeiter auswählen (für NEU/Edit oder Auswahl leeren):").grid(row=0, column=0,
                                                                                                       padx=5, pady=5,
                                                                                                       sticky='w')
        self.user_pref_combo = ttk.Combobox(select_frame, values=self.user_options, state="readonly", width=30)
        self.user_pref_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.user_pref_combo.bind("<<ComboboxSelected>>", self._load_selected_user_pref_from_combobox)
        ttk.Button(select_frame, text="Eingaben leeren", command=self._clear_input_fields).grid(row=0, column=2, padx=5,
                                                                                                pady=5, sticky='w')
        select_frame.columnconfigure(1, weight=1)

        # Einstellungsfelder
        settings_frame = ttk.Frame(input_controls_frame)
        settings_frame.pack(fill="x", padx=5, pady=5)

        row_idx = 0

        # Min. Monatsstunden
        ttk.Label(settings_frame, text="Min. Monatsstunden (Zahl):").grid(row=row_idx, column=0, padx=5, pady=2,
                                                                          sticky='w')
        self.min_hours_entry = ttk.Entry(settings_frame, textvariable=self.min_hours_var, width=10)
        self.min_hours_entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(settings_frame, text="* Soft Limit (Erhöht Zuweisungs-Score bei Unterschreitung)").grid(row=row_idx,
                                                                                                          column=2,
                                                                                                          padx=5,
                                                                                                          pady=2,
                                                                                                          sticky='w')
        row_idx += 1

        # Max. Monatsstunden
        ttk.Label(settings_frame, text="Max. Monatsstunden (Zahl):").grid(row=row_idx, column=0, padx=5, pady=2,
                                                                          sticky='w')
        self.max_hours_entry = ttk.Entry(settings_frame, textvariable=self.max_hours_var, width=10)
        self.max_hours_entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(settings_frame, text="* Hard Rule Override (Überschreibt 228h nur nach unten)").grid(row=row_idx,
                                                                                                       column=2, padx=5,
                                                                                                       pady=2,
                                                                                                       sticky='w')
        row_idx += 1

        # Max. gleiche Schichten nacheinander Override (Soft Limit)
        ttk.Label(settings_frame, text="Max. gleiche Schichten nacheinander (Override):").grid(row=row_idx, column=0,
                                                                                               padx=5, pady=2,
                                                                                               sticky='w')
        self.max_same_shift_override_entry = ttk.Entry(settings_frame, textvariable=self.max_same_shift_override_var,
                                                       width=10)
        self.max_same_shift_override_entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(settings_frame, text="* Überschreibt globalen Soft Limit").grid(row=row_idx, column=2, padx=5, pady=2,
                                                                                  sticky='w')
        row_idx += 1

        # Verhältnis-Präferenz (T. vs N.)
        ttk.Label(settings_frame, text="Tages-/Nacht-Verhältnis-Präferenz (0=Nacht, 100=Tag):").grid(row=row_idx,
                                                                                                     column=0, padx=5,
                                                                                                     pady=2, sticky='w')

        ratio_frame = ttk.Frame(settings_frame)
        ratio_frame.grid(row=row_idx, column=1, padx=5, pady=2, sticky='ew')
        ttk.Scale(ratio_frame, from_=0, to=100, variable=self.ratio_pref_scale_var,
                  orient=tk.HORIZONTAL, command=self._update_ratio_label).pack(side=tk.LEFT, fill='x', expand=True)

        ttk.Label(settings_frame, textvariable=self.ratio_pref_label_var, width=25).grid(row=row_idx, column=2, padx=5,
                                                                                         pady=2, sticky='w')
        self._update_ratio_label(self.ratio_pref_scale_var.get())
        row_idx += 1

        # Schicht-Ausschlüsse (Hard Limit)
        ttk.Label(settings_frame, text="Schicht-Ausschlüsse (Kürzel, kommasepariert):").grid(row=row_idx, column=0,
                                                                                             padx=5, pady=2, sticky='w')
        self.shift_exclusions_entry = ttk.Entry(settings_frame, textvariable=self.shift_exclusions_list_var, width=20)
        self.shift_exclusions_entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(settings_frame, text=f"* Harte Sperre (z.B. 6, N.)").grid(row=row_idx, column=2, padx=5, pady=2,
                                                                            sticky='w')
        row_idx += 1

        # Buttons
        btn_frame = ttk.Frame(input_controls_frame)
        btn_frame.pack(fill='x', padx=5, pady=(10, 5))
        ttk.Button(btn_frame, text="Präferenzen SPEICHERN", command=self._save_user_preferences).pack(side='left',
                                                                                                      padx=(0, 5))
        ttk.Button(btn_frame, text="Präferenzen LÖSCHEN", command=self._delete_user_preferences).pack(side='left')

        # --- Übersicht (Treeview) ---
        overview_frame = ttk.LabelFrame(tab, text="Gespeicherte Sonderfaktoren (Doppelklick/Auswahl zum Bearbeiten)")
        overview_frame.pack(padx=10, pady=5, fill="both", expand=True)

        columns = ("#User", "MinHrs", "MaxHrs", "Excl", "RatioPref", "MaxSameOverride")
        self.treeview_prefs = ttk.Treeview(overview_frame, columns=columns, show="headings", height=8)

        # Spalten-Konfiguration
        self.treeview_prefs.heading("#User", text="Mitarbeiter", anchor=tk.W)
        self.treeview_prefs.heading("MinHrs", text="Min. Std", anchor=tk.CENTER)
        self.treeview_prefs.heading("MaxHrs", text="Max. Std", anchor=tk.CENTER)
        self.treeview_prefs.heading("Excl", text="Ausgeschl. Schichten", anchor=tk.W)
        self.treeview_prefs.heading("RatioPref", text="T./N. Präf.", anchor=tk.CENTER)
        self.treeview_prefs.heading("MaxSameOverride", text="Max. Gleiche", anchor=tk.CENTER)

        # Spaltenbreiten
        self.treeview_prefs.column("#User", width=150, stretch=tk.NO)
        self.treeview_prefs.column("MinHrs", width=70, anchor=tk.CENTER, stretch=tk.NO)
        self.treeview_prefs.column("MaxHrs", width=70, anchor=tk.CENTER, stretch=tk.NO)
        self.treeview_prefs.column("Excl", width=150, anchor=tk.W, stretch=tk.YES)
        self.treeview_prefs.column("RatioPref", width=100, anchor=tk.CENTER, stretch=tk.NO)
        self.treeview_prefs.column("MaxSameOverride", width=90, anchor=tk.CENTER, stretch=tk.NO)

        # Scrollbar hinzufügen
        scrollbar = ttk.Scrollbar(overview_frame, orient="vertical", command=self.treeview_prefs.yview)
        self.treeview_prefs.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.treeview_prefs.pack(side="left", fill="both", expand=True)

        self.treeview_prefs.bind('<<TreeviewSelect>>', self._load_selected_user_pref_from_treeview)

        self._load_user_preferences_overview()

        return tab

    def body(self, master):
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        general_tab = self._create_general_tab(self.notebook)
        self.notebook.add(general_tab, text="Allgemein & Partner")

        user_pref_tab = self._create_user_preferences_tab(self.notebook)
        self.notebook.add(user_pref_tab, text="Benutzer-Sonderfaktoren")

        return self.max_same_shift_entry

    def validate(self):
        # GEÄNDERT: Validierung um Float-Werte erweitert und neue Scores geprüft
        try:
            val_soft = int(self.max_same_shift_var.get())
            if val_soft <= 0:
                messagebox.showerror("Eingabefehler",
                                     "Der Wert für das Soft Limit (gleiche Schichten) muss eine positive ganze Zahl sein.",
                                     parent=self)
                return False

            val_rest = int(self.mandatory_rest_days_after_max_shifts_var.get())
            if val_rest < 0:
                messagebox.showerror("Eingabefehler",
                                     "Der Wert für die Min. freie Tage (Hard Rule) darf nicht negativ sein.",
                                     parent=self)
                return False

            val_wunschfrei = int(self.wunschfrei_respect_level_var.get())
            if not (0 <= val_wunschfrei <= 100):
                messagebox.showerror("Eingabefehler", "Der Wunschfrei-Prioritätswert muss zwischen 0 und 100 liegen.",
                                     parent=self)
                return False

            # NEU: Validierung der Score-Schwellenwerte und Multiplikatoren (Float-Werte)
            val_fair_thresh = float(self.fairness_threshold_hours_var.get())
            if val_fair_thresh <= 0: raise ValueError("Fairness-Schwelle muss positiv sein.")

            val_min_hrs_thresh = float(self.min_hours_fairness_threshold_var.get())
            if val_min_hrs_thresh <= 0: raise ValueError("Min. Stunden-Schwelle muss positiv sein.")

            val_min_hrs_mult = float(self.min_hours_score_multiplier_var.get())
            if val_min_hrs_mult <= 0: raise ValueError("MinHrsScore Multiplikator muss positiv sein.")

            val_fair_mult = float(self.fairness_score_multiplier_var.get())
            if val_fair_mult <= 0: raise ValueError("FairScore Multiplikator muss positiv sein.")

            val_iso_mult = float(self.isolation_score_multiplier_var.get())
            if val_iso_mult < 0: raise ValueError("IsoScore Multiplikator darf nicht negativ sein.")

            return True
        except ValueError as e:
            messagebox.showerror("Eingabefehler",
                                 f"Ein Wert muss eine gültige Zahl (Ganzzahl oder Dezimalzahl) sein: {e}", parent=self)
            return False

    def apply(self):
        # GEÄNDERT: Speichern der neuen Score-Multiplikatoren
        user_prefs_to_save = {}
        for uid_str, prefs in self.user_preferences.items():
            has_pref = any(v is not None and v != [] for k, v in prefs.items() if k != 'ratio_preference_scale')
            if prefs.get('ratio_preference_scale') != 50:
                has_pref = True

            if has_pref:
                user_prefs_to_save[uid_str] = prefs

        new_config = {
            'max_consecutive_same_shift': int(self.max_same_shift_var.get()),
            'mandatory_rest_days_after_max_shifts': int(self.mandatory_rest_days_after_max_shifts_var.get()),
            'enable_24h_planning': self.enable_24h_planning_var.get(),
            'preferred_partners_prioritized': self.preferred_partners,
            'user_preferences': user_prefs_to_save,
            # Generator Prioritäten
            'avoid_understaffing_hard': self.avoid_understaffing_hard_var.get(),
            'ensure_one_weekend_off': self.ensure_one_weekend_off_var.get(),
            'wunschfrei_respect_level': int(self.wunschfrei_respect_level_var.get()),
            # NEU: Score Schwellenwerte und Multiplikatoren
            'fairness_threshold_hours': float(self.fairness_threshold_hours_var.get()),
            'min_hours_fairness_threshold': float(self.min_hours_fairness_threshold_var.get()),
            'min_hours_score_multiplier': float(self.min_hours_score_multiplier_var.get()),
            'fairness_score_multiplier': float(self.fairness_score_multiplier_var.get()),
            'isolation_score_multiplier': float(self.isolation_score_multiplier_var.get())
        }

        print(f"[DEBUG] Speichere Konfiguration: {new_config}")

        if self.data_manager and hasattr(self.data_manager, 'save_generator_config'):
            try:
                success = self.data_manager.save_generator_config(new_config)
                print(f"[DEBUG] Ergebnis von save_generator_config: Success={success}")

                if success:
                    messagebox.showinfo("Speichern erfolgreich", "Generator-Einstellungen aktualisiert.")
                else:
                    messagebox.showwarning("Speicherfehler",
                                           "Fehler beim Speichern der Konfiguration in der Datenbank.\nDetails finden Sie in der Konsole.",
                                           parent=self)

            except Exception as e:
                print(f"[FEHLER] Kritischer Fehler beim Speichern der Generator-Konfiguration: {e}")
                traceback.print_exc()
                messagebox.showwarning("Speicherfehler",
                                       f"Ein unerwarteter Fehler ist beim Speichern aufgetreten:\n{e}", parent=self)
        else:
            messagebox.showwarning("Warnung", "Speicherfunktion (save_generator_config) im DataManager nicht gefunden.",
                                   parent=self)