import tkinter as tk
from tkinter import ttk


class MainZuteilungWindow(tk.Tk):
    """
    Platzhalter für das Hauptfenster 'Zuteilung'.
    Diese Klasse dient als Ziel für Rollen, die eine spezialisierte
    Ansicht (z.B. nur Zuteilung von Aufgaben/Hunden) benötigen.

    ERBT VON tk.Tk, um die gleiche Schnittstelle wie MainAdminWindow/MainUserWindow
    bereitzustellen (Regel 1).
    """

    def __init__(self, master, user_data, app):
        """
        Initialisiert das Fenster.

        Args:
            master (Application): Die Bootloader-App-Instanz.
            user_data (dict): Die Daten des angemeldeten Benutzers.
            app (Application): Die Bootloader-App-Instanz (redundant, aber Teil der Signatur).
        """
        super().__init__()
        self.master = master  # Die Bootloader-Instanz
        self.user_data = user_data
        self.app = app  # Die Bootloader-Instanz (für Logout/Close)

        print(f"[Boot Loader] Lade Zuteilungs-Fenster für {self.user_data.get('username')}...")

        self.title(f"DHF Planer - Zuteilung ({self.user_data.get('username')})")
        self.geometry("1024x768")
        self.minsize(800, 600)

        # --- Standard-Protokolle (Regel 1) ---
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

        # --- Menüleiste (Basis) ---
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)

        # Datei-Menü
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Datei", menu=self.file_menu)
        self.file_menu.add_command(label="Abmelden", command=self.on_logout)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Beenden", command=self.on_app_close)

        # --- Platzhalter-Inhalt ---
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(expand=True, fill="both")

        title_label = ttk.Label(
            main_frame,
            text="Zuteilungs-Fenster",
            font=("Segoe UI", 24, "bold")
        )
        title_label.pack(pady=20)

        desc_label = ttk.Label(
            main_frame,
            text="Ihr Account wurde zwar freigeschaltet aber leider noch nicht von einen Admin zugewiesen.",
            font=("Segoe UI", 12),
            justify="center"
        )
        desc_label.pack(pady=10)

        # Wichtig: Das Fenster erst nach dem Setup anzeigen
        self.deiconify()

    def on_logout(self):
        """Leitet den Logout-Prozess im Bootloader ein."""
        print("[ZuteilungWindow] Logout eingeleitet.")
        if self.app and hasattr(self.app, 'on_logout'):
            self.app.on_logout()

    def on_app_close(self):
        """Leitet das Schließen der App im Bootloader ein."""
        print("[ZuteilungWindow] Schließen eingeleitet.")
        if self.app and hasattr(self.app, 'on_app_close'):
            self.app.on_app_close()