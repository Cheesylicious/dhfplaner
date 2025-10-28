# gui/dialogs/settings_tabs/user_preferences_tab.py
import tkinter as tk
from tkinter import ttk, messagebox

# NEU: Import der Tooltip-Klasse für eine sauberere Oberfläche
try:
    from gui.tooltip import ToolTip
except ImportError:
    print("[WARNUNG] Tooltip-Klasse konnte nicht importiert werden.")


    # Fallback, falls ToolTip nicht gefunden wird
    class ToolTip:
        def __init__(self, widget, text):
            pass  # Tut nichts, verhindert aber Absturz


class UserPreferencesTab(ttk.Frame):
    """
    Dieser Frame kapselt alle UI-Elemente und die Logik für den
    "Mitarbeiter-Präferenzen"-Tab des GeneratorSettingsWindow.
    (Überarbeitete, innovativere Version mit Tooltips und besserer Struktur)
    """

    def __init__(self, parent, dialog):
        """
        Initialisiert den Tab-Frame.

        Args:
            parent: Das übergeordnete Widget (das Notebook).
            dialog: Die Instanz des Hauptdialogs (GeneratorSettingsWindow),
                    um auf geteilte Daten (Variablen, Konfigs, Methoden) zuzugreifen.
        """
        super().__init__(parent, padding=10)
        self.dialog = dialog
        self.app = dialog.app

        # Referenzen für UI-Elemente, die in Methoden benötigt werden
        self.user_pref_combo = None
        self.treeview_prefs = None

        # UI-Elemente erstellen
        self._create_widgets()

    def _create_widgets(self):
        """ Erstellt den Inhalt des "Mitarbeiter-Präferenzen"-Tabs. """
        tab = self  # Wir fügen die Widgets direkt zu diesem Frame hinzu

        # --- Frame für Mitarbeiter-Auswahl & Eingabe (oben) ---
        input_controls_frame = ttk.LabelFrame(tab, text="Mitarbeiter-Präferenzen bearbeiten")
        input_controls_frame.pack(padx=5, pady=5, fill="x")

        # Auswahl des Mitarbeiters (Combobox)
        select_frame = ttk.Frame(input_controls_frame)
        select_frame.pack(fill='x', padx=10, pady=(10, 5))
        ttk.Label(select_frame, text="Mitarbeiter:").grid(row=0, column=0, padx=(0, 5), pady=5, sticky='w')

        # Greift auf user_options im Hauptdialog zu
        self.user_pref_combo = ttk.Combobox(select_frame, values=self.dialog.user_options, state="readonly", width=30)
        self.user_pref_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        # Bindet an lokale Methoden
        self.user_pref_combo.bind("<<ComboboxSelected>>", self._load_selected_user_pref_from_combobox)

        ttk.Button(select_frame, text="Eingaben leeren", command=self._clear_input_fields).grid(row=0, column=2, padx=5,
                                                                                                pady=5, sticky='e')
        select_frame.columnconfigure(1, weight=1)  # Combobox dehnt sich
        select_frame.columnconfigure(2, weight=0)

        # --- Einstellungsfelder (Neu strukturiert in 2 Spalten) ---
        settings_frame = ttk.Frame(input_controls_frame)
        settings_frame.pack(fill="x", padx=5, pady=5)
        settings_frame.columnconfigure(0, weight=1, uniform="group1")
        settings_frame.columnconfigure(1, weight=1, uniform="group1")

        # Linke Spalte: Stunden
        col_left_frame = ttk.Frame(settings_frame, padding=5)
        col_left_frame.grid(row=0, column=0, sticky='nsew', padx=5)

        # Min. Monatsstunden
        ttk.Label(col_left_frame, text="Min. Monatsstunden (Soft Limit):").pack(fill='x', anchor='w')
        self.min_hours_entry = ttk.Entry(col_left_frame, textvariable=self.dialog.min_hours_var, width=15)
        self.min_hours_entry.pack(fill='x', anchor='w', pady=(2, 10))
        ToolTip(self.min_hours_entry,
                text="Soft Limit: Erhöht den Zuweisungs-Score,\n"
                     "wenn die Stundenzahl des Mitarbeiters\n"
                     "diesen Wert unterschreitet. (Leer = Ignorieren)")

        # Max. Monatsstunden
        ttk.Label(col_left_frame, text="Max. Monatsstunden (Hard Limit):").pack(fill='x', anchor='w')
        self.max_hours_entry = ttk.Entry(col_left_frame, textvariable=self.dialog.max_hours_var, width=15)
        self.max_hours_entry.pack(fill='x', anchor='w', pady=(2, 10))
        ToolTip(self.max_hours_entry,
                text="Hard Limit: Überschreibt das globale Maximum\n"
                     "(z.B. 228h) nur nach unten. (Leer = Ignorieren)")

        # Max. gleiche Schichten nacheinander Override (Soft Limit)
        ttk.Label(col_left_frame, text="Max. gleiche Schichten (Soft Limit):").pack(fill='x', anchor='w')
        self.max_same_shift_override_entry = ttk.Entry(col_left_frame,
                                                       textvariable=self.dialog.max_same_shift_override_var,
                                                       width=15)
        self.max_same_shift_override_entry.pack(fill='x', anchor='w', pady=(2, 10))
        ToolTip(self.max_same_shift_override_entry,
                text="Soft Limit: Überschreibt den globalen Wert\n"
                     "für 'Max. gleiche Schichten nacheinander'.\n"
                     "(Leer = Ignorieren)")

        # Rechte Spalte: Präferenzen
        col_right_frame = ttk.Frame(settings_frame, padding=5)
        col_right_frame.grid(row=0, column=1, sticky='nsew', padx=5)

        # Verhältnis-Präferenz (T. vs N.)
        ttk.Label(col_right_frame, text="Tages-/Nacht-Bias (0=Nacht, 100=Tag):").pack(fill='x', anchor='w')
        ratio_frame = ttk.Frame(col_right_frame)
        ratio_frame.pack(fill='x', pady=(2, 0))

        scale = ttk.Scale(ratio_frame, from_=0, to=100, variable=self.dialog.ratio_pref_scale_var,
                          orient=tk.HORIZONTAL, command=self._update_ratio_label)
        scale.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 5))
        ToolTip(scale,
                text="Beeinflusst die Zuweisung von T. und N. Schichten.\n"
                     "50 = Neutral (Standard)\n"
                     "< 50 = Bevorzugt N.\n"
                     "> 50 = Bevorzugt T.")

        ratio_label = ttk.Label(ratio_frame, textvariable=self.dialog.ratio_pref_label_var, width=18, anchor='e')
        ratio_label.pack(side=tk.RIGHT)
        self._update_ratio_label(self.dialog.ratio_pref_scale_var.get())  # Initiales Label

        # Schicht-Ausschlüsse (Hard Limit)
        ttk.Label(col_right_frame, text="Schicht-Ausschlüsse (Hard Limit):").pack(fill='x', anchor='w', pady=(10, 0))
        self.shift_exclusions_entry = ttk.Entry(col_right_frame, textvariable=self.dialog.shift_exclusions_list_var,
                                                width=20)
        self.shift_exclusions_entry.pack(fill='x', anchor='w', pady=(2, 10))
        ToolTip(self.shift_exclusions_entry,
                text="Harte Sperre: Dieser Mitarbeiter wird niemals\n"
                     "für die hier eingetragenen Schichten geplant.\n"
                     "Format: T.,N.,6 (kommasepariert)")

        # --- Buttons ---
        btn_frame = ttk.Frame(input_controls_frame)
        btn_frame.pack(fill='x', padx=10, pady=(5, 10))
        ttk.Button(btn_frame, text="Präferenzen SPEICHERN", command=self._save_user_preferences).pack(side='left',
                                                                                                      padx=(0, 5))
        ttk.Button(btn_frame, text="Präferenzen LÖSCHEN", command=self._delete_user_preferences).pack(side='left')

        # --- Übersicht (Treeview) ---
        overview_frame = ttk.LabelFrame(tab, text="Gespeicherte Sonderfaktoren (Doppelklick/Auswahl zum Bearbeiten)")
        overview_frame.pack(padx=5, pady=5, fill="both", expand=True)

        columns = ("#User", "MinHrs", "MaxHrs", "Excl", "RatioPref", "MaxSameOverride")
        self.treeview_prefs = ttk.Treeview(overview_frame, columns=columns, show="headings", height=8)

        # Spalten-Konfiguration (Überschriften leicht angepasst)
        self.treeview_prefs.heading("#User", text="Mitarbeiter", anchor=tk.W)
        self.treeview_prefs.heading("MinHrs", text="Min. Std", anchor=tk.CENTER)
        self.treeview_prefs.heading("MaxHrs", text="Max. Std", anchor=tk.CENTER)
        self.treeview_prefs.heading("Excl", text="Ausgeschl. Schichten", anchor=tk.W)
        self.treeview_prefs.heading("RatioPref", text="T/N-Bias", anchor=tk.CENTER)  # Angepasst
        self.treeview_prefs.heading("MaxSameOverride", text="Max. Gleiche", anchor=tk.CENTER)

        # Spaltenbreiten
        self.treeview_prefs.column("#User", width=160, stretch=tk.NO)
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

        # Daten beim Erstellen laden
        self._load_user_preferences_overview()

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
            bias_perc = (50 - scale_val) * 2
            text = f"Nacht Bias ({bias_perc}%)"
        else:
            bias_perc = (scale_val - 50) * 2
            text = f"Tag Bias ({bias_perc}%)"

        # Greift auf Variable im Hauptdialog zu
        self.dialog.ratio_pref_label_var.set(text)

    # --- Methoden für User-Präferenzen (Logik unverändert) ---
    def _clear_input_fields(self):
        """ Setzt die Eingabefelder für Präferenzen zurück. """
        # Greift auf Variablen im Hauptdialog zu
        self.dialog.selected_user_id_var.set("")
        if self.user_pref_combo:
            self.user_pref_combo.set("")
        self.dialog.min_hours_var.set("")
        self.dialog.max_hours_var.set("")
        self.dialog.ratio_pref_scale_var.set(50)
        self._update_ratio_label(50)  # Lokale Methode
        self.dialog.max_same_shift_override_var.set("")
        self.dialog.shift_exclusions_list_var.set("")
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

            # Greift auf Daten im Hauptdialog zu
            user_config = self.dialog.user_preferences[user_id_str]

            # Greift auf Variablen im Hauptdialog zu
            self.dialog.selected_user_id_var.set(user_id_str)
            self.dialog.min_hours_var.set(str(user_config.get('min_monthly_hours', "")) if user_config.get(
                'min_monthly_hours') is not None else "")
            self.dialog.max_hours_var.set(str(user_config.get('max_monthly_hours', "")) if user_config.get(
                'max_monthly_hours') is not None else "")

            scale_val = user_config.get('ratio_preference_scale', 50)
            self.dialog.ratio_pref_scale_var.set(scale_val)
            self._update_ratio_label(scale_val)

            self.dialog.max_same_shift_override_var.set(
                str(user_config.get('max_consecutive_same_shift_override', "")) if user_config.get(
                    'max_consecutive_same_shift_override') is not None else "")
            self.dialog.shift_exclusions_list_var.set(", ".join(user_config.get('shift_exclusions', [])))

        except ValueError:
            messagebox.showerror("Fehler", "Ungültige Benutzer-ID-Formatierung.", parent=self.dialog)
            self._clear_input_fields()
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self.dialog)
            self._clear_input_fields()

    def _load_selected_user_pref_from_treeview(self, event=None):
        """ Lädt die Präferenzen des im Treeview ausgewählten Benutzers in die Eingabefelder. """
        try:
            selected_item = self.treeview_prefs.focus()
            if not selected_item:
                return

            user_id_str = selected_item
            user_id = int(user_id_str)

            # Greift auf Daten und Methoden im Hauptdialog zu
            user_config = self.dialog.user_preferences[user_id_str]
            user_info_str = self.dialog._get_user_info(user_id)

            self._clear_input_fields()

            if user_info_str in self.dialog.user_options:
                self.user_pref_combo.set(user_info_str)
            else:
                self.user_pref_combo.set("")

            # Greift auf Variablen im Hauptdialog zu
            self.dialog.selected_user_id_var.set(user_id_str)
            self.dialog.min_hours_var.set(str(user_config.get('min_monthly_hours', "")) if user_config.get(
                'min_monthly_hours') is not None else "")
            self.dialog.max_hours_var.set(str(user_config.get('max_monthly_hours', "")) if user_config.get(
                'max_monthly_hours') is not None else "")

            scale_val = user_config.get('ratio_preference_scale', 50)
            self.dialog.ratio_pref_scale_var.set(scale_val)
            self._update_ratio_label(scale_val)

            self.dialog.max_same_shift_override_var.set(
                str(user_config.get('max_consecutive_same_shift_override', "")) if user_config.get(
                    'max_consecutive_same_shift_override') is not None else "")
            self.dialog.shift_exclusions_list_var.set(", ".join(user_config.get('shift_exclusions', [])))

            # Selektion im Treeview setzen (falls durch Klick ausgelöst, ist sie schon gesetzt)
            self.treeview_prefs.selection_set(selected_item)


        except ValueError as e:
            print(f"[FEHLER] Fehler beim Laden der Präferenzen aus Treeview (ValueError): {e}")
            messagebox.showerror("Fehler", "Interner Fehler beim Laden der Benutzerdaten.", parent=self.dialog)
        except Exception as e:
            print(f"[FEHLER] Unerwarteter Fehler beim Laden der Präferenzen aus Treeview: {e}")
            messagebox.showerror("Fehler", f"Unerwarteter Fehler: {e}", parent=self.dialog)

    def _load_user_preferences_overview(self):
        """ Lädt alle gespeicherten Benutzer-Sonderfaktoren in das Treeview. """
        if not self.treeview_prefs: return

        self.treeview_prefs.delete(*self.treeview_prefs.get_children())

        # Greift auf Daten und Methoden im Hauptdialog zu
        sorted_user_ids = sorted(self.dialog.user_preferences.keys(),
                                 key=lambda uid_str: self.dialog.user_map.get(int(uid_str), {}).get('lastname',
                                                                                                    'Z' * 20))

        for user_id_str in sorted_user_ids:
            prefs = self.dialog.user_preferences[user_id_str]
            has_pref = any(v is not None and v != [] for k, v in prefs.items() if k != 'ratio_preference_scale')
            if prefs.get('ratio_preference_scale') != 50:
                has_pref = True

            if not has_pref:
                continue

            user_id = int(user_id_str)
            user_info = self.dialog._get_user_info(user_id)

            min_hrs_display = f"{prefs['min_monthly_hours']:.1f}" if prefs['min_monthly_hours'] is not None else ""
            max_hrs_display = f"{prefs['max_monthly_hours']:.1f}" if prefs['max_monthly_hours'] is not None else ""
            exclusions_display = ", ".join(prefs['shift_exclusions'])

            scale_val = prefs.get('ratio_preference_scale', 50)

            # Angepasste Anzeige-Logik für T/N-Bias
            if scale_val == 50:
                ratio_pref_display = "Neutral (0%)"
            elif scale_val < 50:
                bias_perc = (50 - scale_val) * 2
                ratio_pref_display = f"Nacht ({bias_perc}%)"
            else:
                bias_perc = (scale_val - 50) * 2
                ratio_pref_display = f"Tag ({bias_perc}%)"

            max_same_display = str(prefs['max_consecutive_same_shift_override']) if prefs[
                                                                                        'max_consecutive_same_shift_override'] is not None else ""

            self.treeview_prefs.insert("", tk.END, iid=user_id_str,
                                       values=(user_info, min_hrs_display, max_hrs_display, exclusions_display,
                                               ratio_pref_display, max_same_display))

    def _save_user_preferences(self):
        """ Speichert die aktuellen Einstellungen für den ausgewählten Benutzer. """
        # Greift auf Variablen im Hauptdialog zu
        user_id_str = self.dialog.selected_user_id_var.get()
        if not user_id_str:
            messagebox.showerror("Fehler", "Bitte wählen Sie zuerst einen Mitarbeiter aus.", parent=self.dialog)
            return

        try:
            # 1. Min Stunden
            min_hours_raw = self.dialog.min_hours_var.get().strip()
            min_hours = None
            if min_hours_raw:
                min_hours = float(min_hours_raw)
                if min_hours < 0: raise ValueError("Min. Stunden darf nicht negativ sein.")

            # 2. Max Stunden
            max_hours_raw = self.dialog.max_hours_var.get().strip()
            max_hours = None
            if max_hours_raw:
                max_hours = float(max_hours_raw)
                if max_hours <= 0: raise ValueError("Max. Stunden muss positiv sein.")

            if min_hours is not None and max_hours is not None and min_hours > max_hours:
                raise ValueError("Min. Stunden muss kleiner oder gleich Max. Stunden sein.")

            # 3. Ratio-Präferenz (Skala)
            ratio_pref_scale = self.dialog.ratio_pref_scale_var.get()
            if ratio_pref_scale < 0 or ratio_pref_scale > 100:
                raise ValueError("T./N. Skala muss zwischen 0 und 100 liegen.")

            # 4. Max gleiche Schichten Override
            max_same_shift_raw = self.dialog.max_same_shift_override_var.get().strip()
            max_same_shift_override = None
            if max_same_shift_raw:
                max_same_shift_override = int(max_same_shift_raw)
                if max_same_shift_override <= 0: raise ValueError("Max. gleiche Schichten muss positiv sein.")

            # 5. Schicht-Ausschlüsse
            exclusions_raw = self.dialog.shift_exclusions_list_var.get().upper().replace(' ', '')
            shift_exclusions = [abbr.strip() for abbr in exclusions_raw.split(',') if abbr.strip()]

            # Speichern (im Hauptdialog)
            self.dialog.user_preferences[user_id_str]['min_monthly_hours'] = min_hours
            self.dialog.user_preferences[user_id_str]['max_monthly_hours'] = max_hours
            self.dialog.user_preferences[user_id_str]['shift_exclusions'] = shift_exclusions
            self.dialog.user_preferences[user_id_str]['ratio_preference_scale'] = ratio_pref_scale
            self.dialog.user_preferences[user_id_str]['max_consecutive_same_shift_override'] = max_same_shift_override

            messagebox.showinfo("Erfolg", f"Präferenzen für Benutzer {user_id_str} gespeichert.", parent=self.dialog)

            self._load_user_preferences_overview()
            self._clear_input_fields()

        except ValueError as e:
            messagebox.showerror("Eingabefehler", f"Ungültige Eingabe: {e}", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self.dialog)

    def _delete_user_preferences(self):
        """ Löscht die Einstellungen für den ausgewählten Benutzer. """
        user_id_str = self.dialog.selected_user_id_var.get()
        if not user_id_str:
            messagebox.showerror("Fehler", "Bitte wählen Sie zuerst einen Mitarbeiter aus.", parent=self.dialog)
            return

        if messagebox.askyesno("Löschen bestätigen",
                               f"Möchten Sie alle benutzerdefinierten Präferenzen für Benutzer {user_id_str} wirklich löschen?",
                               parent=self.dialog):
            if user_id_str in self.dialog.user_preferences:
                # Setzt die Daten im Hauptdialog zurück
                self.dialog.user_preferences[user_id_str]['min_monthly_hours'] = None
                self.dialog.user_preferences[user_id_str]['max_monthly_hours'] = None
                self.dialog.user_preferences[user_id_str]['shift_exclusions'] = []
                self.dialog.user_preferences[user_id_str]['ratio_preference_scale'] = 50
                self.dialog.user_preferences[user_id_str]['max_consecutive_same_shift_override'] = None

                messagebox.showinfo("Erfolg",
                                    f"Präferenzen für Benutzer {user_id_str} gelöscht (auf Standard zurückgesetzt).",
                                    parent=self.dialog)

                self._load_user_preferences_overview()
                self._clear_input_fields()
            else:
                messagebox.showwarning("Warnung", f"Keine Präferenzen für Benutzer {user_id_str} gefunden.",
                                       parent=self.dialog)