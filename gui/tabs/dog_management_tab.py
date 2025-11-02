# gui/tabs/dog_management_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading

# --- NEU (Regel 1): Importe für Bildverarbeitung ---
from PIL import Image, ImageTk
import io

# --- NEU (Regel 1 & 2): Import der neuen DB-Funktionen ---
from database.db_dogs import get_all_dogs, delete_dog, get_dog_details

# KORREKTUR: Importieren des korrekten Edit-Windows
from ..dog_edit_window import DogEditWindow


class DogManagementTab(ttk.Frame):
    def __init__(self, master, admin_window, initial_data_cache=None):
        """
        Konstruktor für den DogManagementTab.
        Akzeptiert optional vorgeladene Daten, um DB-Wartezeiten zu vermeiden (Regel 2).
        """
        super().__init__(master)
        self.admin_window = admin_window

        # Speichert die Rohdaten (entweder aus Cache or DB)
        self.all_dogs_data = []

        # --- NEU (Regel 1): Referenzen für Detailansicht ---
        self.selected_dog_id = None
        self.image_preview = None  # Referenz für Bild-Label
        self.detail_widgets = {}
        self.detail_vars = {}
        # --- ENDE NEU ---

        self._create_widgets()

        # --- INNOVATION (Regel 1 & 2) ---
        # Daten entweder aus dem Cache laden oder (als Fallback) aus der DB holen.
        if initial_data_cache is not None:
            print("[DogMgmtTab] Lade Daten aus initialem Cache.")
            self.all_dogs_data = initial_data_cache
            self._load_dogs_from_cache()  # Daten sortieren und in Liste laden
        else:
            print("[DogMgmtTab] Initialer Cache leer. Lade aus DB (Fallback).")
            self.refresh_data()  # Daten aus DB holen und anzeigen
        # --- ENDE INNOVATION ---

    def _create_widgets(self):
        # --- INNOVATION (Regel 1 & 4): Neues Layout mit PanedWindow ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(top_frame, text="Aktualisieren", command=self.refresh_data).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Diensthund hinzufügen", command=self.add_dog).pack(side="left", padx=5)

        # Geteilte Ansicht (Liste links, Details rechts)
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill="both", expand=True)

        # Linke Seite: Treeview (Liste der Hunde)
        tree_frame = ttk.Frame(paned_window, padding=(0, 0, 10, 0))
        tree_frame.pack(fill="both", expand=True)
        paned_window.add(tree_frame, weight=1)

        self.tree = ttk.Treeview(tree_frame,
                                 columns=("id", "name", "rasse"),
                                 show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Name")
        self.tree.heading("rasse", text="Rasse")
        self.tree.column("id", width=30, stretch=tk.NO)
        self.tree.column("name", width=150)
        self.tree.column("rasse", width=150)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(expand=True, fill="both")

        # Rechte Seite: Detailansicht (Bild und Infos)
        self.details_frame = ttk.Frame(paned_window, padding=(10, 0, 0, 0))
        self.details_frame.pack(fill="both", expand=True)
        paned_window.add(self.details_frame, weight=2)

        self._create_details_view()
        # --- ENDE INNOVATION ---

        # Bindings
        self.tree.bind("<Double-1>", self.edit_dog_dialog)
        self.tree.bind("<Button-3>", self.show_context_menu)
        # --- NEU (Regel 2): Lazy Loading beim Klick ---
        self.tree.bind("<<TreeviewSelect>>", self.on_dog_selected)

        # Kontextmenü
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Bearbeiten", command=self.edit_dog_context)
        self.context_menu.add_command(label="Löschen", command=self.delete_dog_context)

    def _create_details_view(self):
        """(NEU) Erstellt die Widgets für die rechte Detailansicht (Regel 4)."""

        # Bild-Label
        self.image_label = ttk.Label(self.details_frame, text="Bitte einen Hund auswählen",
                                     style="TLabel", relief="solid", anchor="center",
                                     font=("Segoe UI", 12))
        self.image_label.pack(fill="x", expand=False, pady=(0, 10), ipady=100)

        # Info-Frame
        info_frame = ttk.Frame(self.details_frame, padding=10)
        info_frame.pack(fill="x", expand=False)
        info_frame.columnconfigure(1, weight=1)

        # Definition der Felder, die angezeigt werden sollen
        detail_fields = {
            "name": "Name:",
            "breed": "Rasse:",
            "birth_date": "Geburtsdatum:",
            "chip_number": "Chipnummer:",
            "acquisition_date": "Zugang am:",
            "departure_date": "Abgang am:",
            "last_dpo_date": "Letzte DPO:",
            "vaccination_info": "Impf-Info:"
        }

        row = 0
        for key, label in detail_fields.items():
            ttk.Label(info_frame, text=label, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="nw",
                                                                                  padx=(0, 10), pady=3)

            self.detail_vars[key] = tk.StringVar(value="...")
            # 'vaccination_info' bekommt ein Label mit Zeilenumbruch
            if key == "vaccination_info":
                widget = ttk.Label(info_frame, textvariable=self.detail_vars[key], wraplength=300, anchor="nw",
                                   justify="left")
                widget.grid(row=row, column=1, sticky="ew", pady=3, ipady=5)
            else:
                widget = ttk.Label(info_frame, textvariable=self.detail_vars[key], anchor="w")
                widget.grid(row=row, column=1, sticky="ew", pady=3)

            self.detail_widgets[key] = widget
            row += 1

    def _load_dogs_from_cache(self):
        """
        Füllt die Treeview (Liste) mit den Daten aus self.all_dogs_data.
        Greift nicht auf die Datenbank zu (Regel 2).
        """
        for i in self.tree.get_children():
            try:
                self.tree.delete(i)
            except tk.TclError:
                pass

        if not self.all_dogs_data:
            return

        sorted_dogs = sorted(self.all_dogs_data, key=lambda d: d.get('name', '').lower())

        for dog in sorted_dogs:
            # Zeigt nur die wichtigsten Infos in der Liste an
            values = (
                dog['id'],
                dog.get('name', 'N/A'),
                dog.get('breed', 'N/A'),  # 'breed' aus db_dogs.py
            )
            self.tree.insert("", "end", iid=dog['id'], values=values)

    def refresh_data(self, data_cache=None):
        """
        Aktualisiert die Daten. Nimmt optional einen Cache entgegen (Regel 2).
        """
        try:
            if data_cache is not None:
                print("[DogMgmtTab] Refresh aus Cache.")
                self.all_dogs_data = data_cache
            else:
                print("[DogMgmtTab] Refresh aus DB.")
                self.all_dogs_data = get_all_dogs()  # Holt Liste OHNE Bilder

            self._load_dogs_from_cache()  # Füllt die Liste (links)
            self._clear_details_view()  # Leert die Details (rechts)

        except Exception as e:
            messagebox.showerror("Fehler Laden", f"Hundedaten laden fehlgeschlagen:\n{e}", parent=self)
            import traceback;
            traceback.print_exc()

    def on_dog_selected(self, event=None):
        """
        (NEU) Wird aufgerufen, wenn ein Hund in der Liste ausgewählt wird.
        Startet das Lazy Loading für die Details (Regel 2).
        """
        selected_item = self.tree.focus()
        if not selected_item:
            return

        try:
            dog_id = int(selected_item)
            if dog_id == self.selected_dog_id:
                return  # Nicht neuladen, wenn schon ausgewählt

            self.selected_dog_id = dog_id

            # Details zurücksetzen und Lade-Thread starten
            self._clear_details_view(loading=True)
            threading.Thread(target=self._load_dog_details_threaded, args=(dog_id,), daemon=True).start()

        except (ValueError, TypeError):
            self._clear_details_view()

    def _load_dog_details_threaded(self, dog_id):
        """(NEU) Lädt das Bild und die Details im Hintergrund (Regel 2)."""
        try:
            # Ruft die DB-Funktion auf, die den BLOB holt
            full_dog_data = get_dog_details(dog_id)

            if full_dog_data:
                # UI-Update im Main-Thread
                self.after(0, self._display_dog_details, full_dog_data)
            else:
                self.after(0, self._clear_details_view)
        except Exception as e:
            print(f"Fehler beim Laden der Hundedetails: {e}")
            self.after(0, self._clear_details_view)

    def _display_dog_details(self, dog_data):
        """(NEU) Füllt die rechte Detailansicht mit Daten (Regel 4)."""

        # 1. Bild anzeigen
        self.image_blob = dog_data.get('image_blob', None)
        self._display_image()  # Zeigt das Bild oder "Kein Bild"

        # 2. Text-Infos füllen
        for key, var in self.detail_vars.items():
            value = dog_data.get(key, "k.A.")  # Holt Wert aus vollem Datensatz
            if not value:
                value = "k.A."

            # Datumsformate anpassen
            if key in ["birth_date", "acquisition_date", "departure_date", "last_dpo_date"] and value != "k.A.":
                try:
                    # Datumsobjekte aus DB
                    if isinstance(value, (datetime, datetime.date)):
                        value = value.strftime('%d.%m.%Y')
                    # Strings aus DB (Fallback)
                    else:
                        value = datetime.strptime(str(value), '%Y-%m-%d').strftime('%d.%m.%Y')
                except Exception:
                    value = str(value)  # Zeige Rohdatum bei Fehler

            var.set(value)

    def _display_image(self):
        """(NEU) Zeigt das Bild im self.image_blob im Label an."""
        if not self.image_blob:
            self.image_label.config(image=None, text="Kein Bild vorhanden")
            self.image_preview = None
            return

        try:
            image_data = io.BytesIO(self.image_blob)
            img = Image.open(image_data)

            # Bild skalieren, um in den Frame zu passen (Breite 300)
            base_width = 300
            w_percent = (base_width / float(img.size[0]))
            h_size = int((float(img.size[1]) * float(w_percent)))
            img = img.resize((base_width, h_size), Image.Resampling.LANCZOS)

            self.image_preview = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.image_preview, text="")
        except Exception as e:
            print(f"Fehler beim Anzeigen des Bilds: {e}")
            self.image_label.config(image=None, text="Bild-Vorschau fehlgeschlagen")
            self.image_preview = None

    def _clear_details_view(self, loading=False):
        """(NEU) Setzt die Detailansicht zurück."""
        self.selected_dog_id = None
        self.image_blob = None
        self.image_preview = None

        if loading:
            self.image_label.config(image=None, text="Lade Details...")
        else:
            self.image_label.config(image=None, text="Bitte einen Hund auswählen")

        for var in self.detail_vars.values():
            var.set("...")

    def on_dog_saved(self):
        """Wird aufgerufen, nachdem das DogEditWindow gespeichert wurde."""
        # Daten neu laden (Fallback-DB-Aufruf)
        self.refresh_data()

        # UI aktualisieren, falls der bearbeitete Hund noch ausgewählt ist
        selected_item = self.tree.focus()
        if selected_item:
            try:
                self.selected_dog_id = int(selected_item)
                self._clear_details_view(loading=True)
                threading.Thread(target=self._load_dog_details_threaded, args=(self.selected_dog_id,),
                                 daemon=True).start()
            except ValueError:
                self._clear_details_view()

        if hasattr(self.admin_window, 'notification_manager'):
            self.admin_window.notification_manager.check_for_updates()

    def add_dog(self):
        """Öffnet das Edit-Fenster für einen NEUEN Hund."""
        edit_win = DogEditWindow(master=self,
                                 dog_data=None,
                                 callback=self.on_dog_saved,
                                 is_new=True)
        edit_win.grab_set()

    def edit_dog_dialog(self, event=None):
        """Öffnet das Edit-Fenster für den ausgewählten Hund (Doppelklick)."""
        selected_item = self.tree.focus()
        if not selected_item: return
        self._open_edit_window(int(selected_item))

    def edit_dog_context(self):
        """Öffnet das Edit-Fenster für den ausgewählten Hund (Rechtsklick)."""
        if self.selected_dog_id:
            self._open_edit_window(self.selected_dog_id)

    def _open_edit_window(self, dog_id):
        """(KORRIGIERT) Ruft DogEditWindow korrekt auf (Regel 1 & 4)."""
        try:
            # Daten aus dem (schnellen) Listen-Cache holen (Regel 2)
            dog_data_from_list = next((dog for dog in self.all_dogs_data if dog['id'] == dog_id), None)

            if dog_data_from_list:
                edit_win = DogEditWindow(master=self,
                                         dog_data=dog_data_from_list,  # Übergibt das (unvollständige) Dict
                                         callback=self.on_dog_saved,
                                         is_new=False)
                edit_win.grab_set()
            else:
                messagebox.showerror("Fehler", f"Hundedaten für ID {dog_id} nicht im Cache gefunden.", parent=self)
        except ValueError:
            pass

    def show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.selected_dog_id = int(iid)  # ID für Kontextmenü setzen
            self.context_menu.tk_popup(event.x_root, event.y_root)
        else:
            self.selected_dog_id = None

    def delete_dog_context(self):
        """Löscht den Hund (Rechtsklick)."""
        if self.selected_dog_id:
            dog_name = "Unbekannt"
            try:
                # Versuche, den Namen aus der Liste zu holen
                dog_name = self.tree.item(self.selected_dog_id)['values'][1]
            except Exception:
                pass

            if messagebox.askyesno("Löschen",
                                   f"Soll der Diensthund '{dog_name}' (ID: {self.selected_dog_id}) wirklich gelöscht werden?",
                                   parent=self):

                success = delete_dog(self.selected_dog_id)

                if success:
                    messagebox.showinfo("Erfolg", f"Hund '{dog_name}' wurde gelöscht.", parent=self)
                    self.on_dog_saved()  # Lädt die Daten neu
                else:
                    messagebox.showerror("Fehler", f"Hund '{dog_name}' konnte nicht gelöscht werden.", parent=self)