# gui/dialogs/settings_tabs/window_config_tab.py
# (NEUE DATEI - Regel 4)

import tkinter as tk
from tkinter import ttk, messagebox

# (Regel 4) Importiert den Manager, der die DB-Logik kapselt
from gui.window_manager import get_window_config, save_window_config, clear_window_config_cache
from database.db_roles import get_all_roles_details  # Um Rollen für das Dropdown zu laden


class WindowConfigTab(ttk.Frame):
    """
    Ein Einstellungs-Tab, der es Admins erlaubt, die
    Anzeigenamen und Registrierungs-Optionen der Hauptfenster
    zu bearbeiten (deine Anforderung).
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.config_data = {}
        self.all_roles = []
        self.widget_map = {}  # Speichert die erstellten Widgets pro Fenster-Key

        self._load_data()
        self._create_widgets()
        self._populate_ui()

    def _load_data(self):
        """Lädt die Konfiguration und die Rollenliste."""
        try:
            # (Regel 2) Lädt die Konfiguration aus der DB (via Manager)
            self.config_data = get_window_config(force_reload=True)
            # Lädt alle Rollennamen (für das Dropdown "Standard-Rolle")
            roles_details = get_all_roles_details()
            self.all_roles = sorted([role['name'] for role in roles_details])
            # Füge 'None' hinzu, falls keine Rolle zugewiesen werden soll
            if "None" not in self.all_roles:
                self.all_roles.insert(0, "None")

        except Exception as e:
            messagebox.showerror("Fehler beim Laden",
                                 f"Fenster-Konfiguration konnte nicht geladen werden: {e}",
                                 parent=self)
            self.config_data = {}
            self.all_roles = ["None", "Mitarbeiter", "Guest"]  # Fallback

    def _create_widgets(self):
        # --- Header ---
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=10, pady=10)
        ttk.Label(header_frame, text="Fenster-Konfiguration", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(header_frame,
                  text="Benennen Sie Anzeigenamen um und legen Sie Registrierungs-Optionen fest.",
                  wraplength=600,
                  justify="left").pack(anchor="w", pady=(5, 0))

        # --- Treeview Header ---
        header_controls = ttk.Frame(self)
        header_controls.pack(fill="x", padx=10, pady=(10, 0))

        ttk.Label(header_controls, text="Interner DB-Name", font=("Segoe UI", 10, "bold")).grid(row=0, column=0,
                                                                                                sticky="w", padx=5)
        ttk.Label(header_controls, text="Anzeigename (Editierbar)", font=("Segoe UI", 10, "bold")).grid(row=0, column=1,
                                                                                                        sticky="w",
                                                                                                        padx=5)
        ttk.Label(header_controls, text="Registrierung erlauben?", font=("Segoe UI", 10, "bold")).grid(row=0, column=2,
                                                                                                       sticky="w",
                                                                                                       padx=5)
        ttk.Label(header_controls, text="Standard-Rolle", font=("Segoe UI", 10, "bold")).grid(row=0, column=3,
                                                                                              sticky="w", padx=5)

        header_controls.columnconfigure(1, weight=1)  # Anzeigename soll sich strecken

        # --- Content Frame (für die dynamischen Einträge) ---
        self.content_frame = ttk.Frame(self, padding=(15, 10))
        self.content_frame.pack(fill="both", expand=True)
        self.content_frame.columnconfigure(1, weight=1)  # Spalte 1 (Anzeigename)

        # --- Footer ---
        footer_frame = ttk.Frame(self)
        footer_frame.pack(fill="x", padx=10, pady=10)

        self.save_button = ttk.Button(footer_frame, text="Speichern", command=self._on_save)
        self.save_button.pack(side="right")

        self.reload_button = ttk.Button(footer_frame, text="Änderungen verwarnen", command=self._populate_ui)
        self.reload_button.pack(side="right", padx=10)

    def _populate_ui(self):
        """(Neu) Füllt den content_frame mit den geladenen Daten."""
        # Lösche alte Widgets, falls vorhanden
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.widget_map.clear()

        if not self.config_data:
            ttk.Label(self.content_frame, text="Fehler: Keine Konfiguration geladen.", foreground="red").grid(row=0,
                                                                                                              column=0)
            return

        row = 0
        for db_key, settings in self.config_data.items():
            # 1. DB-Name (Nicht editierbar)
            ttk.Label(self.content_frame, text=db_key, font=("Segoe UI", 10, "italic"), foreground="#555").grid(row=row,
                                                                                                                column=0,
                                                                                                                sticky="w",
                                                                                                                padx=5,
                                                                                                                pady=10)

            # 2. Anzeigename (Editierbar)
            display_name_var = tk.StringVar(value=settings.get("display_name", ""))
            entry_display_name = ttk.Entry(self.content_frame, textvariable=display_name_var)
            entry_display_name.grid(row=row, column=1, sticky="ew", padx=5, pady=10)

            # 3. Registrierung erlauben (Checkbox)
            allow_reg_var = tk.BooleanVar(value=settings.get("allow_registration", False))
            check_allow_reg = ttk.Checkbutton(self.content_frame, variable=allow_reg_var)
            check_allow_reg.grid(row=row, column=2, sticky="w", padx=20, pady=10)

            # 4. Standard-Rolle (Combobox)
            role_var = tk.StringVar(value=settings.get("default_role", "None"))
            combo_role = ttk.Combobox(self.content_frame, textvariable=role_var, values=self.all_roles,
                                      state='readonly', width=15)
            combo_role.grid(row=row, column=3, sticky="w", padx=5, pady=10)

            # Speichere die Widgets, um sie später auszulesen
            self.widget_map[db_key] = {
                "display_name": display_name_var,
                "allow_registration": allow_reg_var,
                "default_role": role_var
            }
            row += 1

    def _on_save(self):
        """Liest die Daten aus dem UI, erstellt die neue Konfiguration und speichert sie."""

        new_config_data = {}
        try:
            for db_key, widgets in self.widget_map.items():
                display_name = widgets["display_name"].get()
                allow_reg = widgets["allow_registration"].get()
                role = widgets["default_role"].get()

                if not display_name:
                    messagebox.showerror("Fehler", f"Der Anzeigename für '{db_key}' darf nicht leer sein.", parent=self)
                    return

                # Wenn Rolle "None" ist, speichere None (null) statt des Strings
                default_role_val = None if role == "None" else role

                new_config_data[db_key] = {
                    "display_name": display_name,
                    "allow_registration": allow_reg,
                    "default_role": default_role_val
                }

            # Speichere die neue Konfiguration in der DB (via Manager)
            if save_window_config(new_config_data):
                messagebox.showinfo("Gespeichert",
                                    "Die Fenster-Konfiguration wurde gespeichert.\n\n"
                                    "HINWEIS: Änderungen an Anzeigenamen werden in der Rollen-Verwaltung "
                                    "und im Registrierungsfenster erst nach einem Neustart der Anwendung sichtbar.",
                                    parent=self)
            else:
                messagebox.showerror("Fehler", "Die Konfiguration konnte nicht in der Datenbank gespeichert werden.",
                                     parent=self)

        except Exception as e:
            messagebox.showerror("Fehler beim Speichern", f"Ein unerwarteter Fehler ist aufgetreten: {e}", parent=self)