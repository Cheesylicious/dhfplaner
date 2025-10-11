# gui/tabs/password_reset_requests_window.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from database.db_manager import get_pending_password_resets, approve_password_reset, reject_password_reset


class PasswordResetRequestsWindow(tk.Toplevel):
    def __init__(self, master, update_callback):
        super().__init__(master)
        self.title("Passwort-Reset Anfragen")
        self.geometry("500x400")
        self.update_callback = update_callback
        self.transient(master)
        self.grab_set()

        self.create_widgets()
        self.load_requests()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        self.tree = ttk.Treeview(main_frame, columns=("Name", "Zeitstempel"), show="headings")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Zeitstempel", text="Zeitstempel")
        self.tree.pack(expand=True, fill="both", pady=5)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=5)

        approve_button = ttk.Button(button_frame, text="Genehmigen", command=self.approve_request)
        approve_button.pack(side="left")

        reject_button = ttk.Button(button_frame, text="Ablehnen", command=self.reject_request)
        reject_button.pack(side="left", padx=5)

    def load_requests(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.requests = get_pending_password_resets()
        for req in self.requests:
            self.tree.insert("", "end", values=(f"{req['vorname']} {req['name']}", req['timestamp']), iid=req['id'])

    def approve_request(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Fehler", "Bitte wählen Sie eine Anfrage aus.", parent=self)
            return

        request_id = selected_item[0]

        new_password = simpledialog.askstring("Neues Passwort", "Geben Sie ein temporäres Passwort ein:", parent=self)
        if new_password:
            success, message = approve_password_reset(request_id, new_password)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_requests()
                self.update_callback()
            else:
                messagebox.showerror("Fehler", message, parent=self)

    def reject_request(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Fehler", "Bitte wählen Sie eine Anfrage aus.", parent=self)
            return

        request_id = selected_item[0]
        if messagebox.askyesno("Bestätigen", "Möchten Sie diese Anfrage wirklich ablehnen?", parent=self):
            success, message = reject_password_reset(request_id)
            if success:
                messagebox.showinfo("Erfolg", message, parent=self)
                self.load_requests()
                self.update_callback()
            else:
                messagebox.showerror("Fehler", message, parent=self)