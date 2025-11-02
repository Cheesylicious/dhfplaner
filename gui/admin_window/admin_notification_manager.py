# gui/admin_window/admin_notification_manager.py
import tkinter as tk
from tkinter import ttk

# DB-Funktionen für Benachrichtigungen
from database.db_chat import get_senders_with_unread_messages
from database.db_requests import get_pending_wunschfrei_requests, get_pending_vacation_requests_count
from database.db_reports import get_open_bug_reports_count, get_reports_with_user_feedback_count
from database.db_admin import get_pending_password_resets_count


class AdminNotificationManager:
    def __init__(self, admin_window):
        """
        Manager für Benachrichtigungen, Chat-Updates und periodische Prüfungen.

        :param admin_window: Die Instanz von MainAdminWindow.
        """
        self.admin_window = admin_window
        self.user_data = admin_window.user_data

        # --- NEU: Referenz auf den ThreadManager ---
        self.thread_manager = admin_window.thread_manager

        # Referenzen auf UI-Elemente aus dem Hauptfenster
        self.chat_notification_frame = admin_window.chat_notification_frame
        self.notification_frame = admin_window.notification_frame
        self.notebook = admin_window.notebook

        # Referenzen auf andere Manager
        self.tab_manager = admin_window.tab_manager
        self.action_handler = admin_window.action_handler

    def start_checkers(self):
        """Startet die periodischen Checker-Schleifen (jetzt Thread-basiert)."""
        self.admin_window.after(1000, self.check_for_updates_threaded)
        self.admin_window.after(2000, self.check_chat_notifications_threaded)

    # --- BLOCK 1: Update-Schleife (Header-Benachrichtigungen & Tab-Titel) ---

    def check_for_updates_threaded(self):
        """
        [LÄUFT IM GUI-THREAD]
        Startet die Hintergrund-Tasks für Header-Updates und Tab-Titel.
        """
        print("[DEBUG] check_for_updates_threaded: Starte Hintergrund-Abfragen.")
        if not self.admin_window.winfo_exists(): return

        # 1. Thread für Header-Benachrichtigungen starten
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self._fetch_header_notification_data,  # target_func
            self._on_header_data_fetched  # on_complete
        )

        # 2. Thread für Tab-Titel-Updates starten
        # --- KORREKTUR: 'args=' entfernt ---
        self.thread_manager.start_worker(
            self.tab_manager.fetch_tab_title_counts,  # target_func
            self._on_tab_titles_fetched  # on_complete
        )
        # ------------------------------------

        # 3. Spezifische Checks (bleibt im GUI-Thread, da schnell)
        if "Mitarbeiter" in self.tab_manager.loaded_tabs:
            user_tab = self.tab_manager.tab_frames.get("Mitarbeiter")
            if user_tab and user_tab.winfo_exists() and hasattr(user_tab, 'check_pending_approvals'):
                try:
                    print("[DEBUG] check_for_updates: Prüfe ausstehende Freischaltungen.")
                    user_tab.check_pending_approvals()
                except Exception as e_user:
                    print(f"[FEHLER] bei user_tab.check_pending_approvals: {e_user}")

    def _fetch_header_notification_data(self):
        """
        [LÄUFT IM THREAD]
        Sammelt alle Daten für die Header-Buttons.
        """
        data = {}
        try:
            data['password_resets'] = get_pending_password_resets_count()
            data['wunschfrei'] = len(get_pending_wunschfrei_requests())
            data['urlaub'] = get_pending_vacation_requests_count()
            data['user_feedback'] = get_reports_with_user_feedback_count()
            open_bug_count = get_open_bug_reports_count()
            actual_open_bugs = open_bug_count - data['user_feedback']
            data['actual_open_bugs'] = actual_open_bugs

            return data
        except Exception as e:
            print(f"[FEHLER] im Thread _fetch_header_notification_data: {e}")
            return e

    def _on_header_data_fetched(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback, wenn die Header-Daten aus dem Thread zurückkommen.
        """
        if not self.admin_window.winfo_exists():
            return

        if error:
            print(f"[FEHLER] _on_header_data_fetched: {error}")
            self.update_header_notifications_ui(None, has_error=True)
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_header_data_fetched (von Thread): {result}")
            self.update_header_notifications_ui(None, has_error=True)
        else:
            self.update_header_notifications_ui(result, has_error=False)

        self.admin_window.after(60000, self.check_for_updates_threaded)  # Alle 60 Sek.

    def _on_tab_titles_fetched(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Callback, wenn die Zähler für die Tabs geladen wurden.
        """
        if not self.admin_window.winfo_exists():
            return

        if error:
            print(f"[FEHLER] _on_tab_titles_fetched: {error}")
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_tab_titles_fetched (von Thread): {result}")
        else:
            self.tab_manager.update_tab_titles_ui(result)

    def update_header_notifications_ui(self, data: dict, has_error: bool):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert die Benachrichtigungs-Buttons im Header.
        """
        if not hasattr(self.admin_window,
                       'notification_frame') or not self.admin_window.notification_frame.winfo_exists():
            print("[WARNUNG] update_header_notifications_ui: notification_frame nicht gefunden oder zerstört.")
            return

        notification_frame = self.admin_window.notification_frame
        style = self.admin_window.style

        for widget in notification_frame.winfo_children():
            widget.destroy()

        if has_error:
            ttk.Label(notification_frame, text="Fehler beim Laden der Benachrichtigungen!", foreground="red",
                      font=('Segoe UI', 10, 'bold')).pack(padx=5)
            return

        notifications = []
        if not data:
            data = {}

        try:
            pending_password_resets = data.get('password_resets', 0)
            if pending_password_resets > 0:
                notifications.append(
                    {"text": f"{pending_password_resets} Passwort-Reset(s)", "bg": "mediumpurple", "fg": "white",
                     "action": self.action_handler.open_password_resets_window})

            pending_wunsch_count = data.get('wunschfrei', 0)
            if pending_wunsch_count > 0:
                notifications.append(
                    {"text": f"{pending_wunsch_count} Offene Wunschanfrage(n)", "bg": "orange", "fg": "black",
                     "tab": "Wunschanfragen"})

            pending_urlaub_count = data.get('urlaub', 0)
            if pending_urlaub_count > 0:
                notifications.append(
                    {"text": f"{pending_urlaub_count} Offene Urlaubsanträge", "bg": "lightblue", "fg": "black",
                     "tab": "Urlaubsanträge"})

            user_feedback_count = data.get('user_feedback', 0)
            if user_feedback_count > 0:
                notifications.append(
                    {"text": f"{user_feedback_count} User-Feedback(s)", "bg": "springgreen", "fg": "black",
                     "tab": "Bug-Reports"})

            actual_open_bugs = data.get('actual_open_bugs', 0)
            if actual_open_bugs > 0:
                notifications.append({"text": f"{actual_open_bugs} Offene Bug-Report(s)", "bg": "tomato", "fg": "white",
                                      "tab": "Bug-Reports"})

        except Exception as e:
            print(f"[FEHLER] beim Verarbeiten der Benachrichtigungsdaten: {e}")
            has_error = True

        if has_error:
            ttk.Label(notification_frame, text="Fehler bei Anzeige der Benachrichtigungen!", foreground="red",
                      font=('Segoe UI', 10, 'bold')).pack(padx=5)
        elif not notifications:
            ttk.Label(notification_frame, text="Keine neuen Benachrichtigungen", font=('Segoe UI', 10, 'italic')).pack(
                padx=5)
        else:
            for i, notif in enumerate(notifications):
                style_name = f'Notif{i}.TButton'
                style.configure(style_name, background=notif["bg"], foreground=notif.get("fg", "black"),
                                font=('Segoe UI', 10, 'bold'), padding=(10, 5))
                hover_color = self.admin_window.utils.calculate_hover_color(notif["bg"])
                style.map(style_name, background=[('active', hover_color)], relief=[('pressed', 'sunken')])

                command = None
                if "action" in notif:
                    command = notif["action"]
                else:
                    tab_name = notif.get("tab")
                    if tab_name:
                        command = lambda tab=tab_name: self.tab_manager.switch_to_tab(tab)

                if command:
                    btn = ttk.Button(notification_frame, text=notif["text"], style=style_name, command=command)
                    btn.pack(side="left", padx=5, fill="x", expand=True)

    # --- BLOCK 2: Chat-Benachrichtigungs-Schleife ---

    def check_chat_notifications_threaded(self):
        """
        [LÄUFT IM GUI-THREAD]
        Startet die Chat-Abfrage im Hintergrund.
        """
        if not self.admin_window.winfo_exists():
            return

        # --- KORREKTUR: 'args=' entfernt. Das Argument wird positional übergeben ---
        self.thread_manager.start_worker(
            get_senders_with_unread_messages,  # target_func
            self._on_chat_data_fetched,  # on_complete
            self.user_data['id']  # *args[0]
        )
        # -----------------------------------------------------------------------

    def _on_chat_data_fetched(self, result, error):
        """
        [LÄUFT IM GUI-THREAD]
        Aktualisiert die Chat-Leiste, wenn Daten aus dem Thread kommen.
        """
        if not self.admin_window.winfo_exists():
            print("[DEBUG] _on_chat_data_fetched: Fenster existiert nicht mehr. Breche ab.")
            return

        new_senders = result
        if error:
            print(f"[FEHLER] bei _on_chat_data_fetched: {error}")
            new_senders = []
        elif isinstance(result, Exception):
            print(f"[FEHLER] _on_chat_data_fetched (von Thread): {result}")
            new_senders = []

        try:
            is_visible = self.chat_notification_frame.winfo_ismapped()

            if new_senders or is_visible:
                if is_visible:
                    for widget in self.chat_notification_frame.winfo_children():
                        widget.destroy()

                if new_senders:
                    latest_sender_id = new_senders[0]['sender_id']
                    total_unread = sum(s['unread_count'] for s in new_senders)
                    action = lambda event=None, uid=latest_sender_id: self.go_to_chat(uid)

                    if not is_visible:
                        self.chat_notification_frame.pack(fill='x', side='top', ipady=5, before=self.notebook)

                    self.chat_notification_frame.bind("<Button-1>", action)
                    label_text = f"Sie haben {total_unread} neue Nachricht(en)! Hier klicken zum Anzeigen."
                    notification_label = tk.Label(self.chat_notification_frame, text=label_text, bg='tomato',
                                                  fg='white',
                                                  font=('Segoe UI', 12, 'bold'), cursor="hand2")
                    notification_label.pack(side='left', padx=15, pady=5)
                    notification_label.bind("<Button-1>", action)

                    show_button = ttk.Button(self.chat_notification_frame, text="Anzeigen", command=action)
                    show_button.pack(side='right', padx=15)
                else:
                    if is_visible:
                        self.chat_notification_frame.pack_forget()

        except Exception as e:
            print(f"[FEHLER] beim Anzeigen der Chat-Benachrichtigung: {e}")
            if self.chat_notification_frame.winfo_ismapped():
                self.chat_notification_frame.pack_forget()
        finally:
            self.admin_window.after(10000, self.check_chat_notifications_threaded)  # Alle 10 Sek.

    # --- BLOCK 3: Hilfsfunktion (unverändert) ---

    def go_to_chat(self, user_id):
        """Wechselt zum Chat-Tab und versucht, den Chat mit der user_id zu öffnen."""
        print(f"[DEBUG] go_to_chat aufgerufen für User ID: {user_id}")
        self.tab_manager.switch_to_tab("Chat")

        def _select_user_when_ready():
            if not self.admin_window.winfo_exists():
                return

            if "Chat" in self.tab_manager.loaded_tabs:
                chat_tab = self.tab_manager.tab_frames.get("Chat")
                if chat_tab and chat_tab.winfo_exists() and hasattr(chat_tab, "select_user"):
                    try:
                        print(f"[DEBUG] Chat-Tab ist geladen, rufe select_user({user_id}) auf.")
                        chat_tab.select_user(user_id)
                        if self.chat_notification_frame.winfo_ismapped():
                            self.chat_notification_frame.pack_forget()
                            print("[DEBUG] Chat-Benachrichtigung ausgeblendet.")
                    except Exception as e:
                        print(f"[FEHLER] beim Aufrufen von chat_tab.select_user für {user_id}: {e}")
                elif not (chat_tab and chat_tab.winfo_exists()):
                    print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab Widget existiert nicht mehr.")
                else:
                    print("[FEHLER] go_to_chat/_select_user_when_ready: Chat-Tab hat keine 'select_user' Methode.")
            elif "Chat" in self.tab_manager.loading_tabs or (
                    "Chat" not in self.tab_manager.loaded_tabs and "Chat" in self.tab_manager.tab_definitions):
                print("[DEBUG] go_to_chat/_select_user_when_ready: Chat-Tab noch nicht geladen, warte 200ms...")
                self.admin_window.after(200, _select_user_when_ready)
            else:
                print(
                    f"[DEBUG] go_to_chat/_select_user_when_ready: Unerwarteter Status für Chat-Tab (UserID: {user_id}). Breche ab.")

        self.admin_window.after(50, _select_user_when_ready)