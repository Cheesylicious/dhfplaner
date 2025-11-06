import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
# Hier ist die Änderung: db_manager wurde zu db_admin
from database.db_admin import get_pending_password_resets, approve_password_reset, reject_password_reset


# --- KORREKTUR (Fehlerbehebung): Geerbt von ttk.Frame statt tk.Toplevel (Regel 1) ---
class PasswordResetRequestsWindow(ttk.Frame):
    # --- KORREKTUR (Fehlerbehebung): 'admin_window' als drittes Argument hinzugefügt (Regel 1) ---
    def __init__(self, parent, admin_window):
        # 'parent' ist jetzt das ttk.Notebook
        super().__init__(parent)

        # --- NEU (Regel 1 & 2): Referenz auf Admin-Daten speichern ---
        self.admin_window = admin_window
        # Speichert die ID des Admins, der diese Aktionen ausführt (für Logging)
        self.admin_user_id = admin_window.user_data['id']
        # --- ENDE NEU ---

        # (Diese Zeilen werden für ein Frame nicht benötigt)
        # self.title("Ausstehende Passwort-Resets")
        # self.geometry("600x400")

        self.create_widgets()
        self.load_requests()

    def create_widgets(self):
        # 'self' ist jetzt der Frame, der in das Notebook eingefügt wird
        self.tree = ttk.Treeview(self, columns=("ID", "Name", "Zeitstempel"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Zeitstempel", text="Zeitstempel")
        self.tree.pack(expand=True, fill="both", padx=10, pady=10)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=5)

        approve_button = ttk.Button(button_frame, text="Genehmigen", command=self.approve_selected)
        approve_button.pack(side="left", padx=5)

        reject_button = ttk.Button(button_frame, text="Ablehnen", command=self.reject_selected)
        reject_button.pack(side="left", padx=5)

    def load_requests(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        requests = get_pending_password_resets()
        for req in requests:
            self.tree.insert("", "end", values=(req['id'], f"{req['vorname']} {req['name']}", req['timestamp']))

    def approve_selected(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Anfrage aus.")
            return

        request_id = self.tree.item(selected_item, "values")[0]
        # Wichtig: parent=self (der Frame) statt parent=self.admin_window
        new_password = simpledialog.askstring("Neues Passwort", "Bitte geben Sie ein neues temporäres Passwort ein:",
                                              show='*', parent=self)

        if new_password:
            # --- KORREKTUR (Regel 1 & 2): self.admin_user_id hinzugefügt ---
            success, message = approve_password_reset(request_id, new_password, self.admin_user_id)
            # --- ENDE KORREKTUR ---

            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_requests()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def reject_selected(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Keine Auswahl", "Bitte wählen Sie eine Anfrage aus.")
            return

        request_id = self.tree.item(selected_item, "values")[0]
        if messagebox.askyesno("Bestätigen", "Möchten Sie diese Anfrage wirklich ablehnen?", parent=self):

            # --- KORREKTUR (Regel 1 & 2): self.admin_user_id hinzugefügt ---
            success, message = reject_password_reset(request_id, self.admin_user_id)
            # --- ENDE KORREKTUR ---

            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_requests()
            else:
                messagebox.showerror("Fehler", message, parent=self)