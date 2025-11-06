import tkinter as tk
from tkinter import ttk, messagebox
# HIER WIRD 'add_user' durch 'register_user' ersetzt
from database.db_users import register_user, get_user_count

# --- NEU (Zentralisierung): Import aus dem Window Manager (Regel 4) ---
try:
    from gui.window_manager import get_window_options_for_registration, get_default_role_for_window
except ImportError:
    # (Regel 1) Fallback, falls Import fehlschlägt
    print("[FEHLER] registration_window: window_manager.py nicht gefunden. Verwende Fallbacks.")


    def get_window_options_for_registration():
        return [('Benutzer-Fenster', 'main_user_window'), ('Zuteilungs-Fenster', 'main_zuteilung_window')]


    def get_default_role_for_window(key):
        return "Guest" if key == 'main_zuteilung_window' else 'Benutzer'


# --- ENDE NEU ---

class RegistrationWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Registrierung")
        # --- Geometrie angepasst für neues Feld ---
        self.geometry("400x350")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        # --- NEU (Regel 4): Fenster-Optionen laden ---
        # Speichert die Fensteroptionen (Anzeigename, DB-Key)
        self.window_options = get_window_options_for_registration()
        # Speichert die Anzeigenamen für die Combobox
        self.window_display_names = [name for name, key in self.window_options]
        # Variable für die Combobox
        self.selected_window_var = tk.StringVar()
        # --- ENDE NEU ---

        # Style-Konfiguration
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('TButton', font=('Helvetica', 10), padding=5)
        style.configure('TEntry', font=('Helvetica', 10), padding=5)
        # Stil für die neue Combobox (damit sie zum Rest passt)
        style.map('TCombobox', fieldbackground=[('readonly', 'white')])
        style.configure('TCombobox', font=('Helvetica', 10), padding=5)

        self.create_widgets(style)

        # --- NEU: Standardwert setzen (Regel 1) ---
        if self.window_display_names:
            # Setzt den Standard auf "Zuteilungs-Fenster", falls vorhanden (gemäß Anforderung "parken")
            default_selection = "Zuteilungs-Fenster" if "Zuteilungs-Fenster" in self.window_display_names else \
            self.window_display_names[0]
            self.selected_window_var.set(default_selection)
        # --- ENDE NEU ---

    def create_widgets(self, style):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(expand=True, fill='both')

        ttk.Label(main_frame, text="Vorname:", style='TLabel').grid(row=0, column=0, sticky='w', pady=5, padx=5)
        self.vorname_entry = ttk.Entry(main_frame, style='TEntry')
        self.vorname_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(main_frame, text="Name:", style='TLabel').grid(row=1, column=0, sticky='w', pady=5, padx=5)
        self.name_entry = ttk.Entry(main_frame, style='TEntry')
        self.name_entry.grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(main_frame, text="Passwort:", style='TLabel').grid(row=2, column=0, sticky='w', pady=5, padx=5)
        self.password_entry = ttk.Entry(main_frame, show="*", style='TEntry')
        self.password_entry.grid(row=2, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(main_frame, text="Passwort bestätigen:", style='TLabel').grid(row=3, column=0, sticky='w', pady=5,
                                                                                padx=5)
        self.confirm_password_entry = ttk.Entry(main_frame, show="*", style='TEntry')
        self.confirm_password_entry.grid(row=3, column=1, sticky='ew', pady=5, padx=5)

        # --- NEU: Combobox für Fensterauswahl (Regel 4) ---
        ttk.Label(main_frame, text="Kontotyp:", style='TLabel').grid(row=4, column=0, sticky='w', pady=5, padx=5)
        self.window_combo = ttk.Combobox(
            main_frame,
            textvariable=self.selected_window_var,
            values=self.window_display_names,
            state='readonly'  # Verhindert, dass Benutzer eigene Werte eingeben
        )
        self.window_combo.grid(row=4, column=1, sticky='ew', pady=5, padx=5)
        # --- ENDE NEU ---

        reg_button = ttk.Button(main_frame, text="Registrieren", command=self.register, style='TButton')
        # --- KORREKTUR: Zeilennummer angepasst ---
        reg_button.grid(row=5, column=0, columnspan=2, pady=20)
        # --- ENDE KORREKTUR ---

        main_frame.columnconfigure(1, weight=1)

    def register(self):
        vorname = self.vorname_entry.get()
        name = self.name_entry.get()
        password = self.password_entry.get()
        confirm_password = self.confirm_password_entry.get()

        # --- NEU: Ausgewähltes Fenster holen ---
        selected_display_name = self.selected_window_var.get()
        # --- ENDE NEU ---

        if not all([vorname, name, password, confirm_password, selected_display_name]):
            messagebox.showerror("Fehler", "Alle Felder müssen ausgefüllt sein.", parent=self)
            return

        if password != confirm_password:
            messagebox.showerror("Fehler", "Die Passwörter stimmen nicht überein.", parent=self)
            return

        # --- KORREKTUR: Dynamische Rollenzuweisung (Regel 1 & 4) ---

        # 1. Prüfen, ob dies der allererste Benutzer ist (SuperAdmin-Logik)
        if get_user_count() == 0:
            role = "SuperAdmin"
            print("Erster Benutzer wird als SuperAdmin registriert.")
        else:
            # 2. Den DB-Key für den ausgewählten Anzeigenamen finden
            # (Fallback auf 'main_zuteilung_window', falls etwas schiefgeht)
            db_window_key = 'main_zuteilung_window'  # Fallback (sicherster Ort zum Parken)
            for display_name, key in self.window_options:
                if display_name == selected_display_name:
                    db_window_key = key
                    break

            # 3. Die Standardrolle für dieses Fenster abfragen (z.B. "Guest")
            role = get_default_role_for_window(db_window_key)
            print(f"Registrierung für '{selected_display_name}' (Key: {db_window_key}). Zugewiesene Rolle: {role}")

        # HIER WIRD der Funktionsaufruf angepasst
        success, message = register_user(vorname, name, password, role)
        # --- ENDE KORREKTUR ---

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.destroy()
        else:
            messagebox.showerror("Fehler bei der Registrierung", message, parent=self)


