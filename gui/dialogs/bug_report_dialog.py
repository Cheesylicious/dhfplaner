# gui/dialogs/bug_report_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox
from database.db_reports import submit_bug_report

class BugReportDialog(tk.Toplevel):
    def __init__(self, master, user_id, callback=None):
        super().__init__(master)
        self.user_id = user_id
        self.callback = callback
        self.title("Bug / Fehler melden")
        self.geometry("450x400")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Titel:").pack(anchor="w")
        self.title_entry = ttk.Entry(main_frame)
        self.title_entry.pack(fill="x", pady=(2, 10))

        ttk.Label(main_frame, text="Detaillierte Beschreibung:").pack(anchor="w")
        self.description_text = tk.Text(main_frame, height=10)
        self.description_text.pack(fill="both", expand=True, pady=(2, 10))

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(10, 0))
        button_bar.columnconfigure((0, 1), weight=1)

        ttk.Button(button_bar, text="Senden", command=self.submit).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def submit(self):
        title = self.title_entry.get().strip()
        description = self.description_text.get("1.0", tk.END).strip()

        if not title or not description:
            messagebox.showwarning("Eingabe fehlt", "Bitte geben Sie einen Titel und eine Beschreibung an.", parent=self)
            return

        success, message = submit_bug_report(self.user_id, title, description)
        if success:
            messagebox.showinfo("Erfolg", "Fehlerbericht wurde erfolgreich gesendet.", parent=self)
            if self.callback:
                self.callback()
            self.destroy()
        else:
            messagebox.showerror("Fehler", f"Fehler beim Senden des Berichts: {message}", parent=self)