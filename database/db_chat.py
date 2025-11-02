# database/db_chat.py
from .db_core import create_connection
from datetime import datetime
import mysql.connector


def get_users_for_chat(current_user_id):
    """Holt alle Benutzer außer dem aktuell angemeldeten für die Chat-Liste."""
    conn = create_connection()
    if not conn: return []

    users = []
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT id, vorname, name, last_seen FROM users WHERE id != %s ORDER BY vorname, name"
        cursor.execute(query, (current_user_id,))
        users = cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_users_for_chat: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return users


def get_chat_messages(user1_id, user2_id):
    """Holt die Chat-Nachrichten zwischen zwei Benutzern und markiert sie als gelesen."""
    conn = create_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
                       SELECT sender_id, message, timestamp
                       FROM chat_messages
                       WHERE (sender_id = %s
                         AND recipient_id = %s)
                          OR (sender_id = %s
                         AND recipient_id = %s)
                       ORDER BY timestamp ASC
                       """, (user1_id, user2_id, user2_id, user1_id))
        messages = cursor.fetchall()

        cursor.execute("""
                       UPDATE chat_messages
                       SET is_read = 1
                       WHERE sender_id = %s
                         AND recipient_id = %s
                         AND is_read = 0
                       """, (user2_id, user1_id))
        conn.commit()
        return messages
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_chat_messages: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def send_chat_message(sender_id, recipient_id, message):
    """Speichert eine neue Chat-Nachricht in der Datenbank."""
    conn = create_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO chat_messages (sender_id, recipient_id, message)
                       VALUES (%s, %s, %s)
                       """, (sender_id, recipient_id, message))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Fehler in send_chat_message: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_unread_messages_count_for_user(recipient_id):
    """Zählt alle ungelesenen Nachrichten für einen Benutzer."""
    conn = create_connection()
    if not conn: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE recipient_id = %s AND is_read = 0", (recipient_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_unread_messages_count_for_user: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- ANFANG DER ÄNDERUNG ---
def get_senders_with_unread_messages(recipient_id):
    """Gibt eine Liste von Sendern zurück, von denen es ungelesene Nachrichten gibt."""
    conn = create_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # Gruppiert nach Absender und zählt ungelesene Nachrichten, sortiert nach der neuesten Nachricht
        cursor.execute("""
                       SELECT sender_id, COUNT(*) as unread_count, MAX(timestamp) as last_message_time
                       FROM chat_messages
                       WHERE recipient_id = %s
                         AND is_read = 0
                       GROUP BY sender_id
                       ORDER BY last_message_time DESC
                       """, (recipient_id,))
        return cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_senders_with_unread_messages: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# --- ENDE DER ÄNDERUNG ---

def get_unread_messages_from_user(sender_id, recipient_id):
    """Zählt ungelesene Nachrichten von einem bestimmten Absender."""
    conn = create_connection()
    if not conn: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE sender_id = %s AND recipient_id = %s AND is_read = 0",
                       (sender_id, recipient_id))
        result = cursor.fetchone()
        return result[0] if result else 0
    except mysql.connector.Error as e:
        print(f"DB Fehler in get_unread_messages_from_user: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_user_last_seen(user_id):
    """Aktualisiert den 'last_seen' Zeitstempel eines Benutzers."""
    conn = create_connection()
    if not conn: return
    try:
        cursor = conn.cursor()
        timestamp = datetime.now()
        cursor.execute("UPDATE users SET last_seen = %s WHERE id = %s", (timestamp, user_id))
        conn.commit()
    except mysql.connector.Error as e:
        print(f"DB Fehler in update_user_last_seen: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()