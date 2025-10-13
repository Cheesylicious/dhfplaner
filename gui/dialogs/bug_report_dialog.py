# gui/dialogs/bug_report_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_reports import create_bug_report


class BugReportDialog(tk.Toplevel):
    def __init__(self, parent, user_id, callback=None):
        super().__init__(parent)
        self.transient(parent)
        self.title("Bug / Fehler melden")
        self.user_id = user_id
        self.callback = callback
        self.grab_set()

        # Die Kategorien für das Dropdown
        self.categories = ["Unwichtiger Fehler", "Schönheitsfehler", "Kleiner Fehler", "Mittlerer Fehler",
                           "Kritischer Fehler"]

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Titel:", font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky="w",
                                                                                 pady=(0, 5))
        self.title_entry = ttk.Entry(main_frame, width=60)
        self.title_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # NEUES KATEGORIE-FELD
        ttk.Label(main_frame, text="Kategorie:", font=('Segoe UI', 10, 'bold')).grid(row=2, column=0, sticky="w",
                                                                                     pady=(0, 5))
        self.category_combobox = ttk.Combobox(main_frame, values=self.categories, state="readonly")
        self.category_combobox.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.category_combobox.set("Kleiner Fehler")  # Standardwert

        ttk.Label(main_frame, text="Detaillierte Beschreibung:", font=('Segoe UI', 10, 'bold')).grid(row=4, column=0,
                                                                                                     sticky="w",
                                                                                                     pady=(0, 5))
        self.desc_text = tk.Text(main_frame, height=12, width=60, wrap="word", relief="solid", borderwidth=1)
        self.desc_text.grid(row=5, column=0, columnspan=2, sticky="nsew")
        main_frame.rowconfigure(5, weight=1)
        main_frame.columnconfigure(1, weight=1)

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=2, sticky="e", pady=(15, 0))

        ttk.Button(button_frame, text="Absenden", command=self.submit_report).pack(side="right")
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=10)

    def submit_report(self):
        title = self.title_entry.get().strip()
        description = self.desc_text.get("1.0", tk.END).strip()
        category = self.category_combobox.get()

        if not title or not description:
            messagebox.showwarning("Fehlende Eingabe",
                                   "Bitte füllen Sie sowohl den Titel als auch die Beschreibung aus.", parent=self)
            return

        if not category:
            messagebox.showwarning("Fehlende Eingabe", "Bitte wählen Sie eine Kategorie aus.", parent=self)
            return

        success, message = create_bug_report(self.user_id, title, description, category)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            if self.callback:
                self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", f"Der Bericht konnte nicht gesendet werden:\n{message}", parent=self)