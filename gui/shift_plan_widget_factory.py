# gui/shift_plan_widget_factory.py
import tkinter as tk


class ShiftPlanWidgetFactory:
    """
    Verantwortlich für die reine Erstellung und Platzierung (Grid/Pack)
    der Tkinter-Widgets für den Dienstplan.
    Diese Klasse enthält keine Business-Logik (Farben, Text, Aktionen).
    """

    def __init__(self, parent_frame):
        self.parent_frame = parent_frame

    def create_header_label(self, text, font_spec, bg, fg, row, col, rowspan=1, colspan=1, sticky="nsew", bd=1,
                            relief="solid", padx=5, pady=5):
        """Erstellt ein einfaches Label für die Kopfzeile."""
        label = tk.Label(
            self.parent_frame,
            text=text,
            font=font_spec,
            bg=bg,
            fg=fg,
            padx=padx,
            pady=pady,
            bd=bd,
            relief=relief
        )
        label.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, sticky=sticky)
        return label

    def create_user_info_label(self, text, font_spec, row, col, anchor="w", bg="white", fg="black"):
        """Erstellt ein Label für die Benutzer-Spalten (Name, Hund, Std)."""
        label = tk.Label(
            self.parent_frame,
            text=text,
            font=font_spec,
            bg=bg,
            fg=fg,
            padx=5,
            pady=5,
            bd=1,
            relief="solid",
            anchor=anchor
        )
        label.grid(row=row, column=col, sticky="nsew")
        return label

    def create_grid_cell(self, text, font_spec, row, col):
        """
        Erstellt die Frame/Label-Struktur für eine Standard-Grid-Zelle ("Ü" oder Tag).
        Gibt ein Dictionary {'frame': Frame, 'label': Label} zurück.
        """
        frame = tk.Frame(self.parent_frame, bd=1, relief="solid", bg="black")  # Standard-Rahmenfarbe
        frame.grid(row=row, column=col, sticky="nsew")

        label = tk.Label(frame, text=text, font=font_spec, anchor="center")
        label.pack(expand=True, fill="both", padx=1, pady=1)

        return {'frame': frame, 'label': label}

    def create_summary_label(self, text, font_spec, row, col, anchor, bg, fg="black", bd=1, relief="solid"):
        """Erstellt ein Label für die Zusammenfassungszeile."""
        label = tk.Label(
            self.parent_frame,
            text=text,
            font=font_spec,
            bg=bg,
            fg=fg,
            padx=5,
            pady=5,
            bd=bd,
            relief=relief,
            anchor=anchor
        )
        label.grid(row=row, column=col, sticky="nsew")
        return label

    def create_spacer_label(self, row, col, colspan, bg="#E0E0E0"):
        """Erstellt ein leeres Label als Trenner."""
        label = tk.Label(self.parent_frame, text="", bg=bg, bd=0)
        label.grid(row=row, column=col, columnspan=colspan, sticky="nsew", pady=1)
        return label