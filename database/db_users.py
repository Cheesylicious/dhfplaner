# database/db_users.py
import sqlite3
from .db_core import create_connection, hash_password

def get_user_count():
    """Gets the total number of users."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Fetches a single user by their ID."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
    finally:
        if conn:
            conn.close()


def add_user(vorname, name, password):
    """Adds a new user to the database."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        user_count = get_user_count()
        role = "SuperAdmin" if user_count == 0 else "Benutzer"
        if not vorname or not name: return False, "Bitte Vor- und Nachnamen angeben."
        cursor.execute("INSERT INTO users (password_hash, role, vorname, name) VALUES (?, ?, ?, ?)",
                       (hash_password(password), role, vorname, name))
        conn.commit()
        return True, "Registrierung erfolgreich."
    except sqlite3.IntegrityError:
        return False, "Ein Benutzer mit diesem Namen existiert bereits."
    finally:
        conn.close()


def check_login(vorname, name, password):
    """Checks user login credentials."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE lower(vorname) = ? AND lower(name) = ?",
                       (vorname.lower(), name.lower()))
        user = cursor.fetchone()
        if user and user['password_hash'] == hash_password(password):
            return dict(user)
        return None
    finally:
        conn.close()


def get_all_users():
    """Fetches all users from the database."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY name")
        users = cursor.fetchall()
        return {str(user['id']): dict(user) for user in users}
    finally:
        conn.close()


def get_ordered_users_for_schedule(include_hidden=False):
    """Fetches users ordered for the schedule view."""
    conn = create_connection()
    try:
        query = "SELECT u.*, COALESCE(uo.sort_order, 999999) AS sort_order, COALESCE(uo.is_visible, 1) AS is_visible FROM users u LEFT JOIN user_order uo ON u.id = uo.user_id"
        if not include_hidden:
            query += " WHERE COALESCE(uo.is_visible, 1) = 1"
        query += " ORDER BY sort_order ASC, u.name ASC"
        cursor = conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Fehler beim Abrufen der geordneten Benutzer: {e}")
        return list(get_all_users().values())


def save_user_order(order_data_list):
    """Saves the user order and visibility."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM user_order")
        cursor.executemany("INSERT INTO user_order (user_id, sort_order, is_visible) VALUES (?, ?, ?)", order_data_list)
        conn.commit()
        return True, "Reihenfolge und Sichtbarkeit erfolgreich gespeichert."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler beim Speichern der Reihenfolge und Sichtbarkeit: {e}"
    finally:
        conn.close()


def update_user(user_id, data):
    """Updates user data."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE users SET 
               vorname = ?, name = ?, geburtstag = ?, telefon = ?, diensthund = ?, 
               urlaub_gesamt = ?, role = ?, entry_date = ?, 
               has_seen_tutorial = ?, password_changed = ?
               WHERE id = ?""",
            (data.get('vorname'), data.get('name'), data.get('geburtstag', ''),
             data.get('telefon', ''), data.get('diensthund', ''), data.get('urlaub_gesamt', 30),
             data.get('role', 'Benutzer'), data.get('entry_date', ''),
             data.get('has_seen_tutorial', 0), data.get('password_changed', 0),
             user_id)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"DB Error on update_user: {e}")
        return False
    finally:
        conn.close()


def change_password(user_id, new_password):
    """Changes a user's password."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = ?, password_changed = 1 WHERE id = ?",
            (hash_password(new_password), user_id)
        )
        conn.commit()
        return True, "Passwort erfolgreich geändert."
    except sqlite3.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        conn.close()


def delete_user(user_id):
    """Deletes a user from the database."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vacation_requests WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        cursor.execute("DELETE FROM user_order WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def set_user_tutorial_seen(user_id):
    """Sets the tutorial as seen for a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET has_seen_tutorial = 1 WHERE id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"DB-Fehler beim Setzen des Tutorial-Status: {e}")
        return False
    finally:
        conn.close()

def get_all_user_participation():
    """Fetches the last participation data for all visible users."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.vorname, u.name, u.last_ausbildung, u.last_schiessen
            FROM users u
            LEFT JOIN user_order uo ON u.id = uo.user_id
            WHERE COALESCE(uo.is_visible, 1) = 1
            ORDER BY COALESCE(uo.sort_order, 9999)
        """)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"DB Error on get_all_user_participation: {e}")
        return []
    finally:
        conn.close()