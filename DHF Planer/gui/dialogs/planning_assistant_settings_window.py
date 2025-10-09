# gui/dialogs/planning_assistant_settings_window.py
import tkinter as tk
from tkinter import ttk, messagebox
from gui.admin_menu_config_manager import AdminMenuConfigManager

class PlanningAssistantSettingsWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master # Referenz auf MainAdminWindow
        self.title("Einstellungen für Planungs-Helfer")
        self.geometry("450x450")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)

        visibility_frame = ttk.LabelFrame(main_frame, text="Sichtbarkeit im Auswahlmenü", padding="10")
        visibility_frame.pack(fill="x", expand=True)

        ttk.Label(visibility_frame, text="Wähle aus, welche Schichten im Schnell-Menü angezeigt werden sollen.",
                  wraplength=380).pack(anchor="w", pady=(0, 10))

        self.vis_vars = {}
        all_shifts = sorted(self.master.shift_types_data.keys())
        self.menu_config = AdminMenuConfigManager.load_config(all_shifts)

        for shift_abbrev in all_shifts:
            is_visible = self.menu_config.get(shift_abbrev, True)
            self.vis_vars[shift_abbrev] = tk.BooleanVar(value=is_visible)
            ttk.Checkbutton(visibility_frame, text=f"'{shift_abbrev}' anzeigen",
                            variable=self.vis_vars[shift_abbrev]).pack(anchor="w")

        counter_frame = ttk.LabelFrame(main_frame, text="Häufigkeits-Zähler", padding="10")
        counter_frame.pack(fill="x", pady=(20, 0))

        # Zugriff auf die Methode in der Haupt-App
        ttk.Button(counter_frame, text="Zähler jetzt zurücksetzen", command=self.master.reset_shift_frequency).pack(pady=5)

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(20, 0), side="bottom")
        button_bar.columnconfigure((0, 1), weight=1)

        ttk.Button(button_bar, text="Speichern & Schließen", command=self.save_and_close).grid(row=0, column=0,
                                                                                               sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def save_and_close(self):
        new_config = {key: var.get() for key, var in self.vis_vars.items()}
        AdminMenuConfigManager.save_config(new_config)
        messagebox.showinfo("Gespeichert", "Die Einstellungen für das Auswahlmenü wurden gespeichert.", parent=self)
        self.destroy()