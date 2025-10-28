# gui/dialogs/generator_settings_window.py
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import traceback
from collections import defaultdict
# Import der Datenbank-Funktion, um Benutzerdaten zu laden
from database.db_users import get_ordered_users_for_schedule

# NEU: Imports für die ausgelagerten Tabs
from .settings_tabs.general_settings_tab import GeneralSettingsTab
from .settings_tabs.user_preferences_tab import UserPreferencesTab


class GeneratorSettingsWindow(simpledialog.Dialog):
    """
    Dialog zur Konfiguration des automatischen Schichtplangenerators.
    Besteht aus mehreren Tabs (ausgelagert in settings_tabs/), die die
    Logik für Soft Limits, priorisierte Mitarbeiter-Präferenzen und
    benutzerspezifische Sonderfaktoren enthalten.
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

        # NEU: Anzahl der Auffüllrunden (0=Keine, 1=Runde 2, 2=Runde 2+3, 3=Runde 2+3+4)
        self.generator_fill_rounds_var = tk.IntVar(value=self.config.get('generator_fill_rounds', 3))
        self.generator_fill_rounds_label_var = tk.StringVar()  # Für das Label neben dem Slider

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

        # Variablen für UI-Elemente (Allgemein Tab)
        self.partner_a_var = tk.StringVar(value="")
        self.partner_b_var = tk.StringVar(value="")
        self.priority_var = tk.StringVar(value="1")

        # Variablen für User-Präferenzen UI (Benutzer-Sonderfaktoren Tab)
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

        # Treeview-Referenz wird im Tab selbst gespeichert
        # self.treeview_prefs = None

        super().__init__(parent, title="Generator-Einstellungen")

    def _get_user_info(self, user_id):
        """
        Helper-Methode, die von beiden Tabs verwendet wird, um Benutzer-Infos abzurufen.
        """
        user = self.user_map.get(user_id)
        name_parts = [user.get('vorname')] if user and user.get('vorname') else []
        name_parts.append(user.get('lastname', user.get('name', 'Unbekannt')) if user else 'Unbekannt')
        full_name = " ".join(filter(None, name_parts))

        return f"{user_id} ({full_name})" if user else f"ID {user_id} (Unbekannt)"

    # --- Methoden für Partner-Logik sind in GeneralSettingsTab ---

    # --- Methoden für User-Präferenzen-Logik sind in UserPreferencesTab ---

    def body(self, master):
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Erstellt den "Allgemein & Partner"-Tab aus der ausgelagerten Klasse
        self.general_tab = GeneralSettingsTab(self.notebook, self)
        self.notebook.add(self.general_tab, text="Allgemein & Partner")

        # Erstellt den "Benutzer-Sonderfaktoren"-Tab aus der ausgelagerten Klasse
        self.user_pref_tab = UserPreferencesTab(self.notebook, self)
        self.notebook.add(self.user_pref_tab, text="Benutzer-Sonderfaktoren")

        # Gibt das Widget zurück, das den initialen Fokus erhalten soll
        # (wird von der GeneralSettingsTab-Klasse bereitgestellt)
        return self.general_tab.get_initial_focus_widget()

    def validate(self):
        # Validierung greift auf Variablen zu, die in self (Dialog) gespeichert sind
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

            # NEU: Validierung für Runden-Anzahl
            val_rounds = int(self.generator_fill_rounds_var.get())
            if not (0 <= val_rounds <= 3):
                messagebox.showerror("Eingabefehler", "Die Anzahl der Auffüllrunden muss zwischen 0 und 3 liegen.",
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
        # Apply sammelt alle Daten (Variablen aus self und Listen/Dicts aus self)
        # und speichert die Konfiguration.

        # Nur Benutzer-Präferenzen speichern, die vom Standard abweichen
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
            'generator_fill_rounds': int(self.generator_fill_rounds_var.get()),  # NEU
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