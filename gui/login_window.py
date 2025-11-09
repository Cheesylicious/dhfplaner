import tkinter as tk
from tkinter import ttk, messagebox
from database.db_users import authenticate_user, get_user_count, log_user_login
# --- NEU (Schritt 4): Import der Rollen-DB-Funktion ---
from database.db_roles import get_main_window_for_role
# --- ENDE NEU ---
from .registration_window import RegistrationWindow
from .password_reset_window import PasswordResetWindow
import webbrowser  # Beibehalten

# --- NEUE IMPORTE ---
import threading
from database import db_core  # Um den Pool-Status zu prüfen

# --- NEU: ANIMATIONS-IMPORTE (Regel 2) ---
import random
import math


# --- ENDE NEU ---


class LoginWindow(tk.Toplevel):
    def __init__(self, master, app, prewarm_thread, preload_thread):
        """
        Nimmt jetzt den 'prewarm_thread' UND den 'preload_thread' entgegen,
        um den Verbindungsaufbau UND das Daten-Caching zu überwachen.

        WICHTIG: Dieses Fenster wird versteckt initialisiert ('self.withdraw()')
        und von boot_loader.py (via 'show_login_window') angezeigt.

        (Regel 2) Integriert die Konstellations-Animation als Hintergrund.
        """
        print("[DEBUG] LoginWindow.__init__: Wird initialisiert.")
        super().__init__(master)
        self.app = app

        # --- INNOVATION: Pre-Loading-Threads speichern ---
        self.prewarm_thread = prewarm_thread
        self.preload_thread = preload_thread
        # ------------------------------------------------

        # --- NEU: Status-Flags ---
        self.db_ready = False
        self.data_ready = False  # NEUES FLAG für Daten-Thread
        self.login_button_enabled = False
        # -------------------------

        # --- NEU: Animations-Steuerung (Regel 2) ---
        self.running = False  # Startet als 'False', wird von on_splash_screen_finished aktiviert
        self.nodes = []
        self.num_nodes = 40  # Etwas mehr Knoten für den großen Bildschirm
        self.max_speed = 0.4
        self.connection_distance = 180

        # --- Farbpalette (MODIFIZIERT: Harmonisiert mit SplashScreen) ---
        self.bg_color = "#1a1a1a"  # <--- GEÄNDERT (von #2c3e50)
        self.node_color = "#3498db"  # Akzentfarbe (Login-Button)
        self.line_color = "#ecf0f1"  # Helles Grau (Linien)
        # --------------------------------------------

        self.local_version = "0.0.0"

        # --- MODIFIZIERT (M): 'self.withdraw()' bleibt, 'deiconify()' wird entfernt ---
        self.withdraw()  # WICHTIG: Fenster versteckt starten
        self.title("DHF-Planer - Login")
        self.configure(bg=self.bg_color)  # Hintergrund des Toplevel-Fensters

        style = ttk.Style(self)
        style.theme_use('clam')

        # --- MODIFIZIERT: Alle Styles auf self.bg_color (#1a1a1a) umgestellt ---
        style.configure('TFrame', background=self.bg_color)
        style.configure('TLabel', background=self.bg_color, foreground='white', font=('Segoe UI', 10))
        style.configure('TButton', background='#3498db', foreground='white', font=('Segoe UI', 10, 'bold'),
                        borderwidth=0)
        style.map('TButton', background=[('active', '#2980b9')])

        # Style für Ladebalken (Post-Login)
        style.configure('Loading.TLabel', background=self.bg_color, foreground='white', font=('Segoe UI', 12))
        style.configure('Loading.Horizontal.TProgressbar', background='#3498db')

        # --- NEU: Style für Pre-Login-Ladebalken ---
        style.configure('PreLoading.TLabel', background=self.bg_color, foreground='#bdc3c7',
                        font=('Segoe UI', 9, 'italic'))
        # Stil für den Balken selbst
        style.configure('PreLoading.Horizontal.TProgressbar',
                        troughcolor='#34495e',  # Farbe der Leiste
                        background='#3498db')  # Farbe des Balkens

        # Style für erfolgreiche Labels
        style.configure('Success.PreLoading.TLabel', background=self.bg_color, foreground='#2ecc71',
                        font=('Segoe UI', 9, 'italic'))
        # Style für fehlerhafte Labels
        style.configure('Error.PreLoading.TLabel', background=self.bg_color, foreground='red',
                        font=('Segoe UI', 9, 'italic'))
        # --- ENDE MODIFIKATION ---

        self.protocol("WM_DELETE_WINDOW", self.app.on_app_close)
        self.create_widgets(style)

        # --- MODIFIZIERT (R): Sichtbarkeits-Logik entfernt ---
        # (Wird von boot_loader gesteuert)
        # --- ENDE MODIFIZIERT ---

        # --- INNOVATION: Starte den Checker für die Pre-Loading-Threads ---
        if self.prewarm_thread and self.preload_thread:
            # Startet den neuen Checker
            self.after(100, self._check_startup_threads)
        else:
            # Fallback
            print("[WARNUNG] Nicht alle Pre-Loading-Threads an LoginWindow übergeben.")
            self.db_status_label.config(text="Fehler: Pre-Loading nicht gestartet.", style='Error.PreLoading.TLabel')
            self.login_button.config(state="normal")
            self.login_button_enabled = True
        # -------------------------------------------------------------

        print("[DEBUG] LoginWindow.__init__: Initialisierung abgeschlossen (Fenster bleibt versteckt).")

    def create_widgets(self, style):
        """
        (Regel 2) Erstellt die Canvas als unterste Ebene für die Animation
        und platziert den 'wrapper_frame' (mit dem Login-Formular)
        zentriert darauf.
        """

        # --- MODIFIZIERT: Canvas ist der Hauptcontainer ---
        self.canvas = tk.Canvas(self, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # 'wrapper_frame' ist der Container für ALLE UI-Elemente (Formular, Ladebalken)
        # WICHTIG: Der Master ist jetzt self.canvas
        self.wrapper_frame = ttk.Frame(self.canvas, style='TFrame')
        # Wir verwenden create_window statt place/pack, damit es über den
        # Canvas-Items (Nodes/Linien) schwebt.
        # Die Position wird in on_window_resize() gesetzt.
        self.canvas.create_window(0, 0, window=self.wrapper_frame, anchor="center", tags="ui_wrapper")
        # --------------------------------------------------

        # --- Der Inhalt von wrapper_frame bleibt (fast) unverändert ---
        # (Master ist jetzt wrapper_frame)

        self.main_frame = ttk.Frame(self.wrapper_frame, padding="40", style='TFrame')
        self.main_frame.pack()

        ttk.Label(self.main_frame, text=f"DHF Planer", font=("Segoe UI", 28, "bold")).pack(
            pady=(0, 40))

        self.form_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.form_frame.pack(fill="x", pady=5)
        self.form_frame.columnconfigure(1, weight=1)
        ttk.Label(self.form_frame, text="Vorname:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.vorname_entry = ttk.Entry(self.form_frame, font=('Segoe UI', 12), width=30)
        self.vorname_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.vorname_entry.focus_set()
        ttk.Label(self.form_frame, text="Nachname:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.name_entry = ttk.Entry(self.form_frame, font=('Segoe UI', 12))
        self.name_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(self.form_frame, text="Passwort:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.password_entry = ttk.Entry(self.form_frame, show="*", font=('Segoe UI', 12))
        self.password_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        self.password_entry.bind("<Return>", self.attempt_login)
        self.vorname_entry.bind("<Return>", lambda e: self.name_entry.focus())
        self.name_entry.bind("<Return>", lambda e: self.password_entry.focus())

        self.login_button = ttk.Button(self.main_frame, text="Anmelden", command=self.attempt_login, style='TButton',
                                       state="disabled")
        self.login_button.pack(pady=20, fill="x", ipady=8)

        self.button_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.button_frame.pack(fill='x')

        self.register_button = ttk.Button(self.button_frame, text="Registrieren", command=self.open_registration)
        self.register_button.pack(side='left', expand=True, fill='x', padx=(0, 5), ipady=4)

        self.reset_button = ttk.Button(self.button_frame, text="Passwort vergessen", command=self.open_password_reset)
        self.reset_button.pack(side='right', expand=True, fill='x', padx=(5, 0), ipady=4)

        # --- INNOVATION: Pre-Login Lade-Widgets (AUFGETEILT) ---
        # (Master ist wrapper_frame)
        self.pre_login_loading_frame = ttk.Frame(self.wrapper_frame, style='TFrame')
        self.pre_login_loading_frame.pack(fill='x', padx=40, pady=(10, 0))

        # --- Balken 1: Datenbank-Verbindung ---
        self.db_status_label = ttk.Label(self.pre_login_loading_frame, text="Verbinde mit Datenbank...",
                                         style='PreLoading.TLabel', anchor="center")
        self.db_status_label.pack(fill='x')
        self.db_progressbar = ttk.Progressbar(self.pre_login_loading_frame, mode='determinate',
                                              style='PreLoading.Horizontal.TProgressbar',
                                              maximum=100, value=0)
        self.db_progressbar.pack(fill='x', pady=(5, 10))  # Mehr Abstand nach unten

        # --- Balken 2: Anwendungsdaten ---
        self.data_status_label = ttk.Label(self.pre_login_loading_frame, text="Lade Anwendungsdaten...",
                                           style='PreLoading.TLabel', anchor="center")
        self.data_status_label.pack(fill='x')
        self.data_progressbar = ttk.Progressbar(self.pre_login_loading_frame, mode='determinate',
                                                style='PreLoading.Horizontal.TProgressbar',
                                                maximum=100, value=0)
        self.data_progressbar.pack(fill='x', pady=(5, 0))
        # -------------------------------------------------------------

        # --- Post-Login Lade-Widgets (im wrapper_frame) ---
        self.loading_label = ttk.Label(self.wrapper_frame, text="Lade Hauptfenster, bitte warten...",
                                       style='Loading.TLabel', anchor="center")
        self.progress_bar = ttk.Progressbar(self.wrapper_frame, mode='indeterminate',
                                            style='Loading.Horizontal.TProgressbar')
        # -------------------------------------------------

        # --- NEU: Bindung für die Zentrierung des UI-Wrappers ---
        self.bind("<Configure>", self.on_window_resize)
        self.bind("<Map>", self.on_window_resize)  # Beim Sichtbarwerden
        # -------------------------------------------------------

    # --- NEUE FUNKTION: Zentriert das UI-Paket auf der Canvas ---
    def on_window_resize(self, event):
        """Aktualisiert die Position des UI-Wrappers bei Größenänderung."""
        if self.winfo_exists() and self.canvas.winfo_exists():
            x_pos = self.canvas.winfo_width() // 2
            y_pos = self.canvas.winfo_height() // 2
            # (Regel 1) Prüfen ob "ui_wrapper" existiert
            if self.canvas.find_withtag("ui_wrapper"):
                self.canvas.coords("ui_wrapper", x_pos, y_pos)

    # ----------------- ANIMATIONS-CODE (aus SplashScreen) -----------------
    # (Regel 2 & 3)
    def _interpolate_color(self, start_hex, end_hex, ratio):
        """
        Berechnet eine Zwischenfarbe zwischen zwei Hex-Codes.
        Ratio = 0.0 (start_hex) bis 1.0 (end_hex).
        """
        try:
            # Hex zu RGB Tupel konvertieren
            start_rgb = tuple(int(start_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
            end_rgb = tuple(int(end_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))

            # Interpolieren
            r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
            g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
            b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)

            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return end_hex  # Fallback

    def create_nodes(self):
        """Erstellt die 'Datenknoten' an zufälligen Positionen."""
        # (Regel 1) Alte Knoten löschen, falls vorhanden
        for node in self.nodes:
            self.canvas.delete(node['id'])
        self.nodes = []

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        if width <= 1 or height <= 1:
            print("[WARNUNG] Canvas-Größe für Knoten-Erstellung noch 0. Verwende Screen-Größe als Fallback.")
            width = self.winfo_screenwidth()
            height = self.winfo_screenheight()

        for _ in range(self.num_nodes):
            x = random.uniform(5, width - 5)
            y = random.uniform(5, height - 5)
            # Zufällige Geschwindigkeit für X und Y
            dx = random.uniform(-self.max_speed, self.max_speed)
            dy = random.uniform(-self.max_speed, self.max_speed)

            # (dx, dy) dürfen nicht (0, 0) sein
            while dx == 0 and dy == 0:
                dx = random.uniform(-self.max_speed, self.max_speed)
                dy = random.uniform(-self.max_speed, self.max_speed)

            # Knoten als kleine Kreise zeichnen
            oval_id = self.canvas.create_oval(
                x - 2, y - 2, x + 2, y + 2,
                fill=self.node_color,
                outline=""
            )
            self.nodes.append({'id': oval_id, 'x': x, 'y': y, 'dx': dx, 'dy': dy})

    def animate_nodes_and_lines(self):
        """
        Aktualisiert die Knoten-Positionen, lässt sie abprallen
        und zeichnet die Verbindungen basierend auf der Distanz neu.
        """

        # Lösche alle Linien des letzten Frames (Regel 2: Performance)
        self.canvas.delete("connection_line")

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        # 1. Knoten bewegen und abprallen lassen
        for node in self.nodes:
            node['x'] += node['dx']
            node['y'] += node['dy']

            # Abprall-Logik
            if node['x'] <= 0 or node['x'] >= width:
                node['dx'] *= -1
            if node['y'] <= 0 or node['y'] >= height:
                node['dy'] *= -1

            # Position auf Canvas aktualisieren
            self.canvas.coords(node['id'], node['x'] - 2, node['y'] - 2, node['x'] + 2, node['y'] + 2)

        # 2. Linien basierend auf Distanz neu zeichnen
        for i in range(self.num_nodes):
            for j in range(i + 1, self.num_nodes):
                n1 = self.nodes[i]
                n2 = self.nodes[j]

                # Distanz berechnen
                dist = math.hypot(n1['x'] - n2['x'], n1['y'] - n2['y'])

                # Wenn nah genug, zeichne eine Linie
                if dist < self.connection_distance:
                    # Je näher, desto heller (Ratio 1.0 -> 0.0)
                    ratio = dist / self.connection_distance
                    alpha_ratio = 1.0 - ratio
                    alpha_ratio = alpha_ratio ** 2

                    # Farbe von Hintergrund zu Linienfarbe interpolieren
                    color = self._interpolate_color(self.bg_color, self.line_color, alpha_ratio)

                    self.canvas.create_line(
                        n1['x'], n1['y'], n2['x'], n2['y'],
                        fill=color,
                        width=1,
                        tags="connection_line"  # Wichtig für das Löschen
                    )

    def run_animation_loop(self):
        """Die Haupt-Animationsschleife (Ticker)."""
        if not self.running or not self.winfo_exists():
            self.running = False
            return

        try:
            self.animate_nodes_and_lines()
            # (Regel 2) UI nicht blockieren
            self.after(16, self.run_animation_loop)  # ~60 FPS
        except tk.TclError as e:
            # Verhindert Crash, wenn Fenster während Animation geschlossen wird
            print(f"[DEBUG] Animations-Loop gestoppt: {e}")
            self.running = False

    # ----------------- ENDE ANIMATIONS-CODE -----------------

    def _check_startup_threads(self):
        """
        Prüft, ob die Pre-Loading-Threads (DB-Pool UND Daten-Cache) fertig sind
        und aktualisiert die Ladebalken SIMULTAN.
        """
        # ... (Funktion bleibt unverändert) ...
        if not self.winfo_exists():
            return

        db_alive = self.prewarm_thread.is_alive()
        data_alive = self.preload_thread.is_alive()

        # --- 1. DB-Thread (Balken 1) ---
        if self.db_ready:
            # Ist bereits fertig, nichts zu tun
            pass
        elif db_alive:
            # Läuft noch, simuliere Fortschritt
            if self.db_progressbar['value'] < 95:
                self.db_progressbar.step(1.5)  # Etwas schneller simulieren
        else:
            # DB-Thread ist gerade fertig geworden
            pool_obj = db_core.get_db_pool()
            init_flag = db_core.is_db_initialized()

            if pool_obj is not None and init_flag:
                # ERFOLG
                print("[DEBUG] LoginWindow: DB-Pool ist bereit (dynamisch geprüft).")
                self.db_ready = True
                self.db_progressbar['value'] = 100
                self.db_status_label.config(text="Datenbank-Verbindung bereit", style='Success.PreLoading.TLabel')

                # WICHTIG: Login-Button freigeben
                if not self.login_button_enabled:
                    self.login_button.config(state="normal")
                    self.login_button_enabled = True
            else:
                # FEHLSCHLAG
                print("[FEHLER] LoginWindow: DB-Pre-Warming ist fehlgeschlagen (dynamisch geprüft).")
                self.db_ready = True  # Zählt als "fertig", wenn auch fehlgeschlagen
                self.db_progressbar['value'] = 0  # Fehler wird durch Text angezeigt
                self.db_status_label.config(text="Datenbank-Verbindung fehlgeschlagen!",
                                            style='Error.PreLoading.TLabel')

                # Button trotzdem freigeben (Loginversuch wird dann fehlschlagen)
                if not self.login_button_enabled:
                    self.login_button.config(state="normal")
                    self.login_button_enabled = True

        # --- 2. Daten-Thread (Balken 2) ---
        if self.data_ready:
            # Ist bereits fertig, nichts zu tun
            pass
        elif data_alive:
            # Läuft noch, simuliere Fortschritt
            if self.data_progressbar['value'] < 95:
                self.data_progressbar.step(0.7)  # Langsamer simulieren, da Caching länger dauert
        else:
            # Daten-Thread ist gerade fertig geworden
            print("[DEBUG] LoginWindow: Common-Data-Preload ist beendet.")
            self.data_ready = True
            self.data_progressbar['value'] = 100
            self.data_status_label.config(text="Anwendungsdaten bereit", style='Success.PreLoading.TLabel')

        # --- 3. Schleife fortsetzen oder beenden ---
        if not self.db_ready or not self.data_ready:
            # Mindestens ein Thread (oder beide) läuft noch ODER wurde noch nicht geprüft
            self.after(100, self._check_startup_threads)
        else:
            # BEIDE Threads sind beendet (oder fehlgeschlagen)
            print("[DEBUG] LoginWindow: Beide Start-Threads sind abgeschlossen.")
            # Warte kurz, damit der Benutzer den Erfolg sieht, dann blende aus
            self.after(500, self.pre_login_loading_frame.pack_forget)

    # --- MODIFIZIERTE FUNKTION: Startet jetzt auch die Animation ---
    def on_splash_screen_finished(self):
        """
        Wendet Attribute an, die erst nach dem 'deiconify'
        (gesteuert durch main.py/boot_loader.py) gesetzt werden sollen.

        (Regel 2) Startet die Hintergrundanimation.
        """
        print("[DEBUG] LoginWindow.on_splash_screen_finished: Setze -fullscreen.")
        try:
            self.attributes('-fullscreen', True)
            # Wichtig: update_idletasks(), damit winfo_width/height korrekt sind
            self.update_idletasks()
        except tk.TclError as e:
            print(f"[WARNUNG] LoginWindow: Setzen von -fullscreen fehlgeschlagen: {e}")
            # Fallback für den Fall, dass -fullscreen Probleme macht
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
            self.update_idletasks()

        # --- NEU: Animation starten ---
        # UI-Wrapper zentrieren (jetzt, da wir die Größe haben)
        self.on_window_resize(None)

        # Knoten erstellen (jetzt, da wir die Größe haben)
        self.create_nodes()

        # Animation starten
        if not self.running:
            self.running = True
            self.run_animation_loop()
        # -----------------------------

    # --- ENDE NEUE FUNKTION ---

    def attempt_login(self, event=None):
        # ... (Funktion bleibt unverändert) ...
        if not self.login_button_enabled:
            print("[DEBUG] Login-Versuch abgeblockt (DB noch nicht bereit).")
            return

        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()

        if not vorname or not name or not password:
            messagebox.showerror("Eingabe fehlt", "Bitte Vorname, Nachname und Passwort eingeben.", parent=self)
            return

        user_data = authenticate_user(vorname, name, password)

        if user_data:

            # --- NEU (Schritt 4): Dynamisches Hauptfenster ermitteln (Regel 2 & 4) ---
            try:
                # Die Rolle des Benutzers holen (z.B. "Admin")
                user_role = user_data.get('role')

                # Die DB fragen, welches Fenster (z.B. "main_admin_window")
                # (Regel 1) get_main_window_for_role hat einen eingebauten Fallback,
                # falls die Rolle (z.B. "SuperAdmin") noch nicht in der 'roles'-Tabelle
                # eingetragen ist, aber im ENUM existiert.
                main_window_name = get_main_window_for_role(user_role)

                # Den Fensternamen zum user_data-Dict hinzufügen
                user_data['main_window'] = main_window_name
                print(f"[DEBUG] LoginWindow: Rolle '{user_role}' -> Fenster '{main_window_name}' zugewiesen.")

            except Exception as e:
                print(f"[FEHLER] LoginWindow: Konnte Hauptfenster für Rolle '{user_role}' nicht ermitteln: {e}")
                # (Regel 1) Fallback, falls get_main_window_for_role selbst fehlschlägt
                user_data['main_window'] = 'main_admin_window' if user_role in ["Admin",
                                                                                "SuperAdmin"] else 'main_user_window'
            # --- ENDE NEU ---

            log_user_login(user_data['id'], user_data['vorname'], user_data['name'])

            # boot_loader.py (self.app) erhält jetzt user_data inkl. 'main_window'
            self.app.on_login_success(self, user_data)
        else:
            messagebox.showerror("Login fehlgeschlagen", "Benutzername oder Passwort falsch.", parent=self)

    # --- MODIFIZIERT: Stoppt die Animation ---
    def show_loading_ui(self):
        """
        Versteckt das Login-Formular und zeigt die Lade-Animation (POST-Login).
        (Regel 2) Stoppt die Hintergrundanimation.
        """
        print("[DEBUG] LoginWindow.show_loading_ui: Zeige Lade-Animation (Post-Login).")

        # --- NEU: Animation stoppen (Regel 1 & 2) ---
        if self.running:
            print("[DEBUG] Hintergrundanimation wird gestoppt.")
            self.running = False
            # Linien entfernen, um Canvas zu säubern
            self.canvas.delete("connection_line")
            # Optional: Knoten ausblenden
            for node in self.nodes:
                self.canvas.itemconfig(node['id'], state='hidden')
        # --- ENDE NEU ---

        self.main_frame.pack_forget()

        # Stelle sicher, dass der Pre-Login-Lader auch weg ist
        self.pre_login_loading_frame.pack_forget()

        self.loading_label.pack(pady=(20, 10), fill='x', padx=40)
        self.progress_bar.pack(pady=10, fill='x', padx=40)
        self.progress_bar.start(15)

    # --- MODIFIZIERT: Startet die Animation neu ---
    def show_login_ui(self):
        """
        Versteckt die Lade-Animation (POST-Login) und zeigt das Login-Formular wieder an.
        (Wird vom boot_loader bei einem Fehler beim Laden des Hauptfensters aufgerufen)
        (Regel 2) Startet die Hintergrundanimation neu.
        """
        print("[DEBUG] LoginWindow.show_login_ui: Zeige Login-Formular (nach Ladefehler).")
        self.loading_label.pack_forget()
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

        self.main_frame.pack()

        # --- Status-Flags zurücksetzen ---
        self.db_ready = False
        self.data_ready = False  # NEU
        self.login_button_enabled = False
        # ---------------------------------

        # --- Threads neu starten (wichtig!) ---
        print("[Boot Loader] Starte Pre-Warming Thread (erneut)...")
        self.prewarm_thread = threading.Thread(target=db_core.prewarm_connection_pool, daemon=True)
        self.prewarm_thread.start()

        print("[Boot Loader] Starte Common-Data-Pre-Loading Thread (erneut)...")
        self.preload_thread = threading.Thread(target=self.app.preload_common_data, daemon=True)
        self.preload_thread.start()

        # Aktualisiere die Thread-Referenzen in der App
        self.app.prewarm_thread = self.prewarm_thread
        self.app.preload_thread = self.preload_thread
        # --- Ende ---

        # --- UI der Ladebalken zurücksetzen ---
        self.pre_login_loading_frame.pack(fill='x', padx=40, pady=(10, 0))

        self.db_status_label.config(text="Verbindung wird erneut geprüft...", style='PreLoading.TLabel')
        self.db_progressbar.config(value=0)

        self.data_status_label.config(text="Lade Anwendungsdaten...", style='PreLoading.TLabel')
        self.data_progressbar.config(value=0)

        self.login_button.config(state="disabled")

        # Den neuen Checker starten
        self.after(100, self._check_startup_threads)

        # --- NEU: Animation neu starten (Regel 1 & 2) ---
        if not self.running:
            print("[DEBUG] Starte Hintergrundanimation neu (nach Ladefehler).")
            # Optional: Knoten wieder sichtbar machen
            for node in self.nodes:
                self.canvas.itemconfig(node['id'], state='normal')

            # (Regel 1) Stelle sicher, dass Knoten vorhanden sind
            if not self.nodes:
                self.update_idletasks()
                self.create_nodes()

            self.running = True
            self.run_animation_loop()
        # --- ENDE NEU ---

    # ---------------------

    def open_registration(self):
        RegistrationWindow(self)

    def open_password_reset(self, event=None):
        PasswordResetWindow(self)