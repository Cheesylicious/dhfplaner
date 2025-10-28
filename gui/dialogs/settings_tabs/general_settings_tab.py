# gui/dialogs/settings_tabs/general_settings_tab.py
import tkinter as tk
from tkinter import ttk, messagebox


class GeneralSettingsTab(ttk.Frame):
    """
    Dieser Frame kapselt alle UI-Elemente und die Logik für den
    "Allgemein & Partner"-Tab des GeneratorSettingsWindow.
    """

    def __init__(self, parent, dialog):
        """
        Initialisiert den Tab-Frame.

        Args:
            parent: Das übergeordnete Widget (das Notebook).
            dialog: Die Instanz des Hauptdialogs (GeneratorSettingsWindow),
                    um auf geteilte Daten (Variablen, Konfigs, Methoden) zuzugreifen.
        """
        super().__init__(parent)
        self.dialog = dialog
        self.app = dialog.app

        # UI-Elemente erstellen
        self._create_widgets()

        # Initialisiert das Label für den Runden-Slider
        self._update_fill_rounds_label(self.dialog.generator_fill_rounds_var.get())

    def _update_fill_rounds_label(self, value_str):
        """ Aktualisiert das Label für den Runden-Slider. """
        try:
            val = int(float(value_str))
            labels = {
                0: "0: Nur Runde 1 (Fair)",
                1: "1: Runde 2 (Standard Fill)",
                2: "2: Runde 3 (Locker N-F-T)",
                3: "3: Runde 4 (Locker Ruhezeit)"
            }
            self.dialog.generator_fill_rounds_label_var.set(labels.get(val, f"Runde {val}"))
        except ValueError:
            self.dialog.generator_fill_rounds_label_var.set("Ungültig")

    def _create_widgets(self):
        """ Erstellt den Inhalt des "Allgemein & Partner"-Tabs. """
        tab = self  # Wir fügen die Widgets direkt zu diesem Frame hinzu

        # --- Algorithmus-Parameter ---
        general_frame = ttk.LabelFrame(tab, text="Algorithmus-Parameter")
        general_frame.pack(padx=10, pady=5, fill="x")

        # Max. gleiche Schichten nacheinander
        ttk.Label(general_frame, text="Max. gleiche Schichten nacheinander (Soft Limit):").grid(row=0, column=0, padx=5,
                                                                                                pady=5, sticky="w")
        # Greift auf die Variable im Hauptdialog zu
        self.max_same_shift_entry = ttk.Entry(general_frame, textvariable=self.dialog.max_same_shift_var, width=5)
        self.max_same_shift_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Min. freie Tage nach max. Arbeitstagen
        ttk.Label(general_frame, text="Min. freie Tage nach max. Arbeitstagen (Hard Rule):").grid(row=1, column=0,
                                                                                                  padx=5, pady=5,
                                                                                                  sticky="w")
        self.mandatory_rest_entry = ttk.Entry(general_frame,
                                              textvariable=self.dialog.mandatory_rest_days_after_max_shifts_var,
                                              width=5)
        self.mandatory_rest_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # 24h Planung
        ttk.Checkbutton(general_frame, text="24-Stunden-Schicht in Planung berücksichtigen (Vorerst inaktiv)",
                        variable=self.dialog.enable_24h_planning_var, state=tk.DISABLED).grid(row=2, column=0,
                                                                                              columnspan=2,
                                                                                              padx=5, pady=5,
                                                                                              sticky="w")

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
        ttk.Entry(score_config_frame, textvariable=self.dialog.min_hours_score_multiplier_var, width=5).grid(
            row=row_idx,
            column=1,
            padx=5,
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
        ttk.Entry(score_config_frame, textvariable=self.dialog.fairness_score_multiplier_var, width=5).grid(row=row_idx,
                                                                                                            column=1,
                                                                                                            padx=5,
                                                                                                            pady=2,
                                                                                                            sticky="w")
        ttk.Label(score_config_frame,
                  text="""Gewichtung, wenn Mitarbeiter **deutlich** unter dem Durchschnitt liegt. (Wird negativ gewichtet, höhere Zahl = höhere Chance, Dienst zu bekommen.)""").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # IsoScore Multiplier
        ttk.Label(score_config_frame, text="IsoScore Multiplikator:", font=("", 9, "bold")).grid(row=row_idx, column=0,
                                                                                                 padx=5, pady=2,
                                                                                                 sticky="w")
        ttk.Entry(score_config_frame, textvariable=self.dialog.isolation_score_multiplier_var, width=5).grid(
            row=row_idx,
            column=1,
            padx=5,
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
        ttk.Entry(score_config_frame, textvariable=self.dialog.fairness_threshold_hours_var, width=5).grid(row=row_idx,
                                                                                                           column=1,
                                                                                                           padx=5,
                                                                                                           pady=2,
                                                                                                           sticky="w")
        ttk.Label(score_config_frame,
                  text="* Ab dieser Differenz (Durchschnitt - User-Stunden) wird **FairScore 1** vergeben.").grid(
            row=row_idx, column=2, padx=5, pady=2, sticky="w")
        row_idx += 1

        # Min Hours Fairness Threshold
        ttk.Label(score_config_frame, text="Min. Stunden-Schwelle (MinHrsScore):").grid(row=row_idx, column=0, padx=5,
                                                                                        pady=2, sticky="w")
        self.min_hours_fairness_threshold_entry = ttk.Entry(score_config_frame,
                                                            textvariable=self.dialog.min_hours_fairness_threshold_var,
                                                            width=5)
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
                        variable=self.dialog.avoid_understaffing_hard_var).grid(row=0, column=0, columnspan=3, padx=5,
                                                                                pady=2,
                                                                                sticky="w")

        # 2. Ein Wochenende frei
        ttk.Checkbutton(priority_rules_frame,
                        text="Mindestens ein freies WE pro Monat gewährleisten (Hard Rule, nur wenn möglich)",
                        variable=self.dialog.ensure_one_weekend_off_var).grid(row=1, column=0, columnspan=3, padx=5,
                                                                              pady=2,
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
                                          command=lambda v: self.dialog.wunschfrei_respect_level_var.set(
                                              round(float(v))),
                                          variable=self.dialog.wunschfrei_respect_level_var)
        self.wunschfrei_scale.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Anzeige des aktuellen Werts
        self.wunschfrei_display = ttk.Label(priority_rules_frame,
                                            textvariable=self.dialog.wunschfrei_respect_level_var)
        self.wunschfrei_display.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        # NEU: 4. Anzahl Auffüllrunden (Scale)
        ttk.Label(priority_rules_frame, text="Aggressivität (Auffüllrunden nach 'Fair'-Runde 1):").grid(row=3,
                                                                                                        column=0,
                                                                                                        padx=5,
                                                                                                        pady=5,
                                                                                                        sticky="w")

        # Slider für Runden (0-3)
        self.rounds_scale = ttk.Scale(priority_rules_frame,
                                      from_=0, to=3,
                                      orient="horizontal",
                                      command=self._update_fill_rounds_label,  # Lokale Helfermethode
                                      variable=self.dialog.generator_fill_rounds_var)
        self.rounds_scale.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # Anzeige des aktuellen Werts (Text)
        self.rounds_display = ttk.Label(priority_rules_frame,
                                        textvariable=self.dialog.generator_fill_rounds_label_var,
                                        width=25)  # Breite für längsten Text
        self.rounds_display.grid(row=3, column=2, padx=5, pady=5, sticky="w")

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
        self.combo_a = ttk.Combobox(input_frame, textvariable=self.dialog.partner_a_var,
                                    values=self.dialog.user_options,
                                    state="readonly", width=20)
        self.combo_a.grid(row=0, column=1, padx=(0, 10), pady=2, sticky='ew')
        ttk.Label(input_frame, text="Mitarbeiter B:").grid(row=1, column=0, padx=(0, 5), pady=2, sticky='w')
        self.combo_b = ttk.Combobox(input_frame, textvariable=self.dialog.partner_b_var,
                                    values=self.dialog.user_options,
                                    state="readonly", width=20)
        self.combo_b.grid(row=1, column=1, padx=(0, 10), pady=2, sticky='ew')
        ttk.Label(input_frame, text="Priorität (Zahl):").grid(row=0, column=2, padx=(10, 5), pady=2, sticky='w')
        self.prio_entry = ttk.Entry(input_frame, textvariable=self.dialog.priority_var, width=5)
        self.prio_entry.grid(row=0, column=3, pady=2, sticky='w')
        input_frame.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ttk.Frame(pref_frame)
        btn_frame.pack(fill='x', padx=5, pady=(10, 5))
        # Rufen Methoden dieser Klasse auf
        ttk.Button(btn_frame, text="Priorisierte Partner hinzufügen", command=self._add_partner).pack(side='left',
                                                                                                      padx=(0, 5))
        ttk.Button(btn_frame, text="Auswahl entfernen", command=self._remove_partner).pack(side='left')

        # Liste
        ttk.Label(pref_frame, text="Aktuelle Präferenzen (Mitarbeiter A | Mitarbeiter B | Priorität):").pack(padx=5,
                                                                                                             pady=5,
                                                                                                             anchor="w")
        self.listbox = tk.Listbox(pref_frame, height=8)
        self.listbox.pack(padx=5, pady=5, fill="both", expand=True)

        # Daten beim Erstellen laden
        self._load_preferred_partners()

    def get_initial_focus_widget(self):
        """
        Gibt das Widget zurück, das den initialen Fokus erhalten soll,
        wenn der Dialog geöffnet wird.
        """
        return self.max_same_shift_entry

    def _load_preferred_partners(self):
        """ Lädt die Partnerliste in die Listbox. """
        self.listbox.delete(0, tk.END)
        # Greift auf die Daten im Hauptdialog zu
        display_list = sorted(self.dialog.preferred_partners, key=lambda x: (x['id_a'], x['priority']))
        for p in display_list:
            # Greift auf die Helper-Methode im Hauptdialog zu
            user_a_info = self.dialog._get_user_info(p['id_a'])
            user_b_info = self.dialog._get_user_info(p['id_b'])
            self.listbox.insert(tk.END, f"{user_a_info} | {user_b_info} | Prio: {p['priority']}")

    def _add_partner(self):
        """ Fügt eine neue Partner-Priorisierung hinzu. """
        # Greift auf die Variablen im Hauptdialog zu
        selection_a = self.dialog.partner_a_var.get()
        selection_b = self.dialog.partner_b_var.get()
        priority_str = self.dialog.priority_var.get()

        if not selection_a or not selection_b:
            messagebox.showerror("Fehler", "Bitte wählen Sie beide Mitarbeiter aus.", parent=self.dialog)
            return

        try:
            priority = int(priority_str)
            if priority <= 0:
                messagebox.showerror("Fehler", "Priorität muss eine positive Zahl sein.", parent=self.dialog)
                return
        except ValueError:
            messagebox.showerror("Fehler", "Priorität muss eine gültige Zahl sein.", parent=self.dialog)
            return

        try:
            def extract_id(selection):
                return int(selection.split('(')[0].strip())

            id_a = extract_id(selection_a)
            id_b = extract_id(selection_b)

            if id_a == id_b:
                messagebox.showerror("Fehler", "Die Mitarbeiter A und B müssen sich unterscheiden.", parent=self.dialog)
                return

            if id_a not in self.dialog.user_map or id_b not in self.dialog.user_map:
                messagebox.showerror("Fehler", "Mindestens eine der Benutzer-IDs ist nicht aktiv oder ungültig.",
                                     parent=self.dialog)
                return

            user1_id = min(id_a, id_b)
            user2_id = max(id_a, id_b)

            existing_entry_index = -1
            # Greift auf die Daten im Hauptdialog zu
            for i, entry in enumerate(self.dialog.preferred_partners):
                if entry['id_a'] == user1_id and entry['id_b'] == user2_id:
                    existing_entry_index = i
                    break

            new_partner_entry = {'id_a': user1_id, 'id_b': user2_id, 'priority': priority}

            if existing_entry_index != -1:
                if self.dialog.preferred_partners[existing_entry_index]['priority'] == priority:
                    messagebox.showwarning("Duplikat",
                                           "Diese Partnerkombination mit dieser Priorität existiert bereits.",
                                           parent=self.dialog)
                    return
                else:
                    if messagebox.askyesno("Aktualisieren?",
                                           f"Diese Partnerkombination existiert bereits mit Priorität {self.dialog.preferred_partners[existing_entry_index]['priority']}.\nMöchten Sie die Priorität auf {priority} aktualisieren?",
                                           parent=self.dialog):
                        self.dialog.preferred_partners[existing_entry_index]['priority'] = priority
                    else:
                        return
            else:
                self.dialog.preferred_partners.append(new_partner_entry)

            self.dialog.preferred_partners.sort(key=lambda x: (x['id_a'], x['priority']))
            self._load_preferred_partners()  # Lokale Methode

            # Setzt die Variablen im Hauptdialog zurück
            self.dialog.partner_a_var.set("")
            self.dialog.partner_b_var.set("")
            self.dialog.priority_var.set("1")

        except ValueError:
            messagebox.showerror("Fehler", "Interner Fehler beim Parsen der Benutzer-ID.", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self.dialog)

    def _remove_partner(self):
        """ Entfernt die ausgewählte Partner-Priorisierung. """
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
            # Greift auf Daten im Hauptdialog zu
            for entry in self.dialog.preferred_partners:
                if entry['id_a'] == user1_id and entry['id_b'] == user2_id and entry['priority'] == prio:
                    entry_to_remove = entry
                    break

            if entry_to_remove:
                self.dialog.preferred_partners.remove(entry_to_remove)
                print(f"[DEBUG] Partner entfernt: {entry_to_remove}. Aktuell: {self.dialog.preferred_partners}")
                self._load_preferred_partners()  # Lokale Methode
            else:
                messagebox.showerror("Fehler", "Konnte den ausgewählten Eintrag intern nicht finden.",
                                     parent=self.dialog)

        except IndexError:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Eintrag zum Entfernen aus.",
                                   parent=self.dialog)
        except (ValueError, IndexError) as e:
            messagebox.showerror("Fehler", f"Fehler beim Parsen der Auswahl zum Entfernen: {e}", parent=self.dialog)