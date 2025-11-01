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

        # --- NEU: ThreadManager und Loop-Steuerung ---
        self.thread_manager = self.app.thread_manager
        self.periodic_update_active = False
        # --------------------------------------------

        self.setup_ui()

        self.load_user_list_threaded()

        self.after(100, self.start_periodic_update)

        self.bind("<Destroy>", self.on_destroy)

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
        self.chat_history = tk.Text(chat_history_frame, state=tk.DISABLED, wrap=tk.WORD, font=("Segoe UI", 11),
                                    bg="#f0f0f0", bd=0, padx=10, pady=10)
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

    def select_user(self, user_id):
        """Wählt einen Benutzer programmgesteuert in der Liste aus."""
        user_id_str = str(user_id)
        if self.user_tree.exists(user_id_str):
            self.user_tree.selection_set(user_id_str)
            self.user_tree.focus(user_id_str)
            self.on_user_select(None)

    def on_destroy(self, event):
        """Wird aufgerufen, wenn der Tab zerstört wird."""
        if event.widget == self:
            self.stop_periodic_update()

    def start_periodic_update(self):
        """Startet die periodische Update-Schleife, falls sie nicht schon läuft."""
        if self.periodic_update_active:
            return
        print("[ChatTab] Starte periodische Update-Schleife.")
        self.periodic_update_active = True
        self.periodic_update_threaded()

    def stop_periodic_update(self):
        """Stoppt die periodische Update-Schleife."""
        print("[ChatTab] Stoppe periodische Update-Schleife.")
        self.periodic_update_active = False

    def periodic_update_threaded(self):
        """
        [LÄUFT IM GUI-THREAD]
        Startet den Worker-Thread für die Chat-Daten.
        """
        if not self.periodic_update_active or not self.winfo_exists():
            self.periodic_update_active = False
            return

        print("[ChatTab] periodic_update_threaded: Starte Worker...")
        selected_user_id_at_start = self.selected_user_id

        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self._fetch_chat_data,
            self._on_chat_data_fetched,
            self.current_user_id,
            selected_user_id_at_start
        )
        # -----------------------------------

    def _fetch_chat_data(self, current_user_id, selected_user_id):
        """
        [LÄUFT IM THREAD]
        Führt ALLE blockierenden DB-Abfragen für den Chat-Tab aus.
        """
        try:
            update_user_last_seen(current_user_id)

            users = get_users_for_chat(current_user_id)
            user_data_with_unread = []
            for user in users:
                unread_count = get_unread_messages_from_user(user['id'], current_user_id)
                user['unread_count'] = unread_count
                user_data_with_unread.append(user)

            messages = None
            if selected_user_id:
                messages = get_chat_messages(current_user_id, selected_user_id)

            return {
                "users": user_data_with_unread,
                "messages": messages,
                "selected_user_id_at_start": selected_user_id
            }
        except Exception as e:
            print(f"[FEHLER] _fetch_chat_data (Thread): {e}")
            return e

    def _on_chat_data_fetched(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback-Funktion, die die Chat-UI mit den Daten aus dem Thread aktualisiert.
        """
        if not self.periodic_update_active or not self.winfo_exists():
            self.periodic_update_active = False
            return

        if error:
            print(f"[FEHLER] _on_chat_data_fetched: {error}")
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_chat_data_fetched (von Thread): {result}")
        elif result:
            self._update_user_list_ui(result.get("users"))

            selected_user_id_at_start = result.get("selected_user_id_at_start")
            if selected_user_id_at_start is not None and selected_user_id_at_start == self.selected_user_id:
                self._update_messages_ui(result.get("messages"), scroll_to_end=False)

        self.after(5000, self.periodic_update_threaded)

    def on_user_select(self, event):
        """
        [LÄUFT IM GUI-THREAD]
        Wird aufgerufen, wenn ein Benutzer interaktiv ausgewählt wird.
        """
        selected_item = self.user_tree.selection()
        if not selected_item:
            return

        self.selected_user_id = int(selected_item[0])
        user_name = self.user_list_data.get(str(self.selected_user_id), {}).get('name', 'Unbekannt')
        self.chat_header.config(text=f"Chat mit {user_name}")

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

        self.load_messages_threaded(self.current_user_id, self.selected_user_id)

    def load_messages_threaded(self, current_user_id, selected_user_id):
        """[GUI-Thread] Startet Worker, um Nachrichten für Klick zu laden."""
        print(f"[ChatTab] Lade Nachrichten für User {selected_user_id} (interaktiv)...")
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.insert("1.0", "Lade Nachrichten...")
        self.chat_history.config(state=tk.DISABLED)

        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            get_chat_messages,
            self._on_messages_loaded_interactive,
            current_user_id,
            selected_user_id
        )
        # -----------------------------------

    def _on_messages_loaded_interactive(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback für interaktives Laden von Nachrichten.
        """
        if not self.winfo_exists():
            return

        if error:
            print(f"[FEHLER] _on_messages_loaded_interactive: {error}")
            self.chat_history.config(state=tk.NORMAL)
            self.chat_history.delete("1.0", tk.END)
            self.chat_history.insert("1.0", f"Fehler beim Laden der Nachrichten: {error}")
            self.chat_history.config(state=tk.DISABLED)
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_messages_loaded_interactive (von Thread): {result}")
        else:
            self._update_messages_ui(result, scroll_to_end=True)

    def load_user_list_threaded(self):
        """[GUI-Thread] Lädt die Benutzerliste einmalig beim Start asynchron."""
        print("[ChatTab] Lade initiale Benutzerliste...")

        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            get_users_for_chat,
            self._on_initial_user_list_loaded,
            self.current_user_id
        )
        # -----------------------------------

    def _on_initial_user_list_loaded(self, result, error):
        """[GUI-Thread] Callback für die initiale Benutzerliste."""
        if not self.winfo_exists():
            return
        if error:
            print(f"[FEHLER] _on_initial_user_list_loaded: {error}")
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_initial_user_list_loaded (von Thread): {result}")
        else:
            self._update_user_list_ui(result)

    def _update_user_list_ui(self, users):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert das Treeview mit den Benutzerdaten.
        """
        if users is None or not self.winfo_exists():
            return

        self.user_tree.unbind("<<TreeviewSelect>>")
        selected_item_id = self.user_tree.selection()[0] if self.user_tree.selection() else None
        existing_ids = set(self.user_tree.get_children())

        now = datetime.now()

        for user in users:
            user_id_str = str(user['id'])
            full_name = f"{user['vorname']} {user['name']}"
            self.user_list_data[user_id_str] = {'name': full_name, 'last_seen': user['last_seen']}

            status = "Offline"
            if user['last_seen']:
                last_seen_dt = user['last_seen']
                if isinstance(last_seen_dt, str):
                    try:
                        last_seen_dt = datetime.strptime(last_seen_dt, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        last_seen_dt = None

                if last_seen_dt and (now - last_seen_dt < timedelta(minutes=2)):
                    status = "Online"

            unread_count = user.get('unread_count', 0)

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

        if selected_item_id and self.user_tree.exists(selected_item_id):
            try:
                self.user_tree.selection_set(selected_item_id)
            except tk.TclError:
                pass

        self.user_tree.bind("<<TreeviewSelect>>", self.on_user_select)

    def _update_messages_ui(self, messages, scroll_to_end=True):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert das Text-Widget mit den Nachrichten.
        """
        if messages is None or not self.winfo_exists():
            if messages is None:
                return

        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)

        for msg in messages:
            timestamp = msg['timestamp']
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    timestamp = datetime.now()  # Fallback
            timestamp_str = timestamp.strftime("%d.%m.%Y %H:%M")
            tag = "sent" if msg['sender_id'] == self.current_user_id else "received"
            self.chat_history.insert(tk.END, f"{msg['message']}\n", tag)
            self.chat_history.insert(tk.END, f"{timestamp_str}\n\n", "timestamp")

        self.chat_history.config(state=tk.DISABLED)
        if scroll_to_end:
            self.chat_history.yview(tk.END)

    def send_message(self, event=None):
        """
        [LÄUFT IM GUI-THREAD]
        Sendet eine Nachricht.
        """
        message = self.message_entry.get().strip()
        if message and self.selected_user_id:
            self.message_entry.delete(0, tk.END)
            self._add_optimistic_message(message)

            # --- KORREKTUR: 'args=' entfernt ---
            self.thread_manager.start_worker(
                send_chat_message,
                self._on_message_sent,
                self.current_user_id,
                self.selected_user_id,
                message
            )
            # -----------------------------------

    def _add_optimistic_message(self, message):
        """Fügt die gesendete Nachricht sofort hinzu."""
        if not self.winfo_exists(): return

        timestamp_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.insert(tk.END, f"{message}\n", "sent")
        self.chat_history.insert(tk.END, f"{timestamp_str}\n\n", "timestamp")
        self.chat_history.config(state=tk.DISABLED)
        self.chat_history.yview(tk.END)

    def _on_message_sent(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback nach dem Senden einer Nachricht.
        """
        if not self.winfo_exists(): return

        if error or isinstance(result, Exception) or not result:
            print(f"[FEHLER] Beim Senden der Nachricht: {error or result}")
            self.load_messages_threaded(self.current_user_id, self.selected_user_id)
        else:
            print("[ChatTab] Nachricht erfolgreich gesendet.")

    def refresh_data(self):
        """Öffentliche Methode, um ein Update zu erzwingen."""
        self.load_user_list_threaded()
        if self.selected_user_id:
            self.load_messages_threaded(self.current_user_id, self.selected_user_id)