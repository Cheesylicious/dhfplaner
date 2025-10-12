# database/db_dogs.py
import sqlite3
from .db_core import create_connection

def get_all_dogs():
    """Fetches all dogs."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dogs ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def add_dog(data):
    """Adds a new dog."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dogs (name, breed, birth_date, chip_number, acquisition_date, departure_date, last_dpo_date, vaccination_info) VALUES (:name, :breed, :birth_date, :chip_number, :acquisition_date, :departure_date, :last_dpo_date, :vaccination_info)",
            data)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_dog(dog_id, data):
    """Updates a dog's data."""
    data['id'] = dog_id
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dogs SET name = :name, breed = :breed, birth_date = :birth_date, chip_number = :chip_number, acquisition_date = :acquisition_date, departure_date = :departure_date, last_dpo_date = :last_dpo_date, vaccination_info = :vaccination_info WHERE id = :id",
            data)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_dog(dog_id):
    """Deletes a dog."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET diensthund = '' WHERE diensthund = (SELECT name FROM dogs WHERE id = ?)",
                       (dog_id,))
        cursor.execute("DELETE FROM dogs WHERE id = ?", (dog_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_dog_handlers(dog_name):
    """Fetches the handlers of a dog."""
    if not dog_name: return []
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, vorname, name FROM users WHERE diensthund = ?", (dog_name,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_dog_assignment_count(dog_name):
    """Gets the assignment count of a dog."""
    if not dog_name or dog_name == "Kein": return 0
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE diensthund = ?", (dog_name,))
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_available_dogs():
    """Fetches all available dogs."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.name FROM dogs d
            LEFT JOIN (
                SELECT diensthund, COUNT(*) as assignment_count
                FROM users
                WHERE diensthund IS NOT NULL AND diensthund != ''
                GROUP BY diensthund
            ) AS assignments ON d.name = assignments.diensthund
            WHERE assignments.assignment_count < 2 OR assignments.assignment_count IS NULL
        """)
        return [row['name'] for row in cursor.fetchall()]
    finally:
        conn.close()


def assign_dog(dog_name, user_id):
    """Assigns a dog to a user."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET diensthund = ? WHERE id = ?", (dog_name, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Fehler bei der Zuweisung: {e}")
        return False
    finally:
        conn.close()