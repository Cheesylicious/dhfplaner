# gui/dialogs/settings_tabs/general_rules_tab.py
import tkinter as tk
from tkinter import ttk

try:
    from gui.tooltip import ToolTip
except ImportError:
    print("[WARNUNG] ToolTip-Modul nicht gefunden. Hilfe-Icons werden nicht angezeigt.")


    # Fallback, damit das Programm nicht abstürzt
    class ToolTip:
        def __init__(self, widget, text):
            pass


class GeneralRulesTab(ttk.Frame):
    """
    Kapselt den "Allgemeine Regeln" Tab der Generator-Einstellungen.
    JETZT MIT TOOLTIPS.
    """

    def __init__(self, notebook, dialog):
        super().__init__(notebook, padding=10)
        self.dialog = dialog  # Referenz zum Hauptdialog

        self._create_widgets()

    def get_initial_focus_widget(self):
        return self.spin_max_same_shift

    def _create_widgets(self):
        # --- Frame 1: Grundregeln ---
        rules_frame = ttk.Labelframe(self, text="Grundregeln & Limiter", padding=10)
        rules_frame.pack(expand=True, fill="x", padx=5, pady=5)
        rules_frame.columnconfigure(1, weight=1)  # Label-Spalte
        rules_frame.columnconfigure(2, weight=0)  # Icon-Spalte
        rules_frame.columnconfigure(3, weight=0)  # Widget-Spalte

        row = 0
        # Max Consecutive Same Shift
        ttk.Label(rules_frame, text="Max. gleiche Schichten (Soft Limit):").grid(row=row, column=0, columnspan=2,
                                                                                 sticky="w", pady=3)
        self._add_tooltip(rules_frame, row, 2,
                          "Soft Limit (Runde 1):\n"
                          "Wie oft darf ein MA dieselbe Schicht (z.B. 'N.') in Folge planen,\n"
                          "bevor er dafür bestraft wird? (Standard: 4)")
        self.spin_max_same_shift = ttk.Spinbox(rules_frame, from_=1, to=10, width=7,
                                               textvariable=self.dialog.max_same_shift_var)
        self.spin_max_same_shift.grid(row=row, column=3, sticky="e", pady=3, padx=5)

        row += 1
        # Mandatory Rest Days
        ttk.Label(rules_frame, text="Min. freie Tage (nach Hard Limit):").grid(row=row, column=0, columnspan=2,
                                                                               sticky="w", pady=3)
        self._add_tooltip(rules_frame, row, 2,
                          "Harte Regel (Runde 1-4):\n"
                          "Wie viele Tage *muss* ein MA frei haben,\n"
                          "nachdem er die 'Hard Max Consecutive Shifts' (aktuell 8) erreicht hat?")
        ttk.Spinbox(rules_frame, from_=0, to=10, width=7,
                    textvariable=self.dialog.mandatory_rest_days_after_max_shifts_var).grid(row=row, column=3,
                                                                                            sticky="e", pady=3, padx=5)

        # --- Frame 2: Prioritäten & Verhalten ---
        prio_frame = ttk.Labelframe(self, text="Prioritäten & Verhalten", padding=10)
        prio_frame.pack(expand=True, fill="x", padx=5, pady=5)
        prio_frame.columnconfigure(1, weight=1)  # Label-Spalte
        prio_frame.columnconfigure(2, weight=0)  # Icon-Spalte
        prio_frame.columnconfigure(3, weight=0)  # Widget-Spalte

        row = 0
        # 24h Planung
        ttk.Checkbutton(prio_frame, text="24h-Dienste bei Planung berücksichtigen",
                        variable=self.dialog.enable_24h_planning_var).grid(row=row, column=0, columnspan=2,
                                                                           sticky="w", pady=5)

        row += 1
        # Prioritäten
        ttk.Checkbutton(prio_frame, text="Unterbesetzung (wenn möglich) hart vermeiden",
                        variable=self.dialog.avoid_understaffing_hard_var).grid(row=row, column=0, columnspan=2,
                                                                                sticky="w", pady=5)
        self._add_tooltip(prio_frame, row, 2,
                          "Wenn aktiv:\n"
                          "Der Generator bricht *eher* Soft-Regeln (z.B. Wunschfrei),\n"
                          "bevor eine Schicht unterbesetzt bleibt (Runde 2-4).")

        row += 1
        ttk.Checkbutton(prio_frame, text="Mindestens 1 freies Wochenende pro Monat erzwingen",
                        variable=self.dialog.ensure_one_weekend_off_var).grid(row=row, column=0, columnspan=2,
                                                                              sticky="w", pady=5)
        self._add_tooltip(prio_frame, row, 2,
                          "Experimentell:\n"
                          "Versucht, jedem MA mindestens ein komplettes\n"
                          "Wochenende (Sa/So) freizuhalten.")

        row += 1
        # Wunschfrei Respekt
        ttk.Label(prio_frame, text="Priorität 'Wunschfrei' (Soft Limit %):").grid(row=row, column=0, columnspan=2,
                                                                                  sticky="w",
                                                                                  pady=8)
        self._add_tooltip(prio_frame, row, 2,
                          "Wie stark wird 'Wunschfrei' in Runde 1 gewichtet?\n"
                          "Bei 100% wird Wunschfrei fast wie eine Hard-Regel behandelt.\n"
                          "Bei 0% wird es ignoriert (nicht empfohlen).")
        ttk.Scale(prio_frame, from_=0, to=100, orient="horizontal", length=150,
                  variable=self.dialog.wunschfrei_respect_level_var).grid(row=row, column=3, sticky="e", pady=8,
                                                                          padx=5)

        row += 1
        # Generator Runden
        ttk.Label(prio_frame, text="Anzahl Auffüllrunden:").grid(row=row, column=0, columnspan=2, sticky="w", pady=8)
        self._add_tooltip(prio_frame, row, 2,
                          "Definiert, wie aggressiv Lücken gefüllt werden:\n"
                          "0: Nur Runde 1 (Fairness)\n"
                          "1: +Runde 2 (ignoriert Wunschfrei)\n"
                          "2: +Runde 3 (ignoriert N-F-T)\n"
                          "3: +Runde 4 (ignoriert Ruhezeit-Regel)")

        round_frame = ttk.Frame(prio_frame)
        round_frame.grid(row=row, column=3, sticky="e", padx=5)
        ttk.Scale(round_frame, from_=0, to=3, orient="horizontal", length=120,
                  variable=self.dialog.generator_fill_rounds_var, command=self._update_rounds_label).grid(row=0,
                                                                                                          column=0,
                                                                                                          sticky="we")
        ttk.Label(round_frame, textvariable=self.dialog.generator_fill_rounds_label_var, width=18, anchor="e").grid(
            row=0, column=1, sticky="e", padx=(5, 0))
        self._update_rounds_label(self.dialog.generator_fill_rounds_var.get())  # Initiales Label setzen

    def _add_tooltip(self, parent, row, col, text):
        """Helper zum Hinzufügen eines (?) Icons mit Tooltip."""
        info_label = ttk.Label(parent, text=" (?)", cursor="question_arrow", foreground="blue")
        info_label.grid(row=row, column=col, sticky="w", padx=(0, 5))
        ToolTip(info_label, text)

    def _update_rounds_label(self, value):
        val = int(float(value))
        labels = {
            0: "Keine (Nur Runde 1)",
            1: "Runde 2 (Wunschfrei)",
            2: "Runde 2+3 (Alle)",
            3: "Runde 2+3+4 (Aggressiv)"
        }
        self.dialog.generator_fill_rounds_label_var.set(labels.get(val, ""))