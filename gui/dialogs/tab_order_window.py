# gui/dialogs/tab_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os

TAB_ORDER_FILE = 'tab_order_config.json'


class TabOrderManager:
    """Verwaltet die Reihenfolge der Reiter im Admin-Fenster."""
    DEFAULT_ORDER = [
        "Schichtplan", "Offene Anfragen", "Urlaubsanträge",
        "Benutzerverwaltung", "Diensthunde", "Schichtarten", "Protokoll"
    ]

    @staticmethod
    def load_order():
        if not os.path.exists(TAB_ORDER_FILE):
            TabOrderManager.save_order(TabOrderManager.DEFAULT_ORDER)
            return TabOrderManager.DEFAULT_ORDER
        try:
            with open(TAB_ORDER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return TabOrderManager.DEFAULT_ORDER

    @staticmethod
    def save_order(order_list):
        try:
            with open(TAB_ORDER_FILE, 'w', encoding='utf-8') as f:
                json.dump(order_list, f, indent=4)
            return True
        except IOError:
            return False


class TabOrderWindow(tk.Toplevel):
    """Fenster zum Anpassen der Reiter-Reihenfolge."""

    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Reiter-Reihenfolge anpassen")
        self.geometry("400x500")
        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Ändern Sie die Reihenfolge der Reiter im Hauptfenster.").pack(anchor="w",
                                                                                                  pady=(0, 10))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.tab_listbox = tk.Listbox(list_frame, selectmode="single")
        self.tab_listbox.grid(row=0, column=0, sticky="nsew")

        button_subframe = ttk.Frame(list_frame)
        button_subframe.grid(row=0, column=1, sticky="ns", padx=(10, 0))

        ttk.Button(button_subframe, text="↑ Hoch", command=lambda: self.move_item(-1)).pack(pady=2, fill="x")
        ttk.Button(button_subframe, text="↓ Runter", command=lambda: self.move_item(1)).pack(pady=2, fill="x")

        # Initialbefüllung der Liste
        current_order = TabOrderManager.load_order()
        for tab_name in current_order:
            self.tab_listbox.insert(tk.END, tab_name)

        button_bar = ttk.Frame(main_frame)
        button_bar.pack(fill="x", pady=(15, 0))
        button_bar.columnconfigure((0, 1), weight=1)

        ttk.Button(button_bar, text="Speichern & Schließen", command=self.save_and_close).grid(row=0, column=0,
                                                                                               sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def move_item(self, direction):
        selection = self.tab_listbox.curselection()
        if not selection: return
        idx = selection[0]
        new_idx = idx + direction
        if not (0 <= new_idx < self.tab_listbox.size()): return

        item_text = self.tab_listbox.get(idx)
        self.tab_listbox.delete(idx)
        self.tab_listbox.insert(new_idx, item_text)
        self.tab_listbox.selection_set(new_idx)
        self.tab_listbox.activate(new_idx)

    def save_and_close(self):
        new_order = list(self.tab_listbox.get(0, tk.END))
        if TabOrderManager.save_order(new_order):
            messagebox.showinfo("Gespeichert", "Die Reiter-Reihenfolge wurde aktualisiert.", parent=self)
            self.callback(new_order)
            self.destroy()
        else:
            messagebox.showerror("Fehler", "Die Reihenfolge konnte nicht gespeichert werden.", parent=self)