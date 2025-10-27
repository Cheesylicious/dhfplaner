# gui/dialogs/generator_settings_window.py
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import traceback  # Für detailliertere Fehlerausgaben

# Import der Datenbank-Funktion, um Benutzerdaten zu laden
from database.db_users import get_ordered_users_for_schedule


class GeneratorSettingsWindow(simpledialog.Dialog):
    """
    Dialog zur Konfiguration des automatischen Schichtplangenerators.
    Enthält Soft Limits und priorisierte Mitarbeiter-Präferenzen.
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

        # Initialisiere Variablen
        self.max_same_shift_var = tk.IntVar(value=self.config.get('max_consecutive_same_shift', 4))
        self.enable_24h_planning_var = tk.BooleanVar(value=self.config.get('enable_24h_planning', False))

        # Partner-Liste mit Prioritäten laden
        # Format: [{'id_a': 1, 'id_b': 10, 'priority': 1}, {'id_a': 1, 'id_b': 5, 'priority': 2}, ...]
        raw_partners = self.config.get('preferred_partners_prioritized', [])  # Neuer Schlüssel
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
            print(f"[DEBUG] {len(self.user_options)} Benutzeroptionen für Comboboxen geladen.")
        except Exception as e:
            print(f"[FEHLER] Kritischer Fehler beim Laden der Benutzerdaten für Comboboxen: {e}")
            traceback.print_exc()

        # Variablen für UI-Elemente
        self.partner_a_var = tk.StringVar(value="")
        self.partner_b_var = tk.StringVar(value="")
        self.priority_var = tk.StringVar(value="1")  # Standard-Priorität 1

        super().__init__(parent, title="Generator-Einstellungen")

    def body(self, master):
        # --- Allgemein-Einstellungen ---
        general_frame = ttk.LabelFrame(master, text="Algorithmus-Parameter")
        general_frame.pack(padx=10, pady=5, fill="x")
        ttk.Label(general_frame, text="Max. gleiche Schichten nacheinander (Soft Limit):").grid(row=0, column=0, padx=5,
                                                                                                pady=5, sticky="w")
        self.max_same_shift_entry = ttk.Entry(general_frame, textvariable=self.max_same_shift_var, width=5)
        self.max_same_shift_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(general_frame, text="24-Stunden-Schicht in Planung berücksichtigen (Vorerst inaktiv)",
                        variable=self.enable_24h_planning_var, state=tk.DISABLED).grid(row=1, column=0, columnspan=2,
                                                                                       padx=5, pady=5, sticky="w")

        # --- Mitarbeiter-Präferenzen mit Priorität ---
        pref_frame = ttk.LabelFrame(master, text="Mitarbeiter-Präferenzen (Priorisierte Zusammenarbeit)")
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

        return self.max_same_shift_entry

    def _get_user_info(self, user_id):
        user = self.user_map.get(user_id)
        return f"{user_id} ({user.get('lastname', user.get('name', 'Unbekannt'))})" if user else f"ID {user_id} (Unbekannt)"

    def _load_preferred_partners(self):
        self.listbox.delete(0, tk.END)
        display_list = sorted(self.preferred_partners, key=lambda x: (x['id_a'], x['priority']))
        print(f"[DEBUG] _load_preferred_partners wird aufgerufen mit (sortiert): {display_list}")
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

    def validate(self):
        # (Unverändert)
        try:
            val = int(self.max_same_shift_var.get())
            if val <= 0:
                messagebox.showerror("Eingabefehler", "Der Wert für das Soft Limit muss eine positive ganze Zahl sein.",
                                     parent=self)
                return False
            return True
        except ValueError:
            messagebox.showerror("Eingabefehler", "Der Wert muss eine ganze Zahl sein.", parent=self)
            return False

    def apply(self):
        # Speichert die Konfiguration mit der neuen Struktur.
        new_config = {
            'max_consecutive_same_shift': int(self.max_same_shift_var.get()),
            'enable_24h_planning': self.enable_24h_planning_var.get(),
            'preferred_partners_prioritized': self.preferred_partners  # Speichert die Liste mit Prioritäten
        }

        print(f"[DEBUG] Speichere Konfiguration: {new_config}")

        if self.data_manager and hasattr(self.data_manager, 'save_generator_config'):
            try:
                # Erwartet nur einen booleschen Rückgabewert (True/False)
                success = self.data_manager.save_generator_config(new_config)
                print(f"[DEBUG] Ergebnis von save_generator_config: Success={success}")  # DEBUG

                if success:
                    messagebox.showinfo("Speichern erfolgreich", "Generator-Einstellungen aktualisiert.")
                else:
                    # Die Funktion save_config_json gibt bei Fehlern False zurück
                    messagebox.showwarning("Speicherfehler",
                                           "Fehler beim Speichern der Konfiguration in der Datenbank.\nDetails finden Sie in der Konsole.",
                                           parent=self)

            except Exception as e:
                # Fängt unerwartete Fehler beim Speichern ab
                print(f"[FEHLER] Kritischer Fehler beim Speichern der Generator-Konfiguration: {e}")
                traceback.print_exc()
                messagebox.showwarning("Speicherfehler",
                                       f"Ein unerwarteter Fehler ist beim Speichern aufgetreten:\n{e}", parent=self)
        else:
            # Diese Meldung sollte nicht mehr erscheinen, wenn die Übergabe in shift_plan_tab korrekt ist
            messagebox.showwarning("Warnung", "Speicherfunktion (save_generator_config) im DataManager nicht gefunden.",
                                   parent=self)