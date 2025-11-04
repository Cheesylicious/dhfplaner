# gui/tabs/tab_components/shift_plan_ui_setup.py
import tkinter as tk
from tkinter import ttk


class ShiftPlanUISetup:
    """
    Diese Klasse ist ausschließlich für die Erstellung der
    Benutzeroberfläche (Widgets) des ShiftPlanTabs verantwortlich.
    Sie hält Referenzen auf die erstellten Widgets, damit der
    ShiftPlanTab (als Controller) darauf zugreifen kann.
    """

    def __init__(self, master_tab, app):
        """
        Initialisiert die UI-Klasse.
        :param master_tab: Die Instanz von ShiftPlanTab (das Haupt-Frame).
        :param app: Die Haupt-Applikationsinstanz (MainAdminWindow).
        """
        self.master_tab = master_tab
        self.app = app

        # Referenzen auf wichtige Widgets, die von außen benötigt werden
        self.month_label_var = tk.StringVar()
        self.month_label = None
        self.lock_status_label = None
        self.canvas = None
        self.inner_frame = None
        self.plan_grid_frame = None
        self.lock_button = None
        self.understaffing_result_frame = None

        # Widgets für den Lade-Status
        self.progress_frame = None
        self.progress_bar = None
        self.status_label = None

    def setup_ui(self, callbacks):
        """
        Erstellt die gesamte Benutzeroberfläche im master_tab Frame.

        :param callbacks: Eine Instanz von ShiftPlanEvents, die
                          alle command- und bind-Ziele enthält.
        """
        main_view_container = ttk.Frame(self.master_tab, padding="10")
        main_view_container.pack(fill="both", expand=True)

        nav_frame = ttk.Frame(main_view_container)
        nav_frame.pack(fill="x", pady=(0, 10))

        left_nav_frame = ttk.Frame(nav_frame)
        left_nav_frame.pack(side="left")

        # --- Styles (unverändert) ---
        style = ttk.Style(self.master_tab)
        style.configure("Delete.TButton", background="red", foreground="white", font=('Segoe UI', 9, 'bold'))
        style.map("Delete.TButton", background=[('active', '#CC0000')])
        style.configure("Generate.TButton", background="green", foreground="white", font=('Segoe UI', 9, 'bold'))
        style.map("Generate.TButton", background=[('active', '#006400')])
        style.configure("SettingsWarn.TButton", background="gold", foreground="black", font=('Segoe UI', 9, 'bold'))
        style.map("SettingsWarn.TButton", background=[('active', 'goldenrod')])
        style.configure("UnlockAll.TButton", background="darkorange", foreground="white", font=('Segoe UI', 9, 'bold'))
        style.map("UnlockAll.TButton", background=[('active', '#E67E00')])

        # --- Linke Navigations-Buttons ---
        # (Regel 4: Commands zeigen auf die callback-Instanz)
        ttk.Button(left_nav_frame, text="< Voriger Monat", command=callbacks.show_previous_month).pack(side="left")
        ttk.Button(left_nav_frame, text="📄 Drucken", command=callbacks.print_shift_plan).pack(side="left", padx=(20, 5))
        ttk.Button(left_nav_frame, text="Schichtplan Löschen !!!", command=callbacks._on_delete_month,
                   style="Delete.TButton").pack(side="left", padx=5)
        ttk.Separator(left_nav_frame, orient='vertical').pack(side='left', fill='y', padx=(10, 5))
        ttk.Button(left_nav_frame, text="Schichtplan generieren", command=callbacks._on_generate_plan,
                   style="Generate.TButton").pack(side="left", padx=5)
        ttk.Button(left_nav_frame, text="Planungsassistent-Einstellungen", command=callbacks._open_generator_settings,
                   style="SettingsWarn.TButton").pack(side="left", padx=5)
        ttk.Button(left_nav_frame, text="Alle Sicherungen aufheben", command=callbacks._on_unlock_all_shifts,
                   style="UnlockAll.TButton").pack(side="left", padx=5)

        # --- Mittlere Monatsanzeige ---
        month_label_frame = ttk.Frame(nav_frame)
        month_label_frame.pack(side="left", expand=True, fill="x")

        self.month_label = ttk.Label(month_label_frame, textvariable=self.month_label_var,
                                     font=("Segoe UI", 14, "bold"),
                                     anchor="center", cursor="hand2")
        self.month_label.pack()
        # (Regel 4: Bind zeigt auf callback-Instanz)
        self.month_label.bind("<Button-1>", callbacks._on_month_label_click)

        self.lock_status_label = ttk.Label(month_label_frame, text="", font=("Segoe UI", 10, "italic"),
                                           anchor="center")
        self.lock_status_label.pack()

        # --- Rechter Navigations-Button ---
        ttk.Button(nav_frame, text="Nächster Monat >", command=callbacks.show_next_month).pack(side="right")

        # --- Haupt-Grid-Container (mit Scrollbars) ---
        grid_container_frame = ttk.Frame(main_view_container)
        grid_container_frame.pack(fill="both", expand=True)

        vsb = ttk.Scrollbar(grid_container_frame, orient="vertical")
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(grid_container_frame, orient="horizontal")
        hsb.pack(side="bottom", fill="x")

        self.canvas = tk.Canvas(grid_container_frame, yscrollcommand=vsb.set, xscrollcommand=hsb.set,
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self.canvas.yview)
        hsb.config(command=self.canvas.xview)

        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw", tags="inner_frame")

        # Das Frame, in das der Renderer das Gitter zeichnet
        self.plan_grid_frame = ttk.Frame(self.inner_frame)
        self.plan_grid_frame.pack(fill="both", expand=True)

        # --- Canvas Scroll-Logik ---
        def _configure_inner_frame(event):
            if self.inner_frame.winfo_exists() and self.canvas.winfo_exists():
                self.canvas.itemconfig('inner_frame', width=event.width)

        def _configure_scrollregion(event):
            if self.inner_frame.winfo_exists() and self.canvas.winfo_exists():
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.canvas.bind('<Configure>', _configure_inner_frame)
        self.inner_frame.bind('<Configure>', _configure_scrollregion)

        # --- Tastatur-Shortcuts (Regel 4: Bindings hier, Logik im Callback-Handler) ---
        self.canvas.bind("<Key>", callbacks._on_key_press)
        # Fokus setzen, damit das Canvas Tasten-Events empfängt
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())

        # --- Footer-Elemente ---
        footer_frame = ttk.Frame(main_view_container)
        footer_frame.pack(fill="x", pady=(10, 0))

        check_frame = ttk.Frame(footer_frame)
        check_frame.pack(side="left")
        ttk.Button(check_frame, text="Schichtplan Prüfen", command=callbacks.check_understaffing).pack(side="left",
                                                                                                       padx=5)
        ttk.Button(check_frame, text="Leeren", command=callbacks.clear_understaffing_results).pack(side="left", padx=5)

        self.lock_button = ttk.Button(footer_frame, text="", command=callbacks.toggle_month_lock)
        self.lock_button.pack(side="right", padx=5)

        # Frame für Unterbesetzungs-Ergebnisse (wird bei Bedarf eingeblendet)
        self.understaffing_result_frame = ttk.Frame(main_view_container, padding="10")

    def _create_progress_widgets(self):
        """
        Erstellt die Lade-Anzeige. Diese Methode wird vom ShiftPlanTab
        (dem Controller) aufgerufen, wenn Daten geladen werden.
        """
        if self.progress_frame and self.progress_frame.winfo_exists():
            self.progress_frame.destroy()

        # WICHTIG: Das Progress-Frame wird im plan_grid_frame erstellt,
        # da es das Gitter während des Ladens ersetzt.
        self.progress_frame = ttk.Frame(self.plan_grid_frame)

        self.status_label = ttk.Label(self.progress_frame, text="", font=("Segoe UI", 12))
        self.status_label.pack(pady=(20, 5))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=300, mode='determinate')
        self.progress_bar.pack(pady=5)