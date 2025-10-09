# gui/dialogs/tutorial_window.py
import tkinter as tk
from tkinter import ttk


class TutorialWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Willkommen beim DHF Planer! - Tutorial")
        self.geometry("600x400")

        self.steps = [
            {
                "title": "Willkommen!",
                "text": "Dieses kurze Tutorial führt dich durch die wichtigsten Funktionen, die dir als Benutzer zur Verfügung stehen.\n\nKlicke auf 'Weiter', um zu beginnen."
            },
            {
                "title": "1. Der Schichtplan",
                "text": "Im Reiter 'Schichtplan' siehst du den aktuellen Dienstplan.\n\n"
                        "Deine eigene Zeile ist fett markiert. Du kannst auf eine Zelle in deiner Zeile klicken, um einen Wunsch (z.B. 'Wunschfrei' oder eine Wunschschicht) für diesen Tag zu äußern oder einen bestehenden Wunsch zu ändern/zurückzuziehen."
            },
            {
                "title": "2. Meine Anfragen",
                "text": "Im Reiter 'Meine Anfragen' findest du eine Übersicht aller deiner gestellten Wünsche ('Wunschfrei' und Wunschdienste).\n\n"
                        "Hier siehst du den Status (Ausstehend, Genehmigt, Abgelehnt) und kannst ausstehende Wünsche auch wieder zurückziehen."
            },
            {
                "title": "3. Mein Urlaub",
                "text": "Der Reiter 'Mein Urlaub' ist für die Urlaubsplanung.\n\n"
                        "Hier kannst du einen neuen Urlaubsantrag für einen Zeitraum stellen und siehst eine Liste deiner bisherigen Anträge und deren Status."
            },
            {
                "title": "4. Die Fußleiste",
                "text": "Ganz unten im Fenster findest du zwei wichtige Buttons:\n\n"
                        "- 'Abmelden' (gelb): Loggt dich aus und bringt dich zurück zum Login-Bildschirm.\n"
                        "- 'Bug / Fehler melden' (blau): Öffnet ein Fenster, in dem du Fehler oder Probleme direkt an den Admin melden kannst."
            },
            {
                "title": "5. Sonstiges",
                "text": "Ganz oben rechts im Fenster findest du den Button 'Reiter anpassen'. Damit kannst du die Reihenfolge der Tabs nach deinen Wünschen sortieren.\n\n"
                        "Dieses Tutorial kannst du jederzeit über den 'Tutorial'-Button (oben links) erneut aufrufen.\n\nViel Spaß bei der Nutzung!"
            }
        ]
        self.current_step = 0

        self.setup_ui()
        self.show_step()

        self.wait_window(self)

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        self.title_label = ttk.Label(main_frame, text="", font=("Segoe UI", 16, "bold"))
        self.title_label.pack(pady=(0, 15))

        self.text_label = ttk.Label(main_frame, text="", wraplength=550, justify="left", font=("Segoe UI", 11))
        self.text_label.pack(expand=True, fill="both")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", side="bottom", pady=(15, 0))

        self.prev_button = ttk.Button(button_frame, text="Zurück", command=self.prev_step)
        self.prev_button.pack(side="left")

        self.next_button = ttk.Button(button_frame, text="Weiter", command=self.next_step)
        self.next_button.pack(side="right")

        self.skip_button = ttk.Button(button_frame, text="Überspringen / Schließen", command=self.destroy)
        self.skip_button.pack(side="right", padx=10)

    def show_step(self):
        step_data = self.steps[self.current_step]
        self.title_label.config(text=step_data["title"])
        self.text_label.config(text=step_data["text"])

        # Buttons anpassen
        if self.current_step == 0:
            self.prev_button.config(state="disabled")
        else:
            self.prev_button.config(state="normal")

        if self.current_step == len(self.steps) - 1:
            self.next_button.config(state="disabled")
        else:
            self.next_button.config(state="normal")

    def next_step(self):
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self.show_step()

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.show_step()