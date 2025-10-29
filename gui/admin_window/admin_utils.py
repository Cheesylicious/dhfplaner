# gui/admin_window/admin_utils.py
import tkinter as tk
from tkinter import messagebox

from database.db_core import (
    ROLE_HIERARCHY,
    run_db_update_v1,
    run_db_update_is_approved,
    run_db_fix_approve_all_users,
    run_db_update_add_is_archived,
    run_db_update_add_archived_date
)


class AdminUtils:
    def __init__(self, admin_window):
        """
        Sammlung von Hilfsfunktionen und Alt-Funktionen für das Admin-Fenster.

        :param admin_window: Die Instanz von MainAdminWindow.
        """
        self.admin_window = admin_window
        self.user_data = admin_window.user_data

    def calculate_hover_color(self, base_color):
        """Dunkelt eine Hex-Farbe leicht ab für den Hover-Effekt."""
        try:
            if not base_color.startswith('#'):
                try:
                    rgb = self.admin_window.winfo_rgb(base_color)
                    r, g, b = [x // 256 for x in rgb]
                    hex_color = f"#{r:02x}{g:02x}{b:02x}"
                except tk.TclError:
                    return '#e0e0e0'
            else:
                hex_color = base_color

            if len(hex_color) not in [4, 7]: return '#e0e0e0'

            if len(hex_color) == 4:
                r, g, b = [int(c * 2, 16) for c in hex_color[1:]]
            else:
                r, g, b = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]

            factor = 0.85
            r = max(0, int(r * factor))
            g = max(0, int(g * factor))
            b = max(0, int(b * factor))

            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            return '#e0e0e0'

    def get_contrast_color(self, hex_color):
        """Berechnet Schwarz oder Weiß als gut lesbare Kontrastfarbe."""
        if not isinstance(hex_color, str): return 'black'
        if not hex_color.startswith('#'):
            try:
                rgb_16bit = self.admin_window.winfo_rgb(hex_color)
                r, g, b = [x // 256 for x in rgb_16bit]
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
            except tk.TclError:
                print(f"[WARNUNG] get_contrast_color: Unbekannte Farbe '{hex_color}', verwende Schwarz.")
                return 'black'

        if len(hex_color) not in [4, 7]:
            print(f"[WARNUNG] get_contrast_color: Ungültiges Hex-Format '{hex_color}', verwende Schwarz.")
            return 'black'

        try:
            if len(hex_color) == 4:
                r, g, b = [int(c * 2, 16) for c in hex_color[1:]]
            else:
                r, g, b = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
        except ValueError:
            print(f"[WARNUNG] get_contrast_color: Fehler bei Hex-Konvertierung für '{hex_color}', verwende Schwarz.")
            return 'black'

        luminance = (r * 299 + g * 587 + b * 114) / 1000
        threshold = 140
        contrast_color = 'black' if luminance >= threshold else 'white'
        return contrast_color

    def get_allowed_roles(self):
        """Gibt eine Liste der Rollen zurück, die der aktuelle Admin verwalten darf."""
        current_admin_role = self.user_data.get('role', 'Benutzer')
        admin_level = ROLE_HIERARCHY.get(current_admin_role, 0)

        allowed_roles = [role for role, level in ROLE_HIERARCHY.items() if level < admin_level]

        if current_admin_role == "Admin":
            if "Admin" not in allowed_roles:
                allowed_roles.append("Admin")
            allowed_roles = [r for r in allowed_roles if
                             ROLE_HIERARCHY.get(r, 99) < ROLE_HIERARCHY.get("SuperAdmin", 99)]
        elif current_admin_role == "SuperAdmin":
            allowed_roles = list(ROLE_HIERARCHY.keys())

        if "Benutzer" in allowed_roles:
            allowed_roles.remove("Benutzer")

        print(f"[DEBUG] Erlaubte Rollen für {current_admin_role} (Level {admin_level}): {allowed_roles}")
        return allowed_roles

    # --- Alte DB-Fix Methoden (für den Wartungstab) ---

    def _run_db_update_with_confirmation(self, message, db_function):
        """ Führt eine DB-Update-Funktion nach Bestätigung aus. """
        if messagebox.askyesno("Bestätigung erforderlich", message, parent=self.admin_window):
            try:
                success, result_message = db_function()
                if success:
                    messagebox.showinfo("Update erfolgreich", result_message, parent=self.admin_window)
                else:
                    messagebox.showerror("Update fehlgeschlagen", result_message, parent=self.admin_window)
            except Exception as e:
                print(f"FEHLER bei DB Update ({db_function.__name__}): {e}")
                messagebox.showerror("Schwerer Datenbankfehler", f"Ein unerwarteter Fehler ist aufgetreten:\n{e}",
                                     parent=self.admin_window)

    def apply_archived_date_fix(self):
        msg = "Dies fügt die Spalte 'archived_date' zur Benutzer-Tabelle hinzu, falls sie fehlt.\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_add_archived_date)

    def apply_is_archived_fix(self):
        msg = "Dies fügt die Spalte 'is_archived' zur Benutzer-Tabelle hinzu, falls sie fehlt.\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_add_is_archived)

    def apply_all_users_approval_fix(self):
        if messagebox.askyesno("ACHTUNG: Kritische Aktion",
                               "Sind Sie ABSOLUT SICHER, dass Sie ALLE bestehenden Benutzerkonten auf 'freigeschaltet' setzen möchten?\nDies kann nicht einfach rückgängig gemacht werden!",
                               icon='warning', parent=self.admin_window):
            self._run_db_update_with_confirmation("Wirklich ALLE Benutzer freischalten?", run_db_fix_approve_all_users)

    def apply_is_approved_fix(self):
        msg = "Dies fügt die Spalte 'is_approved' zur Benutzer-Tabelle hinzu, um die manuelle Freischaltung zu ermöglichen.\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_is_approved)

    def apply_database_fix(self):
        msg = "Dies führt notwendige Updates an der Datenbank für die Chat-Funktionalität durch (fügt Spalten/Tabellen hinzu, falls benötigt).\nFortfahren?"
        self._run_db_update_with_confirmation(msg, run_db_update_v1)