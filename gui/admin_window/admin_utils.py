# gui/admin_window/admin_utils.py
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, date
import csv
import os

# Importiert die korrekte DB-Funktion (die wir in Schritt 2 erstellt haben)
from database.db_roles import get_all_roles_details


class AdminUtils:
    def __init__(self, main_admin_window):
        """Initialisiert die Admin-Hilfsfunktionen."""
        self.maw = main_admin_window  # Referenz zum MainAdminWindow

    def get_contrast_color(self, hex_color):
        """Berechnet die Kontrastfarbe (schwarz/weiß) für eine gegebene Hex-Farbe."""
        if not hex_color:
            return "#000000"  # Standard auf Schwarz
        try:
            # Entferne das '#'-Zeichen, falls vorhanden
            if hex_color.startswith('#'):
                hex_color = hex_color[1:]

            # Stelle sicher, dass der Hex-Code 6-stellig ist (z.B. bei FFF)
            if len(hex_color) == 3:
                hex_color = hex_color * 2

            if len(hex_color) != 6:
                raise ValueError("Ungültiger Hex-Code")

            # Konvertiere Hex zu RGB
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)

            # Berechne die Helligkeit (YIQ-Formel)
            brightness = ((r * 299) + (g * 587) + (b * 114)) / 1000

            # Wähle Schwarz oder Weiß basierend auf der Helligkeit
            return "#FFFFFF" if brightness < 128 else "#000000"

        except (ValueError, TypeError) as e:
            print(f"[FEHLER] get_contrast_color: Ungültiger Wert '{hex_color}'. Fehler: {e}")
            return "#000000"  # Fallback

    # --- NEU HINZUGEFÜGT (Diese Funktion hat den Fehler verursacht) ---
    def calculate_hover_color(self, hex_color):
        """
        Berechnet eine leicht abgedunkelte Hover-Farbe für UI-Elemente.
        (Behebt den AttributeError aus admin_notification_manager.py)
        """
        if not hex_color or not hex_color.startswith('#'):
            return "#E5E5E5"  # Standard-Hover-Grau

        try:
            hex_color = hex_color.lstrip('#')

            # Stelle 6-stellig sicher (falls 3-stellig übergeben)
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])

            if len(hex_color) != 6:
                return "#E5E5E5"

            # Zu RGB konvertieren
            rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

            # Farbe abdunkeln (z.B. um ~15%)
            # Wir verwenden max(0, ...), um nicht unter 0 zu fallen
            hover_rgb = tuple(max(0, int(c * 0.85)) for c in rgb)

            # Zurück zu HEX
            hover_hex = f"#{hover_rgb[0]:02x}{hover_rgb[1]:02x}{hover_rgb[2]:02x}"
            return hover_hex

        except Exception as e:
            print(f"[FEHLER] calculate_hover_color: {e} (Farbe: {hex_color})")
            return "#E5E5E5"  # Fallback

    # --- ENDE NEU HINZUGEFÜGT ---

    def get_allowed_roles(self):
        """
        Proxy-Methode: Ruft ALLE Rollen dynamisch aus der Datenbank ab
        und konvertiert sie in das vom UserEditWindow erwartete Format (LISTE von Namen).
        """
        try:
            # 1. Ruft die Liste ab: [{'id': 1, 'name': 'Admin'}, ...]
            roles_list = get_all_roles_details()

            # 2. Konvertiert in das Listen-Format, das die Combobox (UserEditWindow) erwartet:
            #    ['Admin', 'Test']
            role_names = [role['name'] for role in roles_list]

            if not role_names:
                print("[WARNUNG] get_allowed_roles: Keine Rollen von der DB empfangen.")
                # Fallback auf Standardrollen, falls DB-Abfrage fehlschlägt
                return ["Admin", "Mitarbeiter", "Gast"]

            return role_names

        except Exception as e:
            print(f"[FEHLER] get_allowed_roles: Konnte Rollen nicht laden: {e}")
            # Fallback bei schwerem Fehler
            return ["Admin", "Mitarbeiter", "Gast"]

    def export_shift_plan_to_csv(self):
        """
        Exportiert den aktuell angezeigten Schichtplan (Daten aus dem
        ShiftPlanTab-Datenmanager) als CSV-Datei.
        """
        print("[DEBUG] Exportiere CSV...")

        # 1. Greife auf den Schichtplan-Tab zu
        shift_plan_tab = self.maw.tab_manager.get_tab_instance("Schichtplan")
        if not shift_plan_tab:
            messagebox.showerror("Export fehlgeschlagen", "Der Schichtplan-Tab ist nicht geladen.", parent=self.maw)
            return

        # 2. Greife auf den Datenmanager des Tabs zu
        data_manager = shift_plan_tab.data_manager
        if not data_manager:
            messagebox.showerror("Export fehlgeschlagen", "Datenmanager des Schichtplans nicht gefunden.",
                                 parent=self.maw)
            return

        # 3. Daten aus dem Manager holen (die bereits geladen sind)
        plan_data = data_manager.plan_data
        users_in_plan = data_manager.users_in_plan

        if not plan_data or not users_in_plan:
            messagebox.showerror("Export fehlgeschlagen", "Keine Plandaten zum Exportieren vorhanden.", parent=self.maw)
            return

        # 4. Dateiname und Pfad festlegen
        current_date = self.maw.current_display_date
        filename = f"Schichtplan_{current_date.year}_{current_date.month:02d}.csv"

        # Standard-Speicherort (z.B. "Downloads" im Benutzerverzeichnis)
        try:
            # (Dieser Pfad funktioniert systemübergreifend)
            default_path = os.path.join(os.path.expanduser("~"), "Downloads")
            if not os.path.exists(default_path):
                default_path = os.path.expanduser("~")  # Fallback auf Home
        except Exception:
            default_path = "."  # Fallback auf aktuelles Verzeichnis

        filepath = os.path.join(default_path, filename)

        # 5. CSV schreiben (mit UTF-8-BOM für Excel-Kompatibilität)
        try:
            # Erstelle eine sortierte Liste der Tage für die Spaltenköpfe
            first_user_id = next(iter(users_in_plan))
            sorted_dates = sorted(plan_data.get(first_user_id, {}).keys())

            if not sorted_dates:
                messagebox.showerror("Export fehlgeschlagen", "Keine Datumseinträge gefunden.", parent=self.maw)
                return

            # Header-Zeile erstellen (Name, Vorname, Tag 1, Tag 2, ...)
            headers = ["Name", "Vorname"]
            headers.extend([d.strftime("%d.%m.%Y") for d in sorted_dates])

            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(headers)

                # Datenzeilen für jeden Benutzer schreiben
                for user in users_in_plan:
                    user_id = user['id']
                    row = [user['name'], user['vorname']]

                    user_plan = plan_data.get(user_id, {})

                    for d in sorted_dates:
                        day_data = user_plan.get(d)
                        if day_data:
                            # Kombiniere Schicht-Typ und (falls vorhanden) Aufgabe
                            cell_value = day_data.get('shift_type_name', 'N/A')
                            task = day_data.get('task')
                            if task:
                                cell_value += f" ({task})"
                            row.append(cell_value)
                        else:
                            row.append("")  # Leere Zelle

                    writer.writerow(row)

            messagebox.showinfo("Export erfolgreich",
                                f"Schichtplan wurde exportiert nach:\n{filepath}",
                                parent=self.maw)

        except (IOError, PermissionError) as e:
            messagebox.showerror("Export fehlgeschlagen",
                                 f"Speichern fehlgeschlagen. Ist die Datei vielleicht geöffnet?\n\nFehler: {e}",
                                 parent=self.maw)
        except Exception as e:
            messagebox.showerror("Export fehlgeschlagen",
                                 f"Ein unerwarteter Fehler ist aufgetreten:\n{e}",
                                 parent=self.maw)