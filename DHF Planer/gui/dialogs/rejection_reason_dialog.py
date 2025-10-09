# gui/dialogs/rejection_reason_dialog.py
import tkinter as tk
from tkinter import ttk


class RejectionReasonDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Ablehnungsgrund")
        self.geometry("400x160")

        self.reason = ""
        self.result = False  # Wird True, wenn der Benutzer auf OK klickt

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Bitte geben Sie einen Grund für die Ablehnung an:", wraplength=350).pack(anchor="w",
                                                                                                             pady=(
                                                                                                             0, 10))

        self.reason_entry = ttk.Entry(main_frame, width=50)
        self.reason_entry.pack(fill="x", expand=True, ipady=4)
        self.reason_entry.focus_set()

        self.reason_entry.bind("<Return>", self.on_ok)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(15, 0))
        button_frame.columnconfigure((0, 1), weight=1)

        ttk.Button(button_frame, text="OK", command=self.on_ok).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_frame, text="Abbrechen", command=self.on_cancel).grid(row=0, column=1, sticky="ew",
                                                                                padx=(5, 0))

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # --- KORRIGIERTE LOGIK ZUM ZENTRIEREN DES FENSTERS ---
        # Stellt sicher, dass die Fenstergröße berechnet ist, bevor die Position gesetzt wird
        self.update_idletasks()

        # Holt das Hauptfenster (Toplevel), um sich daran zu zentrieren
        toplevel = parent.winfo_toplevel()
        parent_x = toplevel.winfo_rootx()
        parent_y = toplevel.winfo_rooty()
        parent_width = toplevel.winfo_width()
        parent_height = toplevel.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        position_x = parent_x + (parent_width // 2) - (dialog_width // 2)
        position_y = parent_y + (parent_height // 2) - (dialog_height // 2)

        # Setzt die Position des Dialogfensters
        self.geometry(f"+{position_x}+{position_y}")

        # Wartet, bis dieses Fenster geschlossen wird
        self.wait_window(self)

    def on_ok(self, event=None):
        self.reason = self.reason_entry.get().strip()
        self.result = True
        self.destroy()

    def on_cancel(self):
        self.result = False
        self.destroy()