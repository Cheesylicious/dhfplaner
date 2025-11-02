# gui/dialogs/custom_messagebox.py
import tkinter as tk
from tkinter import ttk


class CustomMessagebox(tk.Toplevel):
    def __init__(self, parent, title, message, callback):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.callback = callback
        self.dont_show_again = tk.BooleanVar()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(expand=True, fill="both")

        ttk.Label(main_frame, text=message, wraplength=300).pack(pady=(0, 20))

        check_frame = ttk.Frame(main_frame)
        check_frame.pack(fill="x", pady=5)
        ttk.Checkbutton(check_frame, text="Nicht mehr anzeigen (für diese Sitzung)",
                        variable=self.dont_show_again).pack(anchor="w")

        ok_button = ttk.Button(main_frame, text="OK", command=self.on_ok)
        ok_button.pack(pady=(10, 0))
        self.bind("<Return>", lambda e: self.on_ok())

        self.protocol("WM_DELETE_WINDOW", self.on_ok)

        # Fenster zentrieren
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_reqwidth()) / 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_reqheight()) / 2
        self.geometry(f"+{int(x)}+{int(y)}")

    def on_ok(self):
        if self.dont_show_again.get():
            self.callback()
        self.destroy()