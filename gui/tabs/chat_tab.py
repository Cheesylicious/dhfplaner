# gui/tabs/chat_tab.py
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta

from database.db_chat import (get_users_for_chat, get_chat_messages, send_chat_message,
                              get_unread_messages_from_user, update_user_last_seen)

class ChatTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.current_user_id = self.app.user_data['id']
        self.selected_user_id = None
        self.user_list_data = {}

        self.setup_ui()
        self.load_user_list()
        self.after(100, self.periodic_update)

    def setup_ui(self):
        # ... (UI-Code bleibt unverändert)
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)
        user_list_frame = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(user_list_frame, weight=1)
        ttk.Label(user_list_frame, text="Kontakte", font=("Segoe UI", 12, "bold")).pack(pady=(0, 5))
        self.user_tree = ttk.Treeview(user_list_frame, columns=("status", "name"), show="headings", selectmode="browse")
        self.user_tree.heading("status", text="Status")
        self.user_tree.heading("name", text="Name")
        self.user_tree.column("status", width=50, anchor="center")
        self.user_tree.column("name", width=150)
        self.user_tree.pack(fill=tk.BOTH, expand=True)
        self.user_tree.tag_configure('online', foreground='green')
        self.user_tree.tag_configure('offline', foreground='gray')
        self.user_tree.tag_configure('unread', font=('Segoe UI', 10, 'bold'))
        self.user_tree.bind("<<TreeviewSelect>>", self.on_user_select)
        chat_frame = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(chat_frame, weight=4)
        self.chat_header = ttk.Label(chat_frame, text="Wähle einen Kontakt zum Chatten", font=("Segoe UI", 12, "bold"))
        self.chat_header.pack(pady=(0, 10))
        chat_history_frame = ttk.Frame(chat_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True)
        self.chat_history = tk.Text(chat_history_frame, state=tk.DISABLED, wrap=tk.WORD, font=("Segoe UI", 11), bg="#f0f0f0", bd=0, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(chat_history_frame, command=self.chat_history.yview)
        self.chat_history.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat_history.tag_configure("sent", foreground="#007bff", justify='right', rmargin=10)
        self.chat_history.tag_configure("received", foreground="#28a745", justify='left', lmargin1=10, lmargin2=10)
        self.chat_history.tag_configure("timestamp", foreground="gray", font=("Segoe UI", 8), justify='center')
        input_frame = ttk.Frame(chat_frame, padding=(0, 10, 0, 0))
        input_frame.pack(fill=tk.X)
        self.message_entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.message_entry.bind("<Return>", self.send_message)
        self.send_button = ttk.Button(input_frame, text="Senden", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=(10, 0))

    # --- ANFANG DER ÄNDERUNG ---
    def select_user(self, user_id):
        """Wählt einen Benutzer programmgesteuert in der Liste aus."""
        user_id_str = str(user_id)
        if self.user_tree.exists(user_id_str):
            self.user_tree.selection_set(user_id_str)
            self.user_tree.focus(user_id_str)
            self.on_user_select(None) # Manuelles Auslösen des Events
    # --- ENDE DER ÄNDERUNG ---

    def load_user_list(self):
        # ... (Funktion bleibt unverändert)
        self.user_tree.unbind("<<TreeviewSelect>>")
        selected_item_id = self.user_tree.selection()[0] if self.user_tree.selection() else None
        existing_ids = set(self.user_tree.get_children())
        users = get_users_for_chat(self.current_user_id)
        now = datetime.now()
        for user in users:
            user_id_str = str(user['id'])
            full_name = f"{user['vorname']} {user['name']}"
            self.user_list_data[user_id_str] = {'name': full_name, 'last_seen': user['last_seen']}
            status = "Offline"
            if user['last_seen']:
                last_seen_dt = user['last_seen']
                if isinstance(last_seen_dt, str):
                    last_seen_dt = datetime.strptime(last_seen_dt, "%Y-%m-%d %H:%M:%S")
                if now - last_seen_dt < timedelta(minutes=2):
                    status = "Online"
            unread_count = get_unread_messages_from_user(user['id'], self.current_user_id)
            display_name = full_name
            tags = ['online' if status == "Online" else 'offline']
            if unread_count > 0:
                display_name += f" ({unread_count})"
                tags.append('unread')
            if user_id_str in existing_ids:
                self.user_tree.item(user_id_str, values=(status, display_name), tags=tags)
                existing_ids.remove(user_id_str)
            else:
                self.user_tree.insert("", "end", iid=user_id_str, values=(status, display_name), tags=tags)
        for user_id_str in existing_ids:
            self.user_tree.delete(user_id_str)
        if selected_item_id:
            try:
                self.user_tree.selection_set(selected_item_id)
            except tk.TclError:
                pass
        self.user_tree.bind("<<TreeviewSelect>>", self.on_user_select)

    def on_user_select(self, event):
        # ... (Funktion bleibt unverändert)
        selected_item = self.user_tree.selection()
        if not selected_item: return
        self.selected_user_id = int(selected_item[0])
        user_name = self.user_list_data[str(self.selected_user_id)]['name']
        self.chat_header.config(text=f"Chat mit {user_name}")
        self.load_messages()
        try:
            current_values = self.user_tree.item(str(self.selected_user_id), 'values')
            new_name = self.user_list_data[str(self.selected_user_id)]['name']
            self.user_tree.item(str(self.selected_user_id), values=(current_values[0], new_name))
            current_tags = list(self.user_tree.item(str(self.selected_user_id), 'tags'))
            if 'unread' in current_tags:
                current_tags.remove('unread')
                self.user_tree.item(str(self.selected_user_id), tags=tuple(current_tags))
        except tk.TclError:
            pass

    def load_messages(self, scroll_to_end=True):
        # ... (Funktion bleibt unverändert)
        if not self.selected_user_id: return
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        messages = get_chat_messages(self.current_user_id, self.selected_user_id)
        for msg in messages:
            timestamp = msg['timestamp'].strftime("%d.%m.%Y %H:%M")
            tag = "sent" if msg['sender_id'] == self.current_user_id else "received"
            self.chat_history.insert(tk.END, f"{msg['message']}\n", tag)
            self.chat_history.insert(tk.END, f"{timestamp}\n\n", "timestamp")
        self.chat_history.config(state=tk.DISABLED)
        if scroll_to_end:
            self.chat_history.yview(tk.END)

    def send_message(self, event=None):
        # ... (Funktion bleibt unverändert)
        message = self.message_entry.get().strip()
        if message and self.selected_user_id:
            if send_chat_message(self.current_user_id, self.selected_user_id, message):
                self.message_entry.delete(0, tk.END)
                self.load_messages()

    def periodic_update(self):
        # ... (Funktion bleibt unverändert)
        update_user_last_seen(self.current_user_id)
        self.load_user_list()
        if self.selected_user_id:
            self.load_messages(scroll_to_end=False)
        self.after(5000, self.periodic_update)

    def refresh_data(self):
        # ... (Funktion bleibt unverändert)
        self.load_user_list()