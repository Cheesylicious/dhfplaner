# gui/tabs/participation_tab.py
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta, date

# Hier ist die Korrektur: von db_manager auf db_users geändert
from database.db_users import get_all_user_participation


class ParticipationTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # Spalten-Definitionen
        columns = ("name", "last_ausbildung", "days_since_ausbildung", "next_ausbildung",
                   "last_schiessen", "days_since_schiessen", "next_schiessen")

        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings")

        # Spaltenüberschriften
        self.tree.heading("name", text="Mitarbeiter")
        self.tree.heading("last_ausbildung", text="Letzte Q-Ausbildung")
        self.tree.heading("days_since_ausbildung", text="Tage her")
        self.tree.heading("next_ausbildung", text="Nächste Fälligkeit")
        self.tree.heading("last_schiessen", text="Letztes Schießen")
        self.tree.heading("days_since_schiessen", text="Tage her")
        self.tree.heading("next_schiessen", text="Nächste Fälligkeit")

        # Spalten-Konfiguration
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("last_ausbildung", anchor="center")
        self.tree.column("days_since_ausbildung", width=80, anchor="center")
        self.tree.column("next_ausbildung", anchor="center")
        self.tree.column("last_schiessen", anchor="center")
        self.tree.column("days_since_schiessen", width=80, anchor="center")
        self.tree.column("next_schiessen", anchor="center")

        # Scrollbar
        vsb = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Tags für die farbliche Hervorhebung
        self.tree.tag_configure('warning', background='orange')
        self.tree.tag_configure('danger', background='tomato')

    def get_end_of_quarter(self, a_date):
        """Ermittelt das Enddatum des Quartals für ein gegebenes Datum."""
        quarter = (a_date.month - 1) // 3 + 1
        if quarter == 1:
            return date(a_date.year, 3, 31)
        elif quarter == 2:
            return date(a_date.year, 6, 30)
        elif quarter == 3:
            return date(a_date.year, 9, 30)
        else:  # quarter == 4
            return date(a_date.year, 12, 31)

    def refresh_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        user_participations = get_all_user_participation()
        today = datetime.now().date()

        for user in user_participations:
            name = f"{user['vorname']} {user['name']}"

            # --- Quartals-Ausbildung ---
            last_ausbildung_str = "Nie"
            days_since_ausbildung_str = "-"
            next_ausbildung_str = "Sofort fällig"
            ausbildung_tags = ('danger',)

            if user['last_ausbildung']:
                try:
                    last_ausbildung_date = datetime.strptime(user['last_ausbildung'], '%Y-%m-%d').date()
                    last_ausbildung_str = last_ausbildung_date.strftime('%d.%m.%Y')

                    days_since = (today - last_ausbildung_date).days
                    days_since_ausbildung_str = str(days_since)

                    # Fälligkeit ist das Ende des nächsten Quartals
                    if last_ausbildung_date.month in [1, 2, 3]:
                        next_quarter_end = date(last_ausbildung_date.year, 6, 30)
                    elif last_ausbildung_date.month in [4, 5, 6]:
                        next_quarter_end = date(last_ausbildung_date.year, 9, 30)
                    elif last_ausbildung_date.month in [7, 8, 9]:
                        next_quarter_end = date(last_ausbildung_date.year, 12, 31)
                    else:
                        next_quarter_end = date(last_ausbildung_date.year + 1, 3, 31)

                    next_ausbildung_str = f"bis {next_quarter_end.strftime('%d.%m.%Y')}"

                    # Farbliche Markierung
                    if today > next_quarter_end:
                        ausbildung_tags = ('danger',)
                    elif today > (next_quarter_end - timedelta(days=30)):  # 30 Tage vor Fälligkeit
                        ausbildung_tags = ('warning',)
                    else:
                        ausbildung_tags = ()

                except (ValueError, TypeError):
                    last_ausbildung_str = "Ungültiges Datum"
                    ausbildung_tags = ('danger',)

            # --- Schießen ---
            last_schiessen_str = "Nie"
            days_since_schiessen_str = "-"
            next_schiessen_str = "Sofort fällig"
            schiessen_tags = ('danger',)

            if user['last_schiessen']:
                try:
                    last_schiessen_date = datetime.strptime(user['last_schiessen'], '%Y-%m-%d').date()
                    last_schiessen_str = last_schiessen_date.strftime('%d.%m.%Y')

                    days_since = (today - last_schiessen_date).days
                    days_since_schiessen_str = str(days_since)

                    # Fälligkeit ist 90 Tage nach dem letzten Termin
                    next_schiessen_date = last_schiessen_date + timedelta(days=90)
                    next_schiessen_str = f"bis {next_schiessen_date.strftime('%d.%m.%Y')}"

                    # Farbliche Markierung
                    if today > next_schiessen_date:
                        schiessen_tags = ('danger',)
                    elif today > (next_schiessen_date - timedelta(days=14)):  # 14 Tage vor Fälligkeit
                        schiessen_tags = ('warning',)
                    else:
                        schiessen_tags = ()

                except (ValueError, TypeError):
                    last_schiessen_str = "Ungültiges Datum"
                    schiessen_tags = ('danger',)

            # In die Tabelle einfügen
            values = (name, last_ausbildung_str, days_since_ausbildung_str, next_ausbildung_str,
                      last_schiessen_str, days_since_schiessen_str, next_schiessen_str)

            # Tags für die Zeilenfärbung kombinieren
            combined_tags = set(ausbildung_tags) | set(schiessen_tags)

            self.tree.insert("", tk.END, values=values, tags=tuple(combined_tags))