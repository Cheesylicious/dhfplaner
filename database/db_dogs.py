# database/db_dogs.py
from .db_core import create_connection
import mysql.connector


def get_all_dogs():
    """
    Holt alle Hunde aus der Datenbank (OHNE Bild-BLOB).
    Wird für den schnellen global_dog_cache beim Start verwendet. (Regel 2)
    """
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # --- KORREKTUR (Regel 2): Wählt alle Spalten AUSSER dem BLOB aus ---
        cursor.execute("""
                       SELECT id,
                              name,
                              breed,
                              birth_date,
                              chip_number,
                              acquisition_date,
                              departure_date,
                              last_dpo_date,
                              vaccination_info
                       FROM dogs
                       ORDER BY name
                       """)
        # --- ENDE KORREKTUR ---
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_dog_details(dog_id):
    """
    (NEUE FUNKTION) Holt alle Details für EINEN Hund, inkl. Bild-BLOB.
    Wird vom Edit-Fenster und der Detailansicht genutzt (Lazy Loading). (Regel 1 & 4)
    """
    conn = create_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM dogs WHERE id = %s", (dog_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Fehler in get_dog_details: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def add_dog(data):
    """Fügt einen neuen Hund hinzu (inkl. Bild-BLOB)."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        # --- KORREKTUR (Regel 1): image_blob hinzugefügt ---
        query = """
                INSERT INTO dogs (name, breed, birth_date, chip_number,
                                  acquisition_date, departure_date, last_dpo_date,
                                  vaccination_info, image_blob)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) \
                """
        params = (data['name'], data['breed'], data['birth_date'], data['chip_number'], data['acquisition_date'],
                  data['departure_date'], data['last_dpo_date'], data['vaccination_info'],
                  data.get('image_blob', None))  # .get() für Sicherheit
        # --- ENDE KORREKTUR ---

        cursor.execute(query, params)
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        # Fängt Fehler ab, wenn z.B. der Name oder die Chipnummer bereits existiert (UNIQUE constraint)
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_dog(dog_id, data):
    """Aktualisiert die Daten eines Hundes (inkl. Bild-BLOB)."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        # --- KORREKTUR (Regel 1): image_blob hinzugefügt ---
        query = """
                UPDATE dogs \
                SET name             = %s, \
                    breed            = %s, \
                    birth_date       = %s, \
                    chip_number      = %s, \
                    acquisition_date = %s, \
                    departure_date   = %s, \
                    last_dpo_date    = %s, \
                    vaccination_info = %s, \
                    image_blob       = %s
                WHERE id = %s \
                """
        params = (data['name'], data['breed'], data['birth_date'], data['chip_number'], data['acquisition_date'],
                  data['departure_date'], data['last_dpo_date'], data['vaccination_info'],
                  data.get('image_blob', None),  # .get() für Sicherheit
                  dog_id)
        # --- ENDE KORREKTUR ---

        cursor.execute(query, params)
        conn.commit()
        return True
    except mysql.connector.IntegrityError:
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_dog(dog_id):
    """Löscht einen Hund."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor(dictionary=True)
        # Zuerst den Namen des Hundes holen, um die Zuweisung bei den Benutzern zu entfernen
        cursor.execute("SELECT name FROM dogs WHERE id = %s", (dog_id,))
        dog_data = cursor.fetchone()
        if dog_data:
            dog_name = dog_data['name']
            cursor.execute("UPDATE users SET diensthund = '' WHERE diensthund = %s", (dog_name,))

        # Dann den Hund löschen
        cursor.execute("DELETE FROM dogs WHERE id = %s", (dog_id,))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"DB Fehler in delete_dog: {e}")
        conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_dog_handlers(dog_name):
    """Holt die Hundeführer eines bestimmten Hundes."""
    if not dog_name: return []
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, vorname, name FROM users WHERE diensthund = %s", (dog_name,))
        return cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_dog_assignment_count(dog_name):
    """Gibt die Anzahl der Zuweisungen für einen Hund zurück."""
    if not dog_name or dog_name == "Kein": return 0
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE diensthund = %s", (dog_name,))
        return cursor.fetchone()[0]
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_available_dogs():
    """Holt alle Hunde, die weniger als zweimal zugewiesen sind."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # Diese Logik bleibt gleich, da sie Standard-SQL ist
        cursor.execute("""
                       SELECT d.name
                       FROM dogs d
                                LEFT JOIN (SELECT diensthund, COUNT(*) as assignment_count
                                           FROM users
                                           WHERE diensthund IS NOT NULL
                                             AND diensthund != ''
                                           GROUP BY diensthund) AS assignments ON d.name = assignments.diensthund
                       WHERE assignments.assignment_count < 2
                          OR assignments.assignment_count IS NULL
                       """)
        return [row['name'] for row in cursor.fetchall()]
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def assign_dog(dog_name, user_id):
    """Weist einem Benutzer einen Hund zu."""
    conn = create_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET diensthund = %s WHERE id = %s", (dog_name, user_id))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"Fehler bei der Zuweisung: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()