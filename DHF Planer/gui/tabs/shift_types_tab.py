# gui/tabs/shift_types_tab.py
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from database.db_manager import (
    get_all_shift_types, add_shift_type, update_shift_type, delete_shift_type
)


class ShiftTypesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.shift_types = {}
        self.selected_shift_id = None
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        list_frame = ttk.LabelFrame(main_frame, text="Vorhandene Schichtarten", padding="10")
        list_frame.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        list_frame.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(list_frame, columns=("name", "abbreviation", "hours"), show="headings")
        self.tree.grid(row=0, column=0, sticky="ns")
        self.tree.heading("name", text="Name")
        self.tree.heading("abbreviation", text="Kürzel")
        self.tree.heading("hours", text="Stunden")
        self.tree.column("name", width=150)
        self.tree.column("abbreviation", width=70)
        self.tree.column("hours", width=70)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.bind("<<TreeviewSelect>>", self.on_shift_type_selected)

        button_frame_left = ttk.Frame(list_frame)
        button_frame_left.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(button_frame_left, text="Neu", command=self.clear_form).pack(side="left", expand=True, fill="x")
        ttk.Button(button_frame_left, text="Löschen", command=self.delete_shift_type).pack(side="right", expand=True,
                                                                                           fill="x")

        edit_frame = ttk.LabelFrame(main_frame, text="Schichtart bearbeiten", padding="15")
        edit_frame.grid(row=0, column=1, sticky="nsew")
        edit_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(edit_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.name_entry = ttk.Entry(edit_frame, width=40)
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(edit_frame, text="Abkürzung:").grid(row=1, column=0, sticky="w", pady=5)
        self.abbreviation_entry = ttk.Entry(edit_frame, width=40)
        self.abbreviation_entry.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(edit_frame, text="Stunden:").grid(row=2, column=0, sticky="w", pady=5)
        self.hours_spinbox = ttk.Spinbox(edit_frame, from_=0, to=24, increment=0.5, width=38)
        self.hours_spinbox.grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(edit_frame, text="Startzeit (HH:MM):").grid(row=3, column=0, sticky="w", pady=5)
        self.start_time_entry = ttk.Entry(edit_frame, width=40)
        self.start_time_entry.grid(row=3, column=1, sticky="ew", pady=5)

        ttk.Label(edit_frame, text="Endzeit (HH:MM):").grid(row=4, column=0, sticky="w", pady=5)
        self.end_time_entry = ttk.Entry(edit_frame, width=40)
        self.end_time_entry.grid(row=4, column=1, sticky="ew", pady=5)

        ttk.Label(edit_frame, text="Beschreibung:").grid(row=5, column=0, sticky="nw", pady=5)
        self.description_text = tk.Text(edit_frame, height=5, width=40, relief="solid", borderwidth=1)
        self.description_text.grid(row=5, column=1, sticky="ew", pady=5)

        ttk.Label(edit_frame, text="Farbe:").grid(row=6, column=0, sticky="w", pady=5)
        color_frame = ttk.Frame(edit_frame)
        color_frame.grid(row=6, column=1, sticky="ew", pady=5)
        self.color_preview = tk.Label(color_frame, text="      ", bg="#FFFFFF", relief="solid", borderwidth=1)
        self.color_preview.pack(side="left")
        ttk.Button(color_frame, text="Farbe wählen", command=self.choose_color).pack(side="left", padx=10)
        self.hex_color_var = tk.StringVar(value="#FFFFFF")

        save_button = ttk.Button(edit_frame, text="Speichern", command=self.save_shift_type)
        save_button.grid(row=7, column=0, columnspan=2, pady=20, ipady=5, sticky="ew")

    def refresh_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.shift_types = {st['id']: st for st in get_all_shift_types()}

        for shift_id, data in self.shift_types.items():
            self.tree.insert("", tk.END, iid=shift_id, values=(data['name'], data['abbreviation'], data['hours']))

    def on_shift_type_selected(self, event):
        selection = self.tree.selection()
        if not selection:
            return

        self.selected_shift_id = int(selection[0])
        shift_data = self.shift_types.get(self.selected_shift_id)

        if shift_data:
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, shift_data.get('name', ''))
            self.abbreviation_entry.delete(0, tk.END)
            self.abbreviation_entry.insert(0, shift_data.get('abbreviation', ''))
            self.hours_spinbox.set(shift_data.get('hours', 0))

            # --- KORREKTUR HIER ---
            self.start_time_entry.delete(0, tk.END)
            start_time = shift_data.get('start_time')
            if start_time is not None:
                self.start_time_entry.insert(0, start_time)

            self.end_time_entry.delete(0, tk.END)
            end_time = shift_data.get('end_time')
            if end_time is not None:
                self.end_time_entry.insert(0, end_time)
            # --- ENDE DER KORREKTUR ---

            self.description_text.delete("1.0", tk.END)
            self.description_text.insert("1.0", shift_data.get('description', ''))

            color = shift_data.get('color', '#FFFFFF')
            self.hex_color_var.set(color)
            self.color_preview.config(bg=color)

    def choose_color(self):
        color_code = colorchooser.askcolor(title="Farbe wählen", initialcolor=self.hex_color_var.get())
        if color_code and color_code[1]:
            self.hex_color_var.set(color_code[1])
            self.color_preview.config(bg=color_code[1])

    def clear_form(self):
        self.selected_shift_id = None
        self.tree.selection_set()
        self.name_entry.delete(0, tk.END)
        self.abbreviation_entry.delete(0, tk.END)
        self.hours_spinbox.set(0)
        self.start_time_entry.delete(0, tk.END)
        self.end_time_entry.delete(0, tk.END)
        self.description_text.delete("1.0", tk.END)
        self.hex_color_var.set("#FFFFFF")
        self.color_preview.config(bg="#FFFFFF")

    def save_shift_type(self):
        data = {
            "name": self.name_entry.get(),
            "abbreviation": self.abbreviation_entry.get(),
            "hours": float(self.hours_spinbox.get()),
            "description": self.description_text.get("1.0", tk.END).strip(),
            "color": self.hex_color_var.get(),
            "start_time": self.start_time_entry.get() or None,
            "end_time": self.end_time_entry.get() or None,
        }

        if not data["name"] or not data["abbreviation"]:
            messagebox.showerror("Fehler", "Name und Abkürzung dürfen nicht leer sein.", parent=self)
            return

        if self.selected_shift_id:
            success, message = update_shift_type(self.selected_shift_id, data)
        else:
            success, message = add_shift_type(data)

        if success:
            messagebox.showinfo("Erfolg", message, parent=self)
            self.refresh_data()
            self.clear_form()
            self.app.refresh_all_tabs()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    def delete_shift_type(self):
        if not self.selected_shift_id:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Schichtart zum Löschen aus.", parent=self)
            return

        if messagebox.askyesno("Bestätigen", "Möchten Sie diese Schichtart wirklich endgültig löschen?", parent=self):
            success, message = delete_shift_type(self.selected_shift_id)
            if success:
                messagebox.showinfo("Gelöscht", message, parent=self)
                self.refresh_data()
                self.clear_form()
                self.app.refresh_all_tabs()
            else:
                messagebox.showerror("Fehler", message, parent=self)