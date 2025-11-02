# gui/dog_edit_window.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from tkcalendar import DateEntry
import threading

# --- NEU (Regel 1): Importe für Bildverarbeitung ---
from PIL import Image, ImageTk
import io

# --- NEU (Regel 1 & 2): Import der neuen DB-Funktion ---
from database.db_dogs import add_dog, update_dog, get_dog_details


class DogEditWindow(tk.Toplevel):
    def __init__(self, master, dog_data, callback, is_new):
        super().__init__(master)
        self.dog_data = dog_data if dog_data else {}  # Sicherstellen, dass es ein Diktat ist
        self.callback = callback
        self.is_new = is_new

        # --- NEU (Regel 1): BLOB-Daten-Container ---
        self.image_blob = None
        self.image_preview = None  # Referenz für Bild-Label

        self.title(
            "Neuen Diensthund anlegen" if self.is_new else f"Diensthund bearbeiten: {self.dog_data.get('name', '')}")
        # --- KORREKTUR (Regel 1): Fenster vergrößert für Bild ---
        self.geometry("450x650")
        # --- ENDE KORREKTUR ---

        self.transient(master)
        self.grab_set()

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("TEntry", fieldbackground="white", foreground="black", font=("Segoe UI", 10))

        self.vars = {}
        self.widgets = {}
        row_index = 0

        # --- Felder-Definition (Keine 'status' oder 'geschlecht' in db_dogs.py, daher entfernt) ---
        fields = {
            "Name:": "name", "Rasse:": "breed", "Chipnummer:": "chip_number",
            "Geburtsdatum:": "birth_date", "Zugang (Datum):": "acquisition_date", "Abgang (Datum):": "departure_date",
            "Letzte DPO:": "last_dpo_date", "Impf-Info (Text):": "vaccination_info"
        }

        for label_text, key in fields.items():
            ttk.Label(main_frame, text=label_text).grid(row=row_index, column=0, sticky="w", pady=5, padx=(0, 10))

            if key in ["birth_date", "acquisition_date", "departure_date", "last_dpo_date"]:
                date_val = None
                try:
                    date_str = self.dog_data.get(key)
                    if isinstance(date_str, datetime):
                        date_val = date_str.date()
                    elif isinstance(date_str, str):
                        date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
                widget = DateEntry(main_frame, date_pattern='dd.mm.yyyy', date=date_val, foreground="black",
                                   headersforeground="black")
                self.widgets[key] = widget
            else:
                self.vars[key] = tk.StringVar(value=self.dog_data.get(key, ""))
                widget = ttk.Entry(main_frame, textvariable=self.vars[key])

            widget.grid(row=row_index, column=1, sticky="ew", pady=5, ipady=2)
            row_index += 1

        # --- NEU (Regel 1 & 4): Bild-Upload-Bereich ---
        ttk.Label(main_frame, text="Bild:").grid(row=row_index, column=0, sticky="nw", pady=(15, 5), padx=(0, 10))

        image_frame = ttk.Frame(main_frame)
        image_frame.grid(row=row_index, column=1, sticky="ew", pady=(10, 0))
        image_frame.columnconfigure(0, weight=1)

        self.image_label = ttk.Label(image_frame, text="Kein Bild geladen", style="TLabel", relief="solid",
                                     anchor="center", padding=5)
        self.image_label.grid(row=0, column=0, sticky="ew", columnspan=2, ipady=40)

        self.select_button = ttk.Button(image_frame, text="Bild auswählen...", command=self._select_image)
        self.select_button.grid(row=1, column=0, sticky="ew", pady=(5, 0), padx=(0, 2))

        self.remove_button = ttk.Button(image_frame, text="Bild entfernen", command=self._remove_image)
        self.remove_button.grid(row=1, column=1, sticky="ew", pady=(5, 0), padx=(2, 0))

        row_index += 1
        # --- ENDE NEU ---

        button_bar = ttk.Frame(main_frame)
        button_bar.grid(row=row_index, column=0, columnspan=2, pady=(20, 0), sticky="ew")
        button_bar.columnconfigure((0, 1), weight=1)
        ttk.Button(button_bar, text="Speichern", command=self.save).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_bar, text="Abbrechen", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        # --- NEU (Regel 2): Bild asynchron laden ---
        if not self.is_new and self.dog_data.get('id'):
            self.image_label.config(text="Lade Bild...")
            threading.Thread(target=self._load_dog_image_threaded, daemon=True).start()

    def _load_dog_image_threaded(self):
        """(NEU) Lädt das Bild im Hintergrund (Regel 2)."""
        try:
            dog_id = self.dog_data['id']
            # Ruft die neue DB-Funktion auf, die den BLOB holt
            full_dog_data = get_dog_details(dog_id)

            if full_dog_data and full_dog_data.get('image_blob'):
                self.image_blob = full_dog_data['image_blob']
                # UI-Update im Main-Thread
                self.after(0, self._display_image)
            else:
                self.after(0, self.image_label.config, {"text": "Kein Bild vorhanden"})
        except Exception as e:
            print(f"Fehler beim Laden des Hundebilds: {e}")
            self.after(0, self.image_label.config, {"text": "Fehler beim Laden"})

    def _display_image(self):
        """(NEU) Zeigt das Bild im self.image_blob im Label an."""
        if not self.image_blob:
            self.image_label.config(image=None, text="Kein Bild")
            self.image_preview = None
            return

        try:
            image_data = io.BytesIO(self.image_blob)
            img = Image.open(image_data)

            # Bild skalieren, damit es ins Fenster passt (z.B. max 200px Breite)
            base_width = 200
            w_percent = (base_width / float(img.size[0]))
            h_size = int((float(img.size[1]) * float(w_percent)))
            img = img.resize((base_width, h_size), Image.Resampling.LANCZOS)

            self.image_preview = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.image_preview, text="")
        except Exception as e:
            print(f"Fehler beim Anzeigen des Bilds: {e}")
            self.image_label.config(image=None, text="Bild-Vorschau fehlgeschlagen")
            self.image_preview = None

    def _select_image(self):
        """(NEU) Öffnet Dateidialog zum Auswählen eines Bildes."""
        file_path = filedialog.askopenfilename(
            title="Bild auswählen",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif")]
        )
        if not file_path:
            return

        try:
            # Bild auf max. Größe prüfen (z.B. 16MB für MEDIUMBLOB)
            import os
            if os.path.getsize(file_path) > 16 * 1024 * 1024:
                messagebox.showerror("Fehler", "Datei ist zu groß (Max. 16 MB).", parent=self)
                return

            with open(file_path, "rb") as f:
                self.image_blob = f.read()

            # Zeige Vorschau
            self._display_image()

        except Exception as e:
            messagebox.showerror("Fehler", f"Bild konnte nicht geladen werden:\n{e}", parent=self)
            self.image_blob = None

    def _remove_image(self):
        """(NEU) Entfernt das Bild (setzt BLOB auf None)."""
        self.image_blob = None
        self._display_image()
        self.image_label.config(text="Bild entfernt")

    def save(self):
        updated_data = {key: var.get().strip() for key, var in self.vars.items()}

        for key, widget in self.widgets.items():
            date_obj = widget.get_date()
            updated_data[key] = date_obj.strftime('%Y-%m-%d') if date_obj else None

        # --- NEU (Regel 1): Bild-BLOB zu den Daten hinzufügen ---
        updated_data['image_blob'] = self.image_blob
        # --- ENDE NEU ---

        if not updated_data.get('name'):
            messagebox.showerror("Fehler", "Name ist ein Pflichtfeld.", parent=self)
            return

        try:
            if self.is_new:
                success = add_dog(updated_data)  # [aus db_dogs.py]
            else:
                success = update_dog(self.dog_data['id'], updated_data)  # [aus db_dogs.py]

            if success:
                messagebox.showinfo("Erfolg", "Hundedaten erfolgreich gespeichert.", parent=self)
                if self.callback:
                    self.callback()
                self.destroy()
            else:
                messagebox.showerror("Datenbankfehler", "Name oder Chipnummer bereits vergeben.", parent=self)
        except Exception as e:
            messagebox.showerror("Fehler", f"Speichern fehlgeschlagen:\n{e}", parent=self)