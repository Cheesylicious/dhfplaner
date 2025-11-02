# gui/dialogs/generator_settings_window.py
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import traceback
from collections import defaultdict
from database.db_users import get_ordered_users_for_schedule

# NEU: Aufgeteilte Importe für die Tabs
from .settings_tabs.general_rules_tab import GeneralRulesTab
from .settings_tabs.scoring_weighting_tab import ScoringWeightingTab
from .settings_tabs.social_tab import SocialTab
from .settings_tabs.user_preferences_tab import UserPreferencesTab


class GeneratorSettingsWindow(simpledialog.Dialog):
    """
    Dialog zur Konfiguration des automatischen Schichtplangenerators.
    Jetzt aufgeteilt in vier logische Tabs für bessere Übersichtlichkeit.
    INKLUSIVE: Preset-Logik mit "Benutzerdefiniert".
    """

    def __init__(self, app, parent, data_manager):
        self.app = app
        self.data_manager = data_manager
        if not self.data_manager:
            print("[FEHLER] DataManager Instanz wurde NICHT an GeneratorSettingsWindow übergeben!")

        # --- Konfiguration laden (unverändert) ---
        self.config = {}
        if self.data_manager and hasattr(self.data_manager, 'get_generator_config'):
            try:
                loaded_config = self.data_manager.get_generator_config()
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

        # --- Initialisierung aller tk.Variablen ---

        # 1. Tab: Allgemeine Regeln
        self.max_same_shift_var = tk.IntVar(value=self.config.get('max_consecutive_same_shift', 4))
        self.enable_24h_planning_var = tk.BooleanVar(value=self.config.get('enable_24h_planning', False))
        self.mandatory_rest_days_after_max_shifts_var = tk.IntVar(
            value=self.config.get('mandatory_rest_days_after_max_shifts', 2))
        self.avoid_understaffing_hard_var = tk.BooleanVar(value=self.config.get('avoid_understaffing_hard', True))
        self.ensure_one_weekend_off_var = tk.BooleanVar(value=self.config.get('ensure_one_weekend_off', False))
        self.wunschfrei_respect_level_var = tk.IntVar(value=self.config.get('wunschfrei_respect_level', 75))
        self.generator_fill_rounds_var = tk.IntVar(value=self.config.get('generator_fill_rounds', 3))
        self.generator_fill_rounds_label_var = tk.StringVar()  # Für das Label

        # 2. Tab: Scoring & Gewichtung
        self.fairness_threshold_hours_var = tk.DoubleVar(value=self.config.get('fairness_threshold_hours', 10.0))
        self.min_hours_fairness_threshold_var = tk.DoubleVar(
            value=self.config.get('min_hours_fairness_threshold', 20.0))
        self.min_hours_score_multiplier_var = tk.DoubleVar(value=self.config.get('min_hours_score_multiplier', 5.0))
        self.fairness_score_multiplier_var = tk.DoubleVar(value=self.config.get('fairness_score_multiplier', 1.0))
        self.isolation_score_multiplier_var = tk.DoubleVar(value=self.config.get('isolation_score_multiplier', 1.0))

        # NEU: Preset-Variable. "Benutzerdefiniert" ist jetzt eine gültige Option.
        self.preset_var = tk.StringVar(value="Benutzerdefiniert")

        # 3. Tab: Soziale Bindungen (Listen)
        self.preferred_partners = self._load_partner_list(self.config.get('preferred_partners_prioritized', []))
        self.avoid_partners = self._load_partner_list(self.config.get('avoid_partners_prioritized', []))

        self.partner_a_var = tk.StringVar(value="")
        self.partner_b_var = tk.StringVar(value="")
        self.priority_var = tk.StringVar(value="1")
        self.avoid_partner_a_var = tk.StringVar(value="")
        self.avoid_partner_b_var = tk.StringVar(value="")
        self.avoid_priority_var = tk.StringVar(value="1")

        # 4. Tab: Mitarbeiter-Präferenzen (Listen)
        default_user_pref = {
            'min_monthly_hours': None, 'max_monthly_hours': None, 'shift_exclusions': [],
            'ratio_preference_scale': 50, 'max_consecutive_same_shift_override': None
        }
        raw_user_preferences = self.config.get('user_preferences', {})
        self.user_preferences = defaultdict(lambda: default_user_pref.copy())
        for user_id_str, prefs in raw_user_preferences.items():
            if 'ratio_preference_scale' not in prefs: prefs['ratio_preference_scale'] = 50
            self.user_preferences[user_id_str].update(prefs)

        self.selected_user_id_var = tk.StringVar(value="")
        self.min_hours_var = tk.StringVar(value="")
        self.max_hours_var = tk.StringVar(value="")
        self.ratio_pref_scale_var = tk.IntVar(value=50)
        self.ratio_pref_label_var = tk.StringVar(value="Neutral (0% Bias)")
        self.max_same_shift_override_var = tk.StringVar(value="")
        self.shift_exclusions_list_var = tk.StringVar(value="")

        # NEU: Variable für den "Kopieren Von"-Dialog
        self.copy_from_user_var = tk.StringVar(value="")

        # --- Lade Benutzerdaten (unverändert) ---
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

        self.all_shift_abbrevs = sorted(list(self.app.shift_types_data.keys())) if self.app and hasattr(self.app,
                                                                                                        'shift_types_data') else [
            "T.", "N.", "6", "24", "U", "EU"]

        super().__init__(parent, title="Generator-Einstellungen")

        # NEU: Traces hinzufügen, um bei Änderung auf "Benutzerdefiniert" zu setzen
        self._add_traces_to_vars()
        # Initialen Preset-Status prüfen
        self._check_preset_status()

    def _add_traces_to_vars(self):
        """Fügt 'write' traces zu allen Scoring-Variablen hinzu."""
        scoring_vars = [
            self.fairness_threshold_hours_var,
            self.min_hours_fairness_threshold_var,
            self.min_hours_score_multiplier_var,
            self.fairness_score_multiplier_var,
            self.isolation_score_multiplier_var
        ]
        for var in scoring_vars:
            var.trace_add("write", self._mark_as_custom)

    def _mark_as_custom(self, *args):
        """Setzt die Preset-Combobox auf 'Benutzerdefiniert'."""
        if self.preset_var.get() != "Benutzerdefiniert":
            self.preset_var.set("Benutzerdefiniert")

    def _check_preset_status(self):
        """Prüft beim Start, ob die geladenen Werte einem Preset entsprechen."""
        if hasattr(self, 'scoring_tab'):  # Stellt sicher, dass der Tab existiert
            self.scoring_tab.check_if_preset_matches()

    def _load_partner_list(self, raw_list):
        # (unverändert)
        processed_list = []
        for p in raw_list:
            if isinstance(p, dict) and 'id_a' in p and 'id_b' in p and 'priority' in p:
                try:
                    id_a = int(p['id_a']);
                    id_b = int(p['id_b']);
                    priority = int(p['priority'])
                    processed_list.append({'id_a': min(id_a, id_b), 'id_b': max(id_a, id_b), 'priority': priority})
                except (ValueError, TypeError):
                    print(f"[WARNUNG] Ungültiger Partnereintrag ignoriert (Typfehler): {p}")
                    continue
            else:
                print(f"[WARNUNG] Ungültiges Partnerdatenformat ignoriert (Strukturfehler): {p}")

        processed_list.sort(key=lambda x: (x['id_a'], x['priority']))
        return processed_list

    def _get_user_info(self, user_id):
        # (unverändert)
        user = self.user_map.get(user_id)
        name_parts = [user.get('vorname')] if user and user.get('vorname') else []
        name_parts.append(user.get('lastname', user.get('name', 'Unbekannt')) if user else 'Unbekannt')
        full_name = " ".join(filter(None, name_parts))
        return f"{user_id} ({full_name})" if user else f"ID {user_id} (Unbekannt)"

    def body(self, master):
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=(10, 0))

        # --- NEUE TAB-STRUKTUR (unverändert) ---
        self.rules_tab = GeneralRulesTab(self.notebook, self)
        self.notebook.add(self.rules_tab, text="Allgemeine Regeln")

        self.scoring_tab = ScoringWeightingTab(self.notebook, self)
        self.notebook.add(self.scoring_tab, text="Scoring & Gewichtung")

        self.social_tab = SocialTab(self.notebook, self)
        self.notebook.add(self.social_tab, text="Soziale Bindungen")

        self.user_pref_tab = UserPreferencesTab(self.notebook, self)
        self.notebook.add(self.user_pref_tab, text="Mitarbeiter-Präferenzen")

        # Wichtig: Wir rufen _check_preset_status, *nachdem* alle Tabs (insb. scoring_tab) erstellt wurden
        self.after(100, self._check_preset_status)

        return self.rules_tab.get_initial_focus_widget()

    def validate(self):
        # (unverändert)
        try:
            val_soft = int(self.max_same_shift_var.get())
            if val_soft <= 0: raise ValueError("Soft Limit muss positiv sein.")
            val_rest = int(self.mandatory_rest_days_after_max_shifts_var.get())
            if val_rest < 0: raise ValueError("Ruhetage dürfen nicht negativ sein.")
            val_wunschfrei = int(self.wunschfrei_respect_level_var.get())
            if not (0 <= val_wunschfrei <= 100): raise ValueError("Wunschfrei-Prio muss 0-100 sein.")
            val_rounds = int(self.generator_fill_rounds_var.get())
            if not (0 <= val_rounds <= 3): raise ValueError("Auffüllrunden müssen 0-3 sein.")

            # Scoring-Werte
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
            messagebox.showerror("Eingabefehler", f"Ein Wert ist ungültig: {e}", parent=self)
            return False

    def apply(self):
        # (unverändert)
        user_prefs_to_save = {}
        for uid_str, prefs in self.user_preferences.items():
            has_pref = any(v is not None and v != [] for k, v in prefs.items() if k != 'ratio_preference_scale')
            if prefs.get('ratio_preference_scale') != 50: has_pref = True
            if has_pref: user_prefs_to_save[uid_str] = prefs

        new_config = {
            'max_consecutive_same_shift': int(self.max_same_shift_var.get()),
            'mandatory_rest_days_after_max_shifts': int(self.mandatory_rest_days_after_max_shifts_var.get()),
            'enable_24h_planning': self.enable_24h_planning_var.get(),
            'avoid_understaffing_hard': self.avoid_understaffing_hard_var.get(),
            'ensure_one_weekend_off': self.ensure_one_weekend_off_var.get(),
            'wunschfrei_respect_level': int(self.wunschfrei_respect_level_var.get()),
            'generator_fill_rounds': int(self.generator_fill_rounds_var.get()),
            'fairness_threshold_hours': float(self.fairness_threshold_hours_var.get()),
            'min_hours_fairness_threshold': float(self.min_hours_fairness_threshold_var.get()),
            'min_hours_score_multiplier': float(self.min_hours_score_multiplier_var.get()),
            'fairness_score_multiplier': float(self.fairness_score_multiplier_var.get()),
            'isolation_score_multiplier': float(self.isolation_score_multiplier_var.get()),
            'preferred_partners_prioritized': self.preferred_partners,
            'avoid_partners_prioritized': self.avoid_partners,
            'user_preferences': user_prefs_to_save,
        }

        print(f"[DEBUG] Speichere Konfiguration: {new_config}")

        if self.data_manager and hasattr(self.data_manager, 'save_generator_config'):
            try:
                success = self.data_manager.save_generator_config(new_config)
                if success:
                    messagebox.showinfo("Speichern erfolgreich", "Generator-Einstellungen aktualisiert.", parent=self)
                else:
                    messagebox.showwarning("Speicherfehler", "Fehler beim Speichern der Konfiguration.", parent=self)
            except Exception as e:
                print(f"[FEHLER] Kritischer Fehler beim Speichern der Generator-Konfiguration: {e}")
                traceback.print_exc()
                messagebox.showwarning("Speicherfehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}", parent=self)
        else:
            messagebox.showwarning("Warnung", "Speicherfunktion (save_generator_config) nicht gefunden.", parent=self)