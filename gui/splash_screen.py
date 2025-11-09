import tkinter as tk
import random
import math


class SplashScreen(tk.Toplevel):
    """
    Ein rahmenloses Splash-Screen-Fenster mit einer dynamischen
    "Nervensystem/Konstellation"-Animation für einen innovativen Look.
    (Regel 2: Innovativ, keine GUI-Blockade)
    """

    def __init__(self, master, width=600, height=400):
        super().__init__(master)
        self.master = master
        self.width = width
        self.height = height

        # --- Farbpalette ---
        self.bg_color = "#1a1a1a"  # Noch dunklerer Hintergrund
        self.accent_color = "#3498db"  # Akzentfarbe (Logo)
        self.node_color = "#3498db"  # Akzentfarbe (Knoten)
        self.line_color = "#ecf0f1"  # Helles Grau (Linien)
        self.text_color = "#bdc3c7"  # Gedimmtes Grau (Text)
        # ---------------------

        # --- Animations-Steuerung ---
        self.animation_step = 0
        self.running = True  # Flag zum Stoppen der Animations-Schleife

        # --- Partikel-System-Parameter ---
        self.nodes = []
        self.num_nodes = 30  # Anzahl der "Datenknoten"
        self.max_speed = 0.5  # Maximale Geschwindigkeit der Knoten
        self.connection_distance = 150  # Maximale Distanz für eine Verbindung
        # -------------------------------

        # Fenstereigenschaften (rahmenlos, immer oben)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.config(bg=self.bg_color)  # Hintergrund setzen

        self.center_window()
        self.setup_canvas()
        self.create_nodes()

        # Starte die Haupt-Animationsschleife
        self.run_animation_loop()

    def center_window(self):
        """Zentriert das Fenster auf dem Bildschirm."""
        try:
            screen_width = self.master.winfo_screenwidth()
            screen_height = self.master.winfo_screenheight()
            x_pos = (screen_width // 2) - (self.width // 2)
            y_pos = (screen_height // 2) - (self.height // 2)
            self.geometry(f'{self.width}x{self.height}+{x_pos}+{y_pos}')
        except tk.TclError:
            self.geometry(f'{self.width}x{self.height}+100+100')

    def setup_canvas(self):
        """Erstellt die Canvas, auf der alle Animationen gezeichnet werden."""
        self.canvas = tk.Canvas(
            self,
            bg=self.bg_color,
            width=self.width,
            height=self.height,
            highlightthickness=0  # Kein Rand um die Canvas
        )
        self.canvas.pack()

        # Erstelle die Text-Objekte (anfangs unsichtbar)

        # 1. Haupt-Logo
        self.logo_id = self.canvas.create_text(
            self.width / 2,
            self.height / 2,  # Zentriert
            text="DHFPlaner",
            font=("Segoe UI", 60, "bold"),
            fill=self.bg_color  # Startet unsichtbar
        )

        # 2. Lade-Text (unter dem Logo)
        self.text_id = self.canvas.create_text(
            self.width / 2,
            self.height / 2 + 55,  # Unter dem Logo
            text="Daten werden vorbereitet...",
            font=("Segoe UI", 14),
            fill=self.bg_color  # Startet unsichtbar
        )

    def create_nodes(self):
        """Erstellt die 'Datenknoten' an zufälligen Positionen."""
        for _ in range(self.num_nodes):
            x = random.uniform(5, self.width - 5)
            y = random.uniform(5, self.height - 5)
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

    def run_animation_loop(self):
        """Die Haupt-Animationsschleife (Ticker)."""
        if not self.running:
            return

        # Rufe die einzelnen Animations-Handler auf
        self.animate_nodes_and_lines()
        self.animate_text_fade_in()

        self.animation_step += 1
        self.after(16, self.run_animation_loop)  # ~60 FPS

    def animate_text_fade_in(self):
        """Animiert das Einblenden von Logo und Lade-Text."""

        # 1. Logo-Fade-In (Start nach 30 Frames)
        start_delay_logo = 30
        fade_duration_logo = 90

        if self.animation_step > start_delay_logo:
            step = self.animation_step - start_delay_logo
            if step <= fade_duration_logo:
                ratio = step / fade_duration_logo
                # Sanfterer Fade-In (Ease-Out-Effekt)
                ratio = 1 - (1 - ratio) ** 3
                color = self._interpolate_color(self.bg_color, self.accent_color, ratio)
                self.canvas.itemconfig(self.logo_id, fill=color)
            elif step == fade_duration_logo + 1:
                self.canvas.itemconfig(self.logo_id, fill=self.accent_color)

        # 2. Sub-Text-Fade-In (Startet, nachdem Logo fast fertig ist)
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

    def animate_nodes_and_lines(self):
        """
        Aktualisiert die Knoten-Positionen, lässt sie abprallen
        und zeichnet die Verbindungen basierend auf der Distanz neu.
        """

        # Lösche alle Linien des letzten Frames (Regel 2: Performance)
        self.canvas.delete("connection_line")

        # 1. Knoten bewegen und abprallen lassen
        for node in self.nodes:
            node['x'] += node['dx']
            node['y'] += node['dy']

            # Abprall-Logik
            if node['x'] <= 0 or node['x'] >= self.width:
                node['dx'] *= -1
            if node['y'] <= 0 or node['y'] >= self.height:
                node['dy'] *= -1

            # Position auf Canvas aktualisieren
            self.canvas.coords(node['id'], node['x'] - 2, node['y'] - 2, node['x'] + 2, node['y'] + 2)

        # 2. Linien basierend auf Distanz neu zeichnen
        #    (Ineffizient, aber der "übertriebene" Effekt)
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
                    # (1.0 - ratio) -> 0.0 (nah) bis 1.0 (fern)
                    # Wir wollen, dass nah = hell (ratio 1.0) und fern = dunkel (ratio 0.0)
                    alpha_ratio = 1.0 - ratio

                    # Alpha-Ratio dämpfen (damit nicht alle Linien zu hell sind)
                    alpha_ratio = alpha_ratio ** 2

                    # Farbe von Hintergrund zu Linienfarbe interpolieren
                    color = self._interpolate_color(self.bg_color, self.line_color, alpha_ratio)

                    self.canvas.create_line(
                        n1['x'], n1['y'], n2['x'], n2['y'],
                        fill=color,
                        width=1,
                        tags="connection_line"  # Wichtig für das Löschen
                    )

    def close_splash(self):
        """
        Stoppt die Animation und zerstört das Splash-Screen-Fenster.
        Wird von außen (main.py) aufgerufen.
        """
        print("[DEBUG] Splash-Screen: Animations-Loop wird gestoppt.")
        self.running = False
        self.destroy()