# gui/dialogs/user_order_window.py
import tkinter as tk
from tkinter import ttk, messagebox
# NEU: datetime wird benötigt, falls for_date=None als Fallback genutzt wird
from datetime import datetime
from database.db_users import get_ordered_users_for_schedule, save_user_order


class UserOrderWindow(tk.Toplevel):
    """
    Fenster zur Verwaltung der globalen Benutzerreihenfolge und Sichtbarkeit
    im Schichtplan.
    """

    # --- ÄNDERUNG: 'for_date' als Argument hinzugefügt ---
    def __init__(self, master, callback, for_date):
        super().__init__(master)
        self.master = master
        self.callback = callback

        # NEU: Das Datum speichern, für das die Sortierung gilt.
        # 'for_date' sollte der Start des Monats sein.
        self.for_date = for_date

        if self.for_date is None:
            # Fallback, falls None übergeben wird (sollte nicht passieren)
            self.for_date = datetime.now()

        self.users = []
        self.user_vars = {}
        self.drag_data = {"index": 0, "y": 0}

        self.title("Mitarbeiter-Sortierung & Sichtbarkeit")
        self.geometry("500x700")
        self.transient(master)
        self.grab_set()

        self.setup_ui()
        self.load_users()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        ttk.Label(main_frame,
                  text="Sortieren (Drag & Drop) und Sichtbarkeit im Plan festlegen.\n"
                       "Unsichtbare Mitarbeiter erscheinen nicht im Schichtplan.",
                  justify="center").grid(row=0, column=0, columnspan=2, pady=(5, 10))

        # Canvas und Scrollbar für die ListBox
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.grid(row=1, column=0, sticky="nsew", columnspan=2)
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Frame IN die Canvas, das die ListBox enthält
        self.list_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")

        self.list_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # Die ListBox (als tk.Listbox für Drag & Drop und Farbkontrolle)
        self.list_box = tk.Listbox(self.list_frame, font=("Segoe UI", 11), selectmode="single", width=40, height=20)
        self.list_box.pack(side=tk.LEFT, fill=tk.Y, expand=True)

        # Frame für die Checkboxen
        self.check_frame = ttk.Frame(self.list_frame)
        self.check_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        btn_frame.columnconfigure((0, 1), weight=1)

        ttk.Button(btn_frame, text="Speichern", command=self.save_order, style="Success.TButton").grid(row=0, column=0,
                                                                                                       padx=5,
                                                                                                       sticky="ew")
        ttk.Button(btn_frame, text="Abbrechen", command=self.destroy).grid(row=0, column=1, padx=5, sticky="ew")

        # Drag & Drop Bindings
        self.list_box.bind("<Button-1>", self.on_press)
        self.list_box.bind("<B1-Motion>", self.on_drag)
        self.list_box.bind("<ButtonRelease-1>", self.on_release)

    def load_users(self):
        """Lädt die Benutzerliste basierend auf dem `self.for_date`."""
        # Alte Checkboxen zerstören, falls vorhanden
        for widget in self.check_frame.winfo_children():
            widget.destroy()

        self.list_box.delete(0, tk.END)

        try:
            # --- HIER IST DIE WICHTIGE ÄNDERUNG ---
            # Ruft die Benutzer ab, die für den spezifischen Monat (self.for_date)
            # relevant sind (aktiviert und noch nicht archiviert).
            # include_hidden=True, damit wir auch die "unsichtbaren" sehen und bearbeiten können.
            users = get_ordered_users_for_schedule(include_hidden=True, for_date=self.for_date)
            # --- ENDE ÄNDERUNG ---
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Benutzer: {e}", parent=self)
            return

        self.users = users
        self.user_vars = {}

        if not self.users:
            ttk.Label(self.check_frame, text="Keine Benutzer für diesen Zeitraum gefunden.").pack()
            return

        for user in self.users:
            name = f"{user['vorname']} {user['name']}"
            self.list_box.insert(tk.END, name)

            # Sichtbarkeits-Status
            is_visible = user.get('is_visible', 1) == 1
            var = tk.BooleanVar(value=is_visible)
            self.user_vars[user['id']] = var

            # Checkbox erstellen
            cb = ttk.Checkbutton(self.check_frame, text="Sichtbar", variable=var,
                                 style="Switch.TCheckbutton")
            cb.pack(anchor="w", pady=5, ipady=1)

            # Mitarbeiter ausgrauen, die nicht sichtbar sind
            if not is_visible:
                self.list_box.itemconfig(tk.END, {'fg': 'grey'})

    def save_order(self):
        """Speichert die neue Reihenfolge UND den Sichtbarkeitsstatus."""
        # Erstellt eine Liste von Dictionaries im Format, das save_user_order erwartet
        ordered_user_info = []

        # self.users muss die sortierte Liste sein (wird durch Drag & Drop aktualisiert)
        for user in self.users:
            user_id = user['id']
            is_visible = self.user_vars[user_id].get()

            ordered_user_info.append({
                'id': user_id,
                'is_visible': 1 if is_visible else 0
            })

        success, message = save_user_order(ordered_user_info)

        if success:
            messagebox.showinfo("Gespeichert", message, parent=self)
            if self.callback:
                self.callback()  # Ruft den spezifischen Reload-Callback auf
            self.destroy()
        else:
            messagebox.showerror("Fehler", message, parent=self)

    # --- Drag & Drop Methoden (on_press, on_drag, on_release) ---
    # (Diese bleiben unverändert, da sie nur die lokale 'self.users' Liste manipulieren)

    def on_press(self, event):
        try:
            index = self.list_box.nearest(event.y)
            self.list_box.selection_clear(0, tk.END)
            self.list_box.selection_set(index)
            self.list_box.activate(index)
            self.drag_data["index"] = index
            self.drag_data["y"] = event.y
        except Exception as e:
            print(f"Fehler bei on_press: {e}")

    def on_drag(self, event):
        try:
            new_index = self.list_box.nearest(event.y)
            if new_index != self.drag_data["index"]:
                # Bewege das Item in der Listbox
                item_text = self.list_box.get(self.drag_data["index"])
                self.list_box.delete(self.drag_data["index"])
                self.list_box.insert(new_index, item_text)

                # Aktualisiere die selection und den active state
                self.list_box.selection_clear(0, tk.END)
                self.list_box.selection_set(new_index)
                self.list_box.activate(new_index)

                # Aktualisiere die zugrundeliegende self.users Liste
                moved_user = self.users.pop(self.drag_data["index"])
                self.users.insert(new_index, moved_user)

                # Aktualisiere die Checkboxen (langsamer, aber notwendig)
                self.update_checkbox_order()

                self.drag_data["index"] = new_index
        except Exception as e:
            print(f"Fehler bei on_drag: {e}")

    def on_release(self, event):
        self.drag_data = {"index": 0, "y": 0}
        # Aktualisiere die Farben basierend auf der neuen Checkbox-Reihenfolge
        self.update_listbox_colors()

    def update_checkbox_order(self):
        """Ordnet die Checkboxen entsprechend der self.users Liste neu an."""
        # Alle Checkboxen aus dem Frame entfernen
        for widget in self.check_frame.winfo_children():
            widget.pack_forget()

        # Checkboxen in der neuen Reihenfolge (basierend auf self.users) wieder hinzufügen
        for user in self.users:
            user_id = user['id']
            var = self.user_vars[user_id]

            # Finde die Checkbox, die zu dieser Variable gehört
            # (Dieser Weg ist robust, falls die Widgets nicht einfach neu erstellt werden)
            for child in self.check_frame.winfo_children():
                if child.cget("variable") == str(var):
                    child.pack(anchor="w", pady=5, ipady=1)
                    break
            else:
                # Fallback: Widget neu erstellen (sollte nicht passieren, wenn load_users korrekt war)
                cb = ttk.Checkbutton(self.check_frame, text="Sichtbar", variable=var,
                                     style="Switch.TCheckbutton")
                cb.pack(anchor="w", pady=5, ipady=1)

    def update_listbox_colors(self):
        """Aktualisiert die Listbox-Farben basierend auf dem Sichtbarkeitsstatus."""
        for i, user in enumerate(self.users):
            user_id = user['id']
            if not self.user_vars[user_id].get():
                self.list_box.itemconfig(i, {'fg': 'grey'})
            else:
                self.list_box.itemconfig(i, {'fg': 'black'})