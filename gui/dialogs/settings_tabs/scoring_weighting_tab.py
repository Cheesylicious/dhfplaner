# gui/dialogs/settings_tabs/scoring_weighting_tab.py
import tkinter as tk
from tkinter import ttk, messagebox

try:
    from gui.tooltip import ToolTip
except ImportError:
    print("[WARNUNG] ToolTip-Modul nicht gefunden. Hilfe-Icons werden nicht angezeigt.")


    # Fallback, damit das Programm nicht abstürzt
    class ToolTip:
        def __init__(self, widget, text):
            pass


class ScoringWeightingTab(ttk.Frame):
    """
    Kapselt den "Scoring & Gewichtung" Tab der Generator-Einstellungen.
    JETZT MIT SLIDERN, Tooltips und "Benutzerdefiniert"-Logik.
    """

    def __init__(self, notebook, dialog):
        super().__init__(notebook, padding=10)
        self.dialog = dialog  # Referenz zum Hauptdialog

        self.presets = {
            "Standard (Ausbalanciert)": {
                'fair_thresh': 10.0, 'min_h_thresh': 20.0,
                'min_h_mult': 5.0, 'fair_mult': 1.0, 'iso_mult': 1.0
            },
            "Fokus: Mindeststunden": {
                'fair_thresh': 15.0, 'min_h_thresh': 25.0,
                'min_h_mult': 10.0, 'fair_mult': 0.5, 'iso_mult': 1.0
            },
            "Fokus: Fairness (Stundenausgleich)": {
                'fair_thresh': 5.0, 'min_h_thresh': 15.0,
                'min_h_mult': 2.0, 'fair_mult': 5.0, 'iso_mult': 1.0
            },
            "Fokus: Isolation vermeiden": {
                'fair_thresh': 10.0, 'min_h_thresh': 20.0,
                'min_h_mult': 3.0, 'fair_mult': 1.0, 'iso_mult': 50.0
            }
        }

        # NEU: "Benutzerdefiniert" zur Preset-Liste hinzufügen
        self.preset_options = ["Benutzerdefiniert"] + list(self.presets.keys())

        self._create_widgets()

    def _create_widgets(self):

        # --- Frame für Presets ---
        preset_frame = ttk.Labelframe(self, text="Voreinstellungen (Presets)", padding=10)
        preset_frame.pack(expand=True, fill="x", padx=5, pady=5)
        preset_frame.columnconfigure(0, weight=1)

        ttk.Label(preset_frame, text="Strategie-Vorlage auswählen:").pack(fill="x", pady=(0, 5))

        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.dialog.preset_var,
                                         values=self.preset_options, state="readonly")
        self.preset_combo.pack(fill="x", pady=5)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # --- Frame für Score-Schwellenwerte (weiterhin Entrys) ---
        threshold_frame = ttk.Labelframe(self, text="Score-Schwellenwerte (Wann wird ein Score aktiv?)", padding=10)
        threshold_frame.pack(expand=True, fill="x", padx=5, pady=5)
        threshold_frame.columnconfigure(1, weight=1)
        threshold_frame.columnconfigure(3, weight=0)  # Tooltip
        threshold_frame.columnconfigure(4, weight=1)
        threshold_frame.columnconfigure(6, weight=0)  # Tooltip

        row = 0
        ttk.Label(threshold_frame, text="Fairness-Schwelle (Std):").grid(row=row, column=0, sticky="w", pady=4,
                                                                         padx=(0, 5))
        ttk.Entry(threshold_frame, width=8, textvariable=self.dialog.fairness_threshold_hours_var).grid(row=row,
                                                                                                        column=1,
                                                                                                        sticky="w",
                                                                                                        pady=4)
        self._add_tooltip(threshold_frame, row, 3,
                          "Schwelle (in Stunden):\n"
                          "Wie viele Stunden muss ein MA *unter* dem Durchschnitt liegen,\n"
                          "bevor der 'Fairness-Score' überhaupt aktiv wird?")

        ttk.Label(threshold_frame, text="Min. Stunden-Schwelle (Std):").grid(row=row, column=4, sticky="w", pady=4,
                                                                             padx=(10, 5))
        ttk.Entry(threshold_frame, width=8, textvariable=self.dialog.min_hours_fairness_threshold_var).grid(row=row,
                                                                                                            column=5,
                                                                                                            sticky="w",
                                                                                                            pady=4)
        self._add_tooltip(threshold_frame, row, 6,
                          "Schwelle (in Stunden):\n"
                          "Wie viele Stunden muss ein MA *unter* seinen vertraglichen\n"
                          "Mindeststunden liegen, bevor der 'Min. Stunden-Score' aktiv wird?")

        # --- Frame für Score-Multiplikatoren (JETZT MIT SLIDERN) ---
        multiplier_frame = ttk.Labelframe(self, text="Score-Gewichtung (Wie stark wirkt ein Score?)", padding=10)
        multiplier_frame.pack(expand=True, fill="both", padx=5, pady=5)
        multiplier_frame.columnconfigure(1, weight=1)
        multiplier_frame.columnconfigure(2, weight=0)

        row = 0
        # Fairness Multiplikator
        ttk.Label(multiplier_frame, text="Fairness-Multiplikator:").grid(row=row, column=0, sticky="w", pady=6)
        self._add_tooltip(multiplier_frame, row, 2, "Stärke des 'Fairness-Scores' (Ausgleich zum Durchschnitt).")
        ttk.Scale(multiplier_frame, from_=0.1, to=10.0, orient="horizontal", length=200,
                  variable=self.dialog.fairness_score_multiplier_var).grid(row=row, column=1, sticky="ew", pady=6,
                                                                           padx=5)

        row += 1
        # Min. Stunden Multiplikator
        ttk.Label(multiplier_frame, text="Min. Stunden-Multiplikator:").grid(row=row, column=0, sticky="w", pady=6)
        self._add_tooltip(multiplier_frame, row, 2, "Stärke des 'Min. Stunden-Scores' (Erreichen der Vertragsstunden).")
        ttk.Scale(multiplier_frame, from_=0.1, to=10.0, orient="horizontal", length=200,
                  variable=self.dialog.min_hours_score_multiplier_var).grid(row=row, column=1, sticky="ew", pady=6,
                                                                            padx=5)

        row += 1
        # Isolation Multiplikator
        ttk.Label(multiplier_frame, text="Isolation-Multiplikator:").grid(row=row, column=0, sticky="w", pady=6)
        self._add_tooltip(multiplier_frame, row, 2,
                          "Stärke der *Strafe* für 'isolierte' Schichten (z.B. Frei-Dienst-Frei).")
        ttk.Scale(multiplier_frame, from_=0.0, to=100.0, orient="horizontal", length=200,
                  variable=self.dialog.isolation_score_multiplier_var).grid(row=row, column=1, sticky="ew", pady=6,
                                                                            padx=5)

    def _add_tooltip(self, parent, row, col, text):
        """Helper zum Hinzufügen eines (?) Icons mit Tooltip."""
        info_label = ttk.Label(parent, text=" (?)", cursor="question_arrow", foreground="blue")
        info_label.grid(row=row, column=col, sticky="w", padx=(0, 5))
        ToolTip(info_label, text)

    def _on_preset_selected(self, event=None):
        """Wendet die ausgewählte Voreinstellung auf die tk.Vars an."""
        preset_name = self.dialog.preset_var.get()

        if preset_name == "Benutzerdefiniert":
            return  # Nichts tun

        settings = self.presets.get(preset_name)
        if not settings:
            messagebox.showerror("Fehler", "Ausgewählte Voreinstellung nicht gefunden.", parent=self)
            return

        try:
            # Wichtig: Traces vorübergehend deaktivieren, damit das Setzen
            # der Werte nicht sofort wieder _mark_as_custom auslöst.
            self.dialog.fairness_threshold_hours_var.trace_remove("write",
                                                                  self.dialog.fairness_threshold_hours_var.trace_info()[
                                                                      0][1])
            self.dialog.min_hours_fairness_threshold_var.trace_remove("write",
                                                                      self.dialog.min_hours_fairness_threshold_var.trace_info()[
                                                                          0][1])
            self.dialog.min_hours_score_multiplier_var.trace_remove("write",
                                                                    self.dialog.min_hours_score_multiplier_var.trace_info()[
                                                                        0][1])
            self.dialog.fairness_score_multiplier_var.trace_remove("write",
                                                                   self.dialog.fairness_score_multiplier_var.trace_info()[
                                                                       0][1])
            self.dialog.isolation_score_multiplier_var.trace_remove("write",
                                                                    self.dialog.isolation_score_multiplier_var.trace_info()[
                                                                        0][1])

            self.dialog.fairness_threshold_hours_var.set(settings['fair_thresh'])
            self.dialog.min_hours_fairness_threshold_var.set(settings['min_h_thresh'])
            self.dialog.min_hours_score_multiplier_var.set(settings['min_h_mult'])
            self.dialog.fairness_score_multiplier_var.set(settings['fair_mult'])
            self.dialog.isolation_score_multiplier_var.set(settings['iso_mult'])

        finally:
            # Traces wieder hinzufügen
            self.dialog.after(50, self.dialog._add_traces_to_vars)

    def check_if_preset_matches(self):
        """Prüft, ob die aktuellen Einstellungen einem Preset entsprechen."""
        current_settings = {
            'fair_thresh': self.dialog.fairness_threshold_hours_var.get(),
            'min_h_thresh': self.dialog.min_hours_fairness_threshold_var.get(),
            'min_h_mult': self.dialog.min_hours_score_multiplier_var.get(),
            'fair_mult': self.dialog.fairness_score_multiplier_var.get(),
            'iso_mult': self.dialog.isolation_score_multiplier_var.get()
        }

        for name, preset_values in self.presets.items():
            if preset_values == current_settings:
                self.dialog.preset_var.set(name)
                return

        # Wenn kein Match gefunden wurde
        self.dialog.preset_var.set("Benutzerdefiniert")