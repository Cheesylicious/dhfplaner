import tkinter as tk
import random
import math


class SplashScreen(tk.Toplevel):
    """
    Ein rahmenloses Splash-Screen-Fenster mit einer dynamischen
    "Nervensystem/Konstellation"-Animation für einen innovativen Look.

    (Regel 2) Nutzt eine "Viewport"-Logik für einen nahtlosen Übergang,
    basierend auf der Idee des Benutzers.
    """

    def __init__(self, master, width=600, height=400):
        super().__init__(master)
        self.master = master

        # --- MODIFIZIERT: Speichert die Startgröße (Viewport-Größe) ---
        self.start_width = width
        self.start_height = height
        # -----------------------------------------------------------

        # --- Farbpalette ---
        self.bg_color = "#1a1a1a"
        self.accent_color = "#3498db"
        self.node_color = "#3498db"
        self.line_color = "#ecf0f1"
        self.text_color = "#bdc3c7"
        # ---------------------

        # --- Animations-Steuerung ---
        self.animation_step = 0
        self.running = True  # Flag für die HAUPT-Schleife

        # --- Übergangs-Steuerung ---
        self.login_window = None
        self.transition_step = 0
        self.max_transition_steps = 40  # Etwas langsamer für weicheren Effekt
        # ------------------------------

        # --- Partikel-System-Parameter (für Vollbild) ---
        self.nodes = []
        self.num_nodes = 50  # Mehr Knoten für den Vollbild-Effekt
        self.max_speed = 0.5
        self.connection_distance = 150
        # ---------------------------------------------

        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.config(bg=self.bg_color)

        # --- MODIFIZIERT: Speichert Vollbild- und Start-Geometrie ---
        self.get_screen_geometry()
        self.center_window(self.start_width, self.start_height)
        # ----------------------------------------------------------

        self.setup_canvas()

        # --- MODIFIZIERT: Knoten im Vollbild-Koordinatensystem erstellen ---
        self.create_nodes()
        # ---------------------------------------------------------------

        # Starte die Haupt-Animationsschleife
        self.run_animation_loop()

    def get_screen_geometry(self):
        """Ermittelt die Bildschirmgröße und die zentrierte Startposition."""
        try:
            self.screen_width = self.master.winfo_screenwidth()
            self.screen_height = self.master.winfo_screenheight()
        except tk.TclError:
            self.screen_width = 1280
            self.screen_height = 720

        # Start-Position (wo das 600x400 Fenster beginnt)
        self.start_x = (self.screen_width // 2) - (self.start_width // 2)
        self.start_y = (self.screen_height // 2) - (self.start_height // 2)

        # Aktuelle Position (für die Animation)
        self.current_x = self.start_x
        self.current_y = self.start_y

    def center_window(self, width, height):
        """Setzt die Fenstergeometrie auf die übergebenen Werte."""
        try:
            x_pos = (self.screen_width // 2) - (width // 2)
            y_pos = (self.screen_height // 2) - (height // 2)
            self.geometry(f'{width}x{height}+{x_pos}+{y_pos}')
        except tk.TclError:
            self.geometry(f'{width}x{height}+100+100')

    def setup_canvas(self):
        """Erstellt die Canvas (sie füllt immer das Toplevel-Fenster)."""
        self.canvas = tk.Canvas(
            self,
            bg=self.bg_color,
            width=self.start_width,
            height=self.start_height,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 1. Haupt-Logo (Zentriert im 600x400 Viewport)
        self.logo_id = self.canvas.create_text(
            self.start_width / 2,
            self.start_height / 2,
            text="DHFPlaner",
            font=("Segoe UI", 60, "bold"),
            fill=self.bg_color
        )

        # 2. Lade-Text (Zentriert im 600x400 Viewport)
        self.text_id = self.canvas.create_text(
            self.start_width / 2,
            self.start_height / 2 + 55,
            text="Daten werden vorbereitet...",
            font=("Segoe UI", 14),
            fill=self.bg_color
        )

        # Dieses Binding ist jetzt nur noch für die *Start*-Animation (Fade-In)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

    def on_canvas_resize(self, event):
        """Zentriert die Texte neu, wenn die Canvas (durch Animation) wächst."""
        if not self.running:
            return
        try:
            w, h = event.width, event.height
            self.canvas.coords(self.logo_id, w / 2, h / 2)
            self.canvas.coords(self.text_id, w / 2, h / 2 + 55)
        except tk.TclError:
            pass

    # --- MODIFIZIERTE FUNKTION (Regel 2) ---
    def create_nodes(self):
        """
        Erstellt die 'Datenknoten' im VOLLBILD-Koordinatensystem
        und zeichnet sie relativ zum Viewport.
        """
        for _ in range(self.num_nodes):
            # 1. Absolute "Welt"-Position (irgendwo im Vollbild)
            px = random.uniform(0, self.screen_width)
            py = random.uniform(0, self.screen_height)

            dx = random.uniform(-self.max_speed, self.max_speed)
            dy = random.uniform(-self.max_speed, self.max_speed)
            while dx == 0 and dy == 0:
                dx = random.uniform(-self.max_speed, self.max_speed)
                dy = random.uniform(-self.max_speed, self.max_speed)

            # 2. Relative "Draw"-Position (wo auf der Canvas gezeichnet wird)
            #    (Welt-Position - Viewport-Startposition)
            draw_x = px - self.start_x
            draw_y = py - self.start_y

            oval_id = self.canvas.create_oval(
                draw_x - 2, draw_y - 2, draw_x + 2, draw_y + 2,
                fill=self.node_color,
                outline=""
            )

            # Speichere die "Welt"-Position
            self.nodes.append({'id': oval_id, 'px': px, 'py': py, 'dx': dx, 'dy': dy})

    def _interpolate_color(self, start_hex, end_hex, ratio):
        """Berechnet eine Zwischenfarbe zwischen zwei Hex-Codes."""
        # (Unverändert)
        try:
            start_rgb = tuple(int(start_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
            end_rgb = tuple(int(end_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
            r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
            g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
            b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return end_hex

    def run_animation_loop(self):
        """Die Haupt-Animationsschleife (Ticker)."""
        if not self.running or not self.winfo_exists():
            return
        try:
            # Aktualisiert Partikel (relativ zu self.current_x/y)
            self.animate_nodes_and_lines(self.current_x, self.current_y)
            self.animate_text_fade_in()
            self.animation_step += 1
            self.after(16, self.run_animation_loop)
        except tk.TclError:
            self.running = False

    def animate_text_fade_in(self):
        """Animiert das Einblenden von Logo und Lade-Text."""
        # (Unverändert)
        if not self.running:
            return
        start_delay_logo = 30
        fade_duration_logo = 90
        if self.animation_step > start_delay_logo:
            step = self.animation_step - start_delay_logo
            if step <= fade_duration_logo:
                ratio = step / fade_duration_logo
                ratio = 1 - (1 - ratio) ** 3
                color = self._interpolate_color(self.bg_color, self.accent_color, ratio)
                self.canvas.itemconfig(self.logo_id, fill=color)
            elif step == fade_duration_logo + 1:
                self.canvas.itemconfig(self.logo_id, fill=self.accent_color)
        start_delay_text = start_delay_logo + fade_duration_logo - 30
        fade_duration_text = 60
        if self.animation_step > start_delay_text:
            step = self.animation_step - start_delay_text
            if step <= fade_duration_text:
                ratio = step / fade_duration_text
                color = self._interpolate_color(self.bg_color, self.text_color, ratio)
                self.canvas.itemconfig(self.text_id, fill=color)
            elif step == fade_duration_text + 1:
                self.canvas.itemconfig(self.text_id, fill=self.text_color)

    # --- MODIFIZIERTE FUNKTION (Regel 2) ---
    def animate_nodes_and_lines(self, viewport_x, viewport_y):
        """
        Aktualisiert die Knoten-Positionen im VOLLBILD-Raum
        und zeichnet sie relativ zum übergebenen Viewport (viewport_x/y).
        """
        if not self.winfo_exists():
            return

        try:
            self.canvas.delete("connection_line")

            for node in self.nodes:
                # 1. "Welt"-Position aktualisieren
                node['px'] += node['dx']
                node['py'] += node['dy']

                # 2. Abprall-Logik im "Welt"-Raum (Vollbild)
                if node['px'] <= 0 or node['px'] >= self.screen_width:
                    node['dx'] *= -1
                if node['py'] <= 0 or node['py'] >= self.screen_height:
                    node['dy'] *= -1

                # 3. "Draw"-Position berechnen (relativ zum Viewport)
                draw_x = node['px'] - viewport_x
                draw_y = node['py'] - viewport_y

                # 4. Auf Canvas zeichnen
                self.canvas.coords(node['id'], draw_x - 2, draw_y - 2, draw_x + 2, draw_y + 2)

            # Linien zeichnen (auch relativ)
            for i in range(self.num_nodes):
                for j in range(i + 1, self.num_nodes):
                    n1 = self.nodes[i]
                    n2 = self.nodes[j]

                    # Distanz im "Welt"-Raum berechnen
                    dist = math.hypot(n1['px'] - n2['px'], n1['py'] - n2['py'])

                    if dist < self.connection_distance:
                        ratio = dist / self.connection_distance
                        alpha_ratio = 1.0 - ratio
                        alpha_ratio = alpha_ratio ** 2
                        color = self._interpolate_color(self.bg_color, self.line_color, alpha_ratio)

                        # Relativ zum Viewport zeichnen
                        self.canvas.create_line(
                            n1['px'] - viewport_x, n1['py'] - viewport_y,
                            n2['px'] - viewport_x, n2['py'] - viewport_y,
                            fill=color,
                            width=1,
                            tags="connection_line"
                        )
        except tk.TclError:
            self.running = False  # Stoppt bei Fehler (z.B. Fensterzerstörung)

    def start_transition_and_close(self, login_window):
        """
        Stoppt die alte Animationsschleife und startet die neue
        kombinierte Übergangs-Schleife.
        """
        print("[DEBUG] Splash-Screen: Starte Übergang zu LoginWindow.")
        self.running = False  # Stoppt die Standard-Animationsschleife
        self.login_window = login_window

        # Ziel-Geometrie (Vollbild)
        self.target_width = self.screen_width
        self.target_height = self.screen_height
        self.target_x = 0
        self.target_y = 0

        # Starte die NEUE, kombinierte Übergangs-Schleife (Regel 2)
        self.after(16, self._run_transition_loop)

    # --- STARK MODIFIZIERTE FUNKTION (Regel 2 & 3) ---
    def _run_transition_loop(self):
        """
        Die kombinierte Schleife für die Übergangs-Animation.
        Diese Schleife übernimmt ALLE Aufgaben:
        1. Fenster-Geometrie animieren
        2. Partikel-Animation (aus animate_nodes_and_lines) weiterführen
        3. Text ausblenden und zentriert halten
        """
        if not self.winfo_exists():
            return

        if self.transition_step <= self.max_transition_steps:

            # --- 1. GEOMETRIE BERECHNEN (Fenster-Expansion) ---
            ratio = self.transition_step / self.max_transition_steps
            anim_ratio = 1 - (1 - ratio) ** 3  # Ease-Out

            current_width = int(self.start_width + (self.target_width - self.start_width) * anim_ratio)
            current_height = int(self.start_height + (self.target_height - self.start_height) * anim_ratio)

            # (Regel 2) self.current_x/y für die Partikel-Berechnung aktualisieren
            self.current_x = int(self.start_x + (self.target_x - self.start_x) * anim_ratio)
            self.current_y = int(self.start_y + (self.target_y - self.start_y) * anim_ratio)

            try:
                self.geometry(f'{current_width}x{current_height}+{self.current_x}+{self.current_y}')
            except tk.TclError:
                self.transition_step = self.max_transition_steps  # Springe zum Ende

            # --- 2. PARTIKEL-ANIMATION (Logik aus animate_nodes_and_lines) ---
            # (Regel 2) Führt die Animation weiter, aber mit den *neuen*
            # Viewport-Koordinaten (self.current_x, self.current_y).
            # Das sorgt dafür, dass die Partikel "enthüllt" werden.
            self.animate_nodes_and_lines(self.current_x, self.current_y)

            # --- 3. TEXT-ANIMATION (Fade-Out & Re-Zentrierung) ---
            fade_ratio = ratio ** 2  # Ease-In
            fade_ratio = min(1.0, fade_ratio)

            try:
                # (Regel 2) Berechne das NEUE Zentrum der (jetzt größeren) Canvas
                new_center_x = current_width / 2
                new_center_y = current_height / 2

                if self.canvas.find_withtag(self.logo_id):
                    logo_color = self._interpolate_color(self.accent_color, self.bg_color, fade_ratio)
                    self.canvas.itemconfig(self.logo_id, fill=logo_color)
                    self.canvas.coords(self.logo_id, new_center_x, new_center_y)

                if self.canvas.find_withtag(self.text_id):
                    text_color = self._interpolate_color(self.text_color, self.bg_color, fade_ratio)
                    self.canvas.itemconfig(self.text_id, fill=text_color)
                    self.canvas.coords(self.text_id, new_center_x, new_center_y + 55)

            except tk.TclError:
                pass  # Fenster wird evtl. gerade zerstört

            # Loop fortsetzen
            self.transition_step += 1
            self.after(16, self._run_transition_loop)

        else:
            # --- Animation abgeschlossen ---
            print("[DEBUG] Splash-Screen: Übergangs-Animation beendet.")
            try:
                self.login_window.deiconify()
                self.login_window.lift()
                self.login_window.focus_force()
                # (Regel 1) Übergibt die Kontrolle an das Login-Fenster
                self.login_window.on_splash_screen_finished()
            except tk.TclError as e:
                print(f"[FEHLER] Übergabe an LoginWindow fehlgeschlagen: {e}")

            # 3. Splash-Screen (sich selbst) zerstören
            self.after(50, self.destroy)  # Mit leichter Verzögerung zerstören

    def close_splash(self):
        """
        Stoppt die Animation und zerstört das Splash-Screen-Fenster.
        (Fallback, Regel 1)
        """
        print("[DEBUG] Splash-Screen: Animations-Loop wird gestoppt (close_splash).")
        self.running = False
        self.destroy()