# gui/generator/generator_config.py
# NEUE DATEI (Refactoring nach Regel 4)

from collections import defaultdict

# Standardwerte für Scores und Regeln
DEFAULT_FAIRNESS_THRESHOLD_HOURS = 10.0
DEFAULT_MIN_HOURS_FAIRNESS_THRESHOLD = 20.0
DEFAULT_MIN_HOURS_SCORE_MULT = 5.0
DEFAULT_FAIRNESS_SCORE_MULT = 1.0
DEFAULT_ISOLATION_SCORE_MULT = 30.0
DEFAULT_WUNSCHFREI_RESPECT = 75
DEFAULT_GENERATOR_FILL_ROUNDS = 3
DEFAULT_MANDATORY_REST_DAYS = 2
DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT = 4
AVOID_PARTNER_PENALTY_SCORE = 10000


class GeneratorConfig:
    """
    Kapselt das Laden, Parsen und Bereitstellen der Konfigurationseinstellungen
    für den ShiftPlanGenerator.
    """

    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.generator_config = {}

        # Generator-Konfiguration laden
        if self.data_manager and hasattr(self.data_manager, 'get_generator_config'):
            try:
                self.generator_config = self.data_manager.get_generator_config()
            except Exception as e:
                print(f"[FEHLER] Konnte Generator-Konfiguration nicht laden: {e}")

        # Alle Einstellungen beim Initialisieren laden
        self._load_settings()

    def _load_settings(self):
        """ Lädt alle Konfigurationswerte aus dem geladenen Diktat. """

        # 1. Allgemeine Regeln
        self.max_consecutive_same_shift_limit = self.generator_config.get(
            'max_consecutive_same_shift', DEFAULT_MAX_CONSECUTIVE_SAME_SHIFT
        )
        self.mandatory_rest_days = self.generator_config.get(
            'mandatory_rest_days_after_max_shifts', DEFAULT_MANDATORY_REST_DAYS
        )
        self.avoid_understaffing_hard = self.generator_config.get(
            'avoid_understaffing_hard', True
        )
        self.wunschfrei_respect_level = self.generator_config.get(
            'wunschfrei_respect_level', DEFAULT_WUNSCHFREI_RESPECT
        )
        self.generator_fill_rounds = self.generator_config.get(
            'generator_fill_rounds', DEFAULT_GENERATOR_FILL_ROUNDS
        )

        # 2. Scoring-Gewichtung
        self.fairness_threshold_hours = self.generator_config.get(
            'fairness_threshold_hours', DEFAULT_FAIRNESS_THRESHOLD_HOURS
        )
        self.min_hours_fairness_threshold = self.generator_config.get(
            'min_hours_fairness_threshold', DEFAULT_MIN_HOURS_FAIRNESS_THRESHOLD
        )
        self.min_hours_score_multiplier = self.generator_config.get(
            'min_hours_score_multiplier', DEFAULT_MIN_HOURS_SCORE_MULT
        )
        self.fairness_score_multiplier = self.generator_config.get(
            'fairness_score_multiplier', DEFAULT_FAIRNESS_SCORE_MULT
        )
        self.isolation_score_multiplier = self.generator_config.get(
            'isolation_score_multiplier', DEFAULT_ISOLATION_SCORE_MULT
        )

        # 3. Harte Strafen (derzeit nicht konfigurierbar, aber hier zentralisiert)
        self.AVOID_PARTNER_PENALTY_SCORE = AVOID_PARTNER_PENALTY_SCORE

        # 4. Benutzerdefinierte Einstellungen
        self._load_user_preferences()

        # 5. Partner-Einstellungen
        self._load_partner_maps()

    def _load_user_preferences(self):
        """ Lädt und parst die benutzerspezifischen Einstellungen. """
        default_user_pref = {
            'min_monthly_hours': None,
            'max_monthly_hours': None,
            'shift_exclusions': [],
            'ratio_preference_scale': 50,
            'max_consecutive_same_shift_override': None
        }
        raw_user_preferences = self.generator_config.get('user_preferences', {})
        self.user_preferences = defaultdict(lambda: default_user_pref.copy())

        for user_id_str, prefs in raw_user_preferences.items():
            if 'ratio_preference_scale' not in prefs:
                prefs['ratio_preference_scale'] = 50
            self.user_preferences[user_id_str].update(prefs)

    def _load_partner_maps(self):
        """ Lädt und parst die Listen für bevorzugte und zu vermeidende Partner. """

        # Bevorzugte Partner
        self.prioritized_partners_list = self.generator_config.get('preferred_partners_prioritized', [])
        self.partner_priority_map = defaultdict(list)
        for entry in self.prioritized_partners_list:
            try:
                id_a, id_b, prio = int(entry['id_a']), int(entry['id_b']), int(entry['priority'])
                self.partner_priority_map[id_a].append((prio, id_b))
                self.partner_priority_map[id_b].append((prio, id_a))
            except (ValueError, KeyError, TypeError):
                continue
        for user_id in self.partner_priority_map:
            self.partner_priority_map[user_id].sort(key=lambda x: x[0])

        # Zu vermeidende Partner
        self.avoid_partners_list = self.generator_config.get('avoid_partners_prioritized', [])
        self.avoid_priority_map = defaultdict(list)
        for entry in self.avoid_partners_list:
            try:
                id_a, id_b, prio = int(entry['id_a']), int(entry['id_b']), int(entry['priority'])
                # Prio 1 = Höchste Vermeidung
                self.avoid_priority_map[id_a].append((prio, id_b))
                self.avoid_priority_map[id_b].append((prio, id_a))
            except (ValueError, KeyError, TypeError):
                continue
        for user_id in self.avoid_priority_map:
            self.avoid_priority_map[user_id].sort(key=lambda x: x[0])