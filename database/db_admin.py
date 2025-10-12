# database/db_admin.py
import sqlite3
from datetime import datetime
from .db_core import create_connection, hash_password, _create_admin_notification

def lock_month(year, month):
    """Locks a month for editing."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO locked_months (year, month) VALUES (?, ?)", (year, month))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"DB Error on lock_month: {e}")
        return False
    finally:
        conn.close()


def unlock_month(year, month):
    """Unlocks a month for editing."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM locked_months WHERE year = ? AND month = ?", (year, month))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"DB Error on unlock_month: {e}")
        return False
    finally:
        conn.close()


def is_month_locked(year, month):
    """Checks if a month is locked."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM locked_months WHERE year = ? AND month = ?", (year, month))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        print(f"DB Error on is_month_locked: {e}")
        return False
    finally:
        conn.close()


def admin_reset_password(user_id, new_password):
    """Resets a user's password."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = ?, password_changed = 0 WHERE id = ?",
            (hash_password(new_password), user_id)
        )
        conn.commit()
        return True, "Passwort wurde zurückgesetzt. Der Benutzer muss es beim nächsten Login ändern."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_unread_admin_notifications():
    """Fetches unread admin notifications."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, message FROM admin_notifications WHERE is_read = 0 ORDER BY timestamp ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def mark_admin_notifications_as_read(notification_ids):
    """Marks admin notifications as read."""
    if not notification_ids:
        return
    conn = create_connection()
    try:
        cursor = conn.cursor()
        ids_tuple = tuple(notification_ids)
        placeholders = ', '.join('?' for _ in ids_tuple)
        query = f"UPDATE admin_notifications SET is_read = 1 WHERE id IN ({placeholders})"
        cursor.execute(query, ids_tuple)
        conn.commit()
    finally:
        conn.close()


def create_user_by_admin(data):
    """Creates a new user by an admin."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        urlaub_gesamt = data.get('urlaub_gesamt') if data.get('urlaub_gesamt') else 30
        cursor.execute(
            "INSERT INTO users (vorname, name, password_hash, role, geburtstag, telefon, diensthund, urlaub_gesamt, urlaub_rest, entry_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data['vorname'], data['name'], hash_password(data['password']), data['role'], data.get('geburtstag', ''),
             data.get('telefon', ''), data.get('diensthund', ''), urlaub_gesamt, urlaub_gesamt,
             data.get('entry_date', '')))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"Error in create_user_by_admin: {e}")
        return False
    finally:
        conn.close()


def request_password_reset(vorname, name):
    """Requests a password reset for a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE lower(vorname) = ? AND lower(name) = ?",
                       (vorname.lower(), name.lower()))
        user = cursor.fetchone()
        if user:
            user_id = user['id']
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "INSERT INTO password_reset_requests (user_id, timestamp) VALUES (?, ?)",
                (user_id, timestamp)
            )
            _create_admin_notification(cursor, f"Benutzer {vorname} {name} hat ein Passwort-Reset angefordert.")
            conn.commit()
            return True, "Ihre Anfrage wurde an einen Administrator gesendet."
        else:
            return False, "Benutzer nicht gefunden."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_pending_password_resets():
    """Fetches all pending password resets."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pr.id, u.vorname, u.name, pr.timestamp
            FROM password_reset_requests pr
            JOIN users u ON pr.user_id = u.id
            WHERE pr.status = 'Ausstehend'
            ORDER BY pr.timestamp ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def approve_password_reset(request_id, new_password):
    """Approves a password reset request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM password_reset_requests WHERE id = ?", (request_id,))
        result = cursor.fetchone()
        if result:
            user_id = result['user_id']
            cursor.execute(
                "UPDATE users SET password_hash = ?, password_changed = 0 WHERE id = ?",
                (hash_password(new_password), user_id)
            )
            cursor.execute("UPDATE password_reset_requests SET status = 'Genehmigt' WHERE id = ?", (request_id,))
            conn.commit()
            return True, f"Passwort für Benutzer ID {user_id} wurde zurückgesetzt."
        return False, "Anfrage nicht gefunden."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def reject_password_reset(request_id):
    """Rejects a password reset request."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE password_reset_requests SET status = 'Abgelehnt' WHERE id = ?", (request_id,))
        conn.commit()
        return True, "Anfrage abgelehnt."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def get_pending_password_resets_count():
    """Gets the count of pending password resets."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM password_reset_requests WHERE status = 'Ausstehend'")
        return cursor.fetchone()[0]
    finally:
        conn.close()