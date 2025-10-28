# gui/dialogs/settings_tabs/social_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
import re


class SocialTab(ttk.Frame):
    """
    Kapselt den "Soziale Bindungen" Tab (Partner & Konflikte)
    der Generator-Einstellungen.
    """

    def __init__(self, notebook, dialog):
        super().__init__(notebook, padding=10)
        self.dialog = dialog  # Referenz zum Hauptdialog

        self._create_widgets()
        self._load_partner_lists()

    def _create_widgets(self):
        # --- Frame für Partner-Management (in einem PanedWindow) ---
        partner_pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        partner_pane.pack(expand=True, fill="both", padx=5, pady=5)

        # --- Frame für Bevorzugte Partner ---
        pref_partner_frame = self._create_partner_frame(partner_pane,
                                                        text="Bevorzugte Partner (Zusammenarbeit)",
                                                        partner_a_var=self.dialog.partner_a_var,
                                                        partner_b_var=self.dialog.partner_b_var,
                                                        priority_var=self.dialog.priority_var,
                                                        treeview_name="treeview_partners",
                                                        add_command=self._add_preferred_partner,
                                                        remove_command=self._remove_preferred_partner)
        partner_pane.add(pref_partner_frame, weight=1)

        # --- Frame für Zu Vermeidende Partner ---
        avoid_partner_frame = self._create_partner_frame(partner_pane,
                                                         text="Zu vermeidende Paare (Konflikte)",
                                                         partner_a_var=self.dialog.avoid_partner_a_var,
                                                         partner_b_var=self.dialog.avoid_partner_b_var,
                                                         priority_var=self.dialog.avoid_priority_var,
                                                         treeview_name="treeview_avoid_partners",
                                                         add_command=self._add_avoid_partner,
                                                         remove_command=self._remove_avoid_partner)
        partner_pane.add(avoid_partner_frame, weight=1)

    def _create_partner_frame(self, parent, text, partner_a_var, partner_b_var, priority_var,
                              treeview_name, add_command, remove_command):
        """Helper-Funktion, um einen Frame für Partner (bevorzugt oder vermieden) zu erstellen."""
        frame = ttk.Labelframe(parent, text=text, padding=10)

        # Eingabe-Frame
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill="x", pady=5)

        ttk.Label(input_frame, text="Mitarbeiter A:").grid(row=0, column=0, padx=(0, 5))
        combo_a = ttk.Combobox(input_frame, textvariable=partner_a_var, values=self.dialog.user_options, width=20)
        combo_a.grid(row=0, column=1, padx=5)

        ttk.Label(input_frame, text="Mitarbeiter B:").grid(row=0, column=2, padx=(10, 5))
        combo_b = ttk.Combobox(input_frame, textvariable=partner_b_var, values=self.dialog.user_options, width=20)
        combo_b.grid(row=0, column=3, padx=5)

        ttk.Label(input_frame, text="Priorität (1=Hoch):").grid(row=0, column=4, padx=(10, 5))
        spin_prio = ttk.Spinbox(input_frame, from_=1, to=100, width=4, textvariable=priority_var)
        spin_prio.grid(row=0, column=5, padx=5)

        add_button = ttk.Button(input_frame, text="Hinzufügen", command=add_command, width=10)
        add_button.grid(row=0, column=6, padx=(10, 0))

        # Treeview-Frame (Liste)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(expand=True, fill="both", pady=5)

        tree = ttk.Treeview(tree_frame, columns=("id_a", "name_a", "id_b", "name_b", "priority"),
                            show="headings", height=4)
        tree.heading("id_a", text="ID A")
        tree.heading("name_a", text="Name A")
        tree.heading("id_b", text="ID B")
        tree.heading("name_b", text="Name B")
        tree.heading("priority", text="Prio (1=Hoch)")

        tree.column("id_a", width=40, anchor="center")
        tree.column("name_a", width=120)
        tree.column("id_b", width=40, anchor="center")
        tree.column("name_b", width=120)
        tree.column("priority", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        tree.pack(expand=True, fill="both")

        # Speichert die Treeview-Referenz im Hauptdialog
        setattr(self.dialog, treeview_name, tree)

        # Button-Frame (Löschen)
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=(5, 0))
        remove_button = ttk.Button(button_frame, text="Ausgewähltes Paar entfernen", command=remove_command)
        remove_button.pack(side="right")

        return frame

    def _parse_user_id(self, user_string):
        """ Extrahiert die ID (Zahl) aus dem Combobox-String, z.B. '123 (Name)'. """
        if not user_string: return None
        match = re.match(r"(\d+)", user_string)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                return None
        return None

    def _load_partner_lists(self):
        """Lädt beide Listen (Bevorzugt und Vermieden) in ihre jeweiligen Treeviews."""
        # Bevorzugte Partner laden
        if hasattr(self.dialog, 'treeview_partners'):
            self.dialog.treeview_partners.delete(*self.dialog.treeview_partners.get_children())
            for entry in self.dialog.preferred_partners:
                id_a, id_b, prio = entry['id_a'], entry['id_b'], entry['priority']
                name_a = self.dialog._get_user_info(id_a)
                name_b = self.dialog._get_user_info(id_b)
                self.dialog.treeview_partners.insert("", "end", values=(id_a, name_a, id_b, name_b, prio))

        # Zu vermeidende Partner laden
        if hasattr(self.dialog, 'treeview_avoid_partners'):
            self.dialog.treeview_avoid_partners.delete(*self.dialog.treeview_avoid_partners.get_children())
            for entry in self.dialog.avoid_partners:
                id_a, id_b, prio = entry['id_a'], entry['id_b'], entry['priority']
                name_a = self.dialog._get_user_info(id_a)
                name_b = self.dialog._get_user_info(id_b)
                self.dialog.treeview_avoid_partners.insert("", "end", values=(id_a, name_a, id_b, name_b, prio))

    # --- Logik für Bevorzugte Partner ---
    def _add_preferred_partner(self):
        id_a, id_b, prio = self._validate_partner_input(self.dialog.partner_a_var,
                                                        self.dialog.partner_b_var,
                                                        self.dialog.priority_var)
        if id_a is None: return

        # Prüfen, ob Kombination schon existiert
        if any(e['id_a'] == id_a and e['id_b'] == id_b for e in self.dialog.preferred_partners):
            messagebox.showwarning("Hinweis", "Dieses Partner-Paar existiert bereits.", parent=self.dialog)
            return

        self.dialog.preferred_partners.append({'id_a': id_a, 'id_b': id_b, 'priority': prio})
        self.dialog.preferred_partners.sort(key=lambda x: (x['id_a'], x['priority']))
        self._load_partner_lists()
        self.dialog.partner_a_var.set("");
        self.dialog.partner_b_var.set("");
        self.dialog.priority_var.set("1")

    def _remove_preferred_partner(self):
        self._remove_partner_from_list(self.dialog.treeview_partners, self.dialog.preferred_partners)

    # --- Logik für Zu Vermeidende Partner ---
    def _add_avoid_partner(self):
        id_a, id_b, prio = self._validate_partner_input(self.dialog.avoid_partner_a_var,
                                                        self.dialog.avoid_partner_b_var,
                                                        self.dialog.avoid_priority_var)
        if id_a is None: return

        # Prüfen, ob Kombination schon existiert
        if any(e['id_a'] == id_a and e['id_b'] == id_b for e in self.dialog.avoid_partners):
            messagebox.showwarning("Hinweis", "Dieses Vermeidungs-Paar existiert bereits.", parent=self.dialog)
            return

        self.dialog.avoid_partners.append({'id_a': id_a, 'id_b': id_b, 'priority': prio})
        self.dialog.avoid_partners.sort(key=lambda x: (x['id_a'], x['priority']))
        self._load_partner_lists()
        self.dialog.avoid_partner_a_var.set("");
        self.dialog.avoid_partner_b_var.set("");
        self.dialog.avoid_priority_var.set("1")

    def _remove_avoid_partner(self):
        self._remove_partner_from_list(self.dialog.treeview_avoid_partners, self.dialog.avoid_partners)

    # --- Gemeinsame Helper-Methoden ---
    def _validate_partner_input(self, var_a, var_b, var_prio):
        """Validiert die Eingabe für ein Partner-Paar und gibt (id_a, id_b, prio) oder (None, None, None) zurück."""
        id_a = self._parse_user_id(var_a.get())
        id_b = self._parse_user_id(var_b.get())
        try:
            prio = int(var_prio.get())
        except ValueError:
            messagebox.showerror("Fehler", "Priorität muss eine Zahl sein.", parent=self.dialog);
            return None, None, None

        if not id_a or not id_b:
            messagebox.showerror("Fehler", "Bitte wählen Sie zwei Mitarbeiter aus.", parent=self.dialog);
            return None, None, None
        if id_a == id_b:
            messagebox.showerror("Fehler", "Mitarbeiter A und B dürfen nicht identisch sein.", parent=self.dialog);
            return None, None, None
        if prio <= 0:
            messagebox.showerror("Fehler", "Priorität muss positiv sein (1=Hoch).", parent=self.dialog);
            return None, None, None

        # Normalisieren (ID A < ID B)
        if id_a > id_b: id_a, id_b = id_b, id_a
        return id_a, id_b, prio

    def _remove_partner_from_list(self, treeview, partner_list):
        """Entfernt einen ausgewählten Eintrag aus der angegebenen Liste und lädt die Treeviews neu."""
        selected_item = treeview.focus()
        if not selected_item:
            messagebox.showerror("Fehler", "Kein Paar zum Entfernen ausgewählt.", parent=self.dialog)
            return

        values = treeview.item(selected_item, 'values')
        if not values: return

        try:
            id_a, id_b = int(values[0]), int(values[2])
            entry_to_remove = next((e for e in partner_list if e['id_a'] == id_a and e['id_b'] == id_b), None)

            if entry_to_remove:
                partner_list.remove(entry_to_remove)
                self._load_partner_lists()
            else:
                messagebox.showerror("Fehler", "Interner Fehler: Paar nicht in der Liste gefunden.", parent=self.dialog)
        except (ValueError, TypeError, IndexError):
            messagebox.showerror("Fehler", "Fehler beim Lesen der Auswahl.", parent=self.dialog)