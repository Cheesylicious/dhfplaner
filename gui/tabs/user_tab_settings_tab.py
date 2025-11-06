import tkinter as tk
from tkinter import ttk, messagebox
from ..tab_lock_manager import TabLockManager


class UserTabSettingsTab(ttk.Frame):
    def __init__(self, master, all_user_tab_names):
        super().__init__(master)
        self.all_user_tab_names = all_user_tab_names
        self.vars = {}

        # --- Styling ---
        style = ttk.Style(self)
        style.configure("Settings.TFrame", background="white")
        style.configure("Title.TLabel", background="white", font=("Segoe UI", 16, "bold"), foreground="#333")
        style.configure("Desc.TLabel", background="white", font=("Segoe UI", 10), foreground="#555")

        style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), background="#2ecc71", foreground="white",
                        padding=(10, 5))
        style.map("Success.TButton", background=[('active', '#27ae60')])

        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), background="#e74c3c", foreground="white",
                        padding=(10, 5))
        style.map("Danger.TButton", background=[('active', '#c0392b')])

        style.configure("Accent.TButton", font=("Segoe UI", 12, "bold"), padding=(20, 10))

        self.setup_ui()

    def setup_ui(self):
        # Der Canvas für die Scrollbar bleibt bestehen
        canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        main_frame = ttk.Frame(canvas, style="Settings.TFrame", padding=(40, 30))

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        canvas_frame_id = canvas.create_window((0, 0), window=main_frame, anchor="nw")

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_frame_id, width=event.width)

        canvas.bind("<Configure>", on_canvas_configure)
        main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        main_frame.columnconfigure(0, weight=1)

        # --- Kopfbereich ---
        header_frame = ttk.Frame(main_frame, style="Settings.TFrame")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(10, 30))

        ttk.Label(header_frame, text="🔒 Benutzer-Reiter verwalten", style="Title.TLabel").pack(anchor="w")
        description = "Aktivieren oder sperren Sie einzelne Reiter für alle Benutzer. Gesperrte Reiter werden in der Benutzeransicht als 'in Wartung' angezeigt und sind nicht zugänglich."
        ttk.Label(header_frame, text=description, wraplength=700, justify="left", style="Desc.TLabel").pack(anchor="w",
                                                                                                            pady=(5, 0))

        ttk.Separator(main_frame, orient='horizontal').grid(row=1, column=0, sticky="ew", pady=(0, 20))

        # --- Einstellungsbereich (JETZT VEREINFACHT) ---
        settings_container = ttk.Frame(main_frame, style="Settings.TFrame")
        settings_container.grid(row=2, column=0, sticky="ew")
        settings_container.columnconfigure(0, weight=1)

        # --- KORREKTUR (Fehlerbehebung): 'load_tab_locks' -> 'load_locks' (Regel 1) ---
        saved_locks = TabLockManager.load_locks()
        # --- ENDE KORREKTUR ---

        row_counter = 0
        for tab_name in self.all_user_tab_names:
            is_enabled = saved_locks.get(tab_name, True)
            self.vars[tab_name] = tk.BooleanVar(value=is_enabled)

            # Verwende ein simples tk.Frame ohne ttk-Style für maximale Kompatibilität
            row_frame = tk.Frame(settings_container, bg="white")
            row_frame.grid(row=row_counter, column=0, sticky="ew", pady=(10, 10))
            row_frame.columnconfigure(0, weight=1)  # Name soll den Platz füllen

            # Verwende ein simples tk.Label mit sichtbarem Hintergrund zur Fehlersuche
            tab_name_label = tk.Label(
                row_frame,
                text=tab_name,
                font=("Segoe UI", 12),
                anchor="w",
                justify="left",
                bg="#e0e0e0",  # Heller Grauton zur Sichtbarkeit
                padx=10
            )
            tab_name_label.grid(row=0, column=0, sticky="ew")

            status_button = ttk.Button(row_frame)
            status_button.grid(row=0, column=1, sticky="e", padx=20)

            def update_button_style(var, button):
                if var.get():
                    button.config(text="Aktiviert", style="Success.TButton")
                else:
                    button.config(text="Gesperrt", style="Danger.TButton")

            def on_toggle(var=self.vars[tab_name]):
                var.set(not var.get())

            status_button.config(command=on_toggle)
            self.vars[tab_name].trace_add("write",
                                          lambda *args, v=self.vars[tab_name], b=status_button: update_button_style(v,
                                                                                                                    b))
            update_button_style(self.vars[tab_name], status_button)

            row_counter += 1

        # --- Fußbereich ---
        footer_frame = ttk.Frame(main_frame, style="Settings.TFrame")
        footer_frame.grid(row=row_counter, column=0, sticky="ew", pady=(30, 10))
        footer_frame.columnconfigure(0, weight=1)

        save_button = ttk.Button(footer_frame, text="Einstellungen speichern", command=self.save_settings,
                                 style="Accent.TButton")
        save_button.grid(row=0, column=0)

    def save_settings(self):
        # --- KORREKTUR (Fehlerbehebung): 'load_tab_locks' -> 'load_locks' (Regel 1) ---
        current_locks = TabLockManager.load_locks()
        # --- ENDE KORREKTUR ---

        for tab_name, var in self.vars.items():
            current_locks[tab_name] = var.get()

        # --- KORREKTUR (Fehlerbehebung): 'save_tab_locks' -> 'save_locks' (Regel 1) ---
        if TabLockManager.save_locks(current_locks):
            # --- ENDE KORREKTUR ---
            messagebox.showinfo("Gespeichert",
                                "Die Einstellungen für die Benutzer-Reiter wurden erfolgreich aktualisiert.",
                                parent=self)
        else:
            messagebox.showerror("Fehler", "Die Einstellungen konnten nicht gespeichert werden.", parent=self)