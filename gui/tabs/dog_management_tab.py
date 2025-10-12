# gui/tabs/dog_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

from database.db_dogs import get_all_dogs, add_dog, update_dog, delete_dog, get_dog_handlers, assign_dog
from database.db_users import get_all_users
from gui.dog_edit_window import DogEditWindow


class DogManagementTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding="10")
        self.app = app

        paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned_window.pack(fill="both", expand=True)

        list_frame = ttk.Frame(paned_window, padding="5")
        paned_window.add(list_frame, weight=1)

        columns = ("name", "breed", "age")
        self.dog_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.dog_tree.heading("name", text="Name")
        self.dog_tree.heading("breed", text="Rasse")
        self.dog_tree.heading("age", text="Alter")
        self.dog_tree.column("age", width=60, anchor="center")
        self.dog_tree.pack(fill="both", expand=True)
        self.dog_tree.bind("<<TreeviewSelect>>", self.on_dog_selected)

        dog_buttons = ttk.Frame(list_frame)
        dog_buttons.pack(fill="x", pady=5)
        ttk.Button(dog_buttons, text="Hund anlegen...", command=self.add_new_dog).pack(side="left", padx=5)
        ttk.Button(dog_buttons, text="Bearbeiten...", command=self.open_dog_edit_window).pack(side="left", padx=5)
        ttk.Button(dog_buttons, text="Löschen", command=self.delete_selected_dog).pack(side="left", padx=5)

        self.detail_frame = ttk.LabelFrame(paned_window, text="Details", padding="15")
        paned_window.add(self.detail_frame, weight=2)

        self.dog_detail_vars = {
            "Name": tk.StringVar(), "Rasse": tk.StringVar(), "Geburtsdatum": tk.StringVar(),
            "Alter": tk.StringVar(), "Chipnummer": tk.StringVar(), "Zugang": tk.StringVar(),
            "Abgang": tk.StringVar(), "Letzte DPO": tk.StringVar(), "Impfungen": tk.StringVar(),
            "Hundeführer": tk.StringVar()
        }
        for i, (label_text, var) in enumerate(self.dog_detail_vars.items()):
            ttk.Label(self.detail_frame, text=f"{label_text}:", font=("Segoe UI", 10, "bold")).grid(row=i, column=0,
                                                                                                    sticky="nw", pady=2,
                                                                                                    padx=5)
            ttk.Label(self.detail_frame, textvariable=var, wraplength=400).grid(row=i, column=1, sticky="nw", pady=2,
                                                                                padx=5)

        assign_frame = ttk.LabelFrame(self.detail_frame, text="Hundeführer zuweisen", padding=10)
        assign_frame.grid(row=len(self.dog_detail_vars), column=0, columnspan=2, sticky="ew", pady=10)
        self.user_combobox = ttk.Combobox(assign_frame, state="readonly")
        self.user_combobox.pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(assign_frame, text="Zuweisen", command=self.assign_selected_dog).pack(side="left", padx=5)

        handlers_frame = ttk.LabelFrame(self.detail_frame, text="Aktuelle Hundeführer", padding=10)
        handlers_frame.grid(row=len(self.dog_detail_vars) + 1, column=0, columnspan=2, sticky="ew", pady=5)
        self.dog_handlers_var = tk.StringVar()
        ttk.Label(handlers_frame, textvariable=self.dog_handlers_var, font=("Segoe UI", 10, "italic")).pack(anchor="w")

        self.refresh_dogs_list()
        self.clear_dog_details()

    def refresh_dogs_list(self):
        for item in self.dog_tree.get_children():
            self.dog_tree.delete(item)
        self.app.dog_data_store = get_all_dogs()
        for dog in self.app.dog_data_store:
            age = "Unbekannt"
            if dog.get("birth_date"):
                try:
                    birth_date = datetime.strptime(dog["birth_date"], '%Y-%m-%d').date()
                    age = (date.today() - birth_date).days // 365
                except (ValueError, TypeError):
                    pass
            self.dog_tree.insert("", tk.END, iid=dog['id'], values=(dog['name'], dog['breed'], age))
        self.clear_dog_details()

    def on_dog_selected(self, event=None):
        selection = self.dog_tree.selection()
        if not selection: return
        dog_id = int(selection[0])
        dog_data = next((d for d in self.app.dog_data_store if d['id'] == dog_id), None)
        if not dog_data: return

        for key, var in self.dog_detail_vars.items(): var.set("---")
        age = "Unbekannt"
        if dog_data.get("birth_date"):
            try:
                birth_date = datetime.strptime(dog_data["birth_date"], '%Y-%m-%d').date()
                age = f"{(date.today() - birth_date).days // 365} Jahre"
                self.dog_detail_vars["Geburtsdatum"].set(birth_date.strftime('%d.%m.%Y'))
            except (ValueError, TypeError):
                pass

        self.dog_detail_vars["Name"].set(dog_data.get('name', '---'))
        self.dog_detail_vars["Rasse"].set(dog_data.get('breed', '---'))
        self.dog_detail_vars["Alter"].set(age)
        self.dog_detail_vars["Chipnummer"].set(dog_data.get('chip_number', '---'))

        if dog_data.get('acquisition_date'): self.dog_detail_vars["Zugang"].set(
            datetime.strptime(dog_data['acquisition_date'], '%Y-%m-%d').strftime('%d.%m.%Y'))
        if dog_data.get('departure_date'): self.dog_detail_vars["Abgang"].set(
            datetime.strptime(dog_data['departure_date'], '%Y-%m-%d').strftime('%d.%m.%Y'))
        if dog_data.get('last_dpo_date'): self.dog_detail_vars["Letzte DPO"].set(
            datetime.strptime(dog_data['last_dpo_date'], '%Y-%m-%d').strftime('%d.%m.%Y'))

        self.dog_detail_vars["Impfungen"].set(dog_data.get('vaccination_info', '---'))

        handlers = get_dog_handlers(dog_data['name'])
        self.dog_handlers_var.set(
            ", ".join([f"{h['vorname']} {h['name']}" for h in handlers]) if handlers else "Nicht zugewiesen")

        all_users = get_all_users()
        self.user_combobox['values'] = [f"{user['vorname']} {user['name']}" for user in all_users.values()]

    def clear_dog_details(self):
        for var in self.dog_detail_vars.values(): var.set("")
        self.dog_handlers_var.set("")
        self.user_combobox['values'] = []
        self.user_combobox.set("")

    def add_new_dog(self):
        empty_data = {"name": "", "breed": "", "birth_date": "", "chip_number": "", "acquisition_date": "",
                      "departure_date": "", "last_dpo_date": "", "vaccination_info": ""}
        DogEditWindow(self.app, empty_data, self.save_new_dog_callback, is_new=True)

    def save_new_dog_callback(self, dog_id, new_data):
        if add_dog(new_data):
            messagebox.showinfo("Erfolg", "Diensthund wurde erfolgreich angelegt.", parent=self.app)
            self.refresh_dogs_list()
        else:
            messagebox.showerror("Fehler", "Ein Hund mit diesem Namen oder Chipnummer existiert bereits.",
                                 parent=self.app)

    def open_dog_edit_window(self):
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Hund zum Bearbeiten aus.", parent=self.app)
            return
        dog_id = int(selection[0])
        dog_data = next((d for d in self.app.dog_data_store if d['id'] == dog_id), None)
        if dog_data:
            DogEditWindow(self.app, dog_data, self.save_edit_dog_callback, is_new=False)

    def save_edit_dog_callback(self, dog_id, new_data):
        if update_dog(dog_id, new_data):
            messagebox.showinfo("Erfolg", "Änderungen wurden gespeichert.", parent=self.app)
            self.app.refresh_all_tabs()
        else:
            messagebox.showerror("Fehler", "Speichern fehlgeschlagen. Name oder Chipnummer möglicherweise doppelt.",
                                 parent=self.app)

    def delete_selected_dog(self):
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Hund zum Löschen aus.", parent=self.app)
            return
        dog_id = int(selection[0])
        dog_name = self.dog_tree.item(selection[0])['values'][0]
        if messagebox.askyesno("Bestätigen", f"Möchten Sie den Hund '{dog_name}' wirklich endgültig löschen?",
                               parent=self.app, icon="warning"):
            if delete_dog(dog_id):
                messagebox.showinfo("Erfolg", "Diensthund wurde gelöscht.", parent=self.app)
                self.app.refresh_all_tabs()
            else:
                messagebox.showerror("Fehler", "Der Hund konnte nicht gelöscht werden.", parent=self.app)

    def assign_selected_dog(self):
        selection = self.dog_tree.selection()
        if not selection:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie einen Hund aus.", parent=self.app)
            return
        dog_name = self.dog_tree.item(selection[0])['values'][0]
        selected_user_name = self.user_combobox.get()
        if not selected_user_name:
            messagebox.showwarning("Keine Auswahl",
                                   "Bitte wählen Sie einen Benutzer aus, dem der Hund zugewiesen werden soll.",
                                   parent=self.app)
            return

        all_users = get_all_users()
        user_id_to_assign = next(
            (uid for uid, udata in all_users.items() if f"{udata['vorname']} {udata['name']}" == selected_user_name),
            None)

        if user_id_to_assign:
            if assign_dog(dog_name, user_id_to_assign):
                messagebox.showinfo("Erfolg", f"'{dog_name}' wurde erfolgreich {selected_user_name} zugewiesen.",
                                    parent=self.app)
                self.app.refresh_all_tabs()
                self.on_dog_selected(None)
            else:
                messagebox.showerror("Fehler", "Zuweisung fehlgeschlagen.", parent=self.app)
        else:
            messagebox.showerror("Fehler", "Ausgewählter Benutzer nicht gefunden.", parent=self.app)