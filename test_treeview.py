# test_treeview.py
import tkinter as tk
from tkinter import ttk

# Die Logik ist genau die gleiche wie in deinem Admin-Fenster
all_columns = {'vorname': 'Vorname', 'name': 'Name', 'role': 'Rolle'}
visible_columns = ('vorname', 'name')

root = tk.Tk()
root.title("Treeview Test")
root.geometry("400x200")

# --- Die entscheidende Reihenfolge ---
# 1. Treeview "nackt" erstellen
tree = ttk.Treeview(root, show="headings")

# 2. Alle möglichen Spalten-Identifier zuweisen
tree["columns"] = list(all_columns.keys())

# 3. Jede Spalte einzeln konfigurieren
for key, text in all_columns.items():
    tree.heading(key, text=text)

# 4. Erst jetzt die sichtbaren Spalten festlegen
tree["displaycolumns"] = visible_columns
# --- Ende der Logik ---

tree.pack(fill="both", expand=True)
root.mainloop()