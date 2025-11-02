# database/db_tasks.py
from datetime import datetime
from .db_core import create_connection
import mysql.connector
from database.db_users import get_user_by_id

# Priorisierung für die Sortierung
TASK_PRIORITY_ORDER = {
    "Kritisch": 5,
    "Hoch": 4,
    "Mittel": 3,
    "Niedrig": 2,
    "Info": 1
}

# Kategorien für die Aufgaben
TASK_CATEGORIES = [
    "Neue Funktion",
    "Verbesserung",
    "Refactoring",
    "Datenbank",
    "GUI-Anpassung",
    "Sonstiges"
]

# Status-Werte für Aufgaben
TASK_STATUS_VALUES = [
    "Neu",
    "In Planung",
    "In Bearbeitung",
    "Warte auf Feedback",
    "Erledigt"
]


def create_task(creator_admin_id, title, description, category, priority):
    """Erstellt eine neue Aufgabe (Task)."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor(dictionary=True)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(
            """
            INSERT INTO tasks 
            (creator_admin_id, timestamp, title, description, category, priority, status, archived) 
            VALUES (%s, %s, %s, %s, %s, %s, 'Neu', 0)
            """,
            (creator_admin_id, timestamp, title, description, category, priority)
        )
        conn.commit()
        return True, "Aufgabe erfolgreich erstellt."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_all_tasks():
    """Holt alle Aufgaben und sortiert sie nach Priorität."""
    conn = create_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # creator_admin_id wird jetzt als user_id Alias geholt, um Kompatibilität mit der Namenssuche zu wahren
        cursor.execute("""
                       SELECT t.id,
                              t.creator_admin_id as user_id, 
                              u.vorname,
                              u.name,
                              t.timestamp,
                              t.title,
                              t.description,
                              t.status,
                              t.category,
                              t.priority,
                              t.archived,
                              t.admin_notes
                       FROM tasks t
                                LEFT JOIN users u ON t.creator_admin_id = u.id
                       """)
        tasks = cursor.fetchall()

        # Sortiert primär nach Archiv-Status, dann nach Status (Erledigt ans Ende), dann Priorität
        tasks.sort(key=lambda r: (
            r.get('archived', 0),
            1 if r.get('status') == 'Erledigt' else 0,
            -TASK_PRIORITY_ORDER.get(r.get('priority'), 0),
            r.get('timestamp')
        ), reverse=False)

        return tasks
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def get_open_tasks_count():
    """Gibt die Anzahl der offenen (nicht erledigten und nicht archivierten) Aufgaben zurück."""
    conn = create_connection()
    if conn is None: return 0
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('Erledigt') AND archived = 0"
        )
        count = cursor.fetchone()[0]
        return count
    except mysql.connector.Error as e:
        print(f"Fehler beim Zählen der offenen Aufgaben: {e}")
        return 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_task_status(task_id, new_status):
    """Aktualisiert den Status einer Aufgabe."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = %s WHERE id = %s",
            (new_status, task_id)
        )
        conn.commit()
        return True, "Status aktualisiert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_task_category(task_id, new_category):
    """Aktualisiert die Kategorie einer Aufgabe."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET category = %s WHERE id = %s", (new_category, task_id))
        conn.commit()
        return True, "Kategorie aktualisiert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def update_task_priority(task_id, new_priority):
    """Aktualisiert die Priorität einer Aufgabe."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET priority = %s WHERE id = %s", (new_priority, task_id))
        conn.commit()
        return True, "Priorität aktualisiert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def append_task_note(task_id, note, admin_name="Admin"):
    """Hängt eine neue Admin-Notiz an eine Aufgabe an."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        timestamped_note = f"[{admin_name}-Notiz am {datetime.now().strftime('%d.%m.%Y %H:%M')}]:\n{note}"
        cursor.execute(
            "UPDATE tasks SET admin_notes = CONCAT_WS('\n\n', admin_notes, %s) WHERE id = %s",
            (timestamped_note, task_id)
        )
        conn.commit()
        return True, "Notiz hinzugefügt."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def archive_task(task_id):
    """Archiviert eine Aufgabe."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET archived = 1 WHERE id = %s", (task_id,))
        conn.commit()
        return True, "Aufgabe wurde archiviert."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def unarchive_task(task_id):
    """Macht die Archivierung einer Aufgabe rückgängig."""
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET archived = 0 WHERE id = %s", (task_id,))
        conn.commit()
        return True, "Aufgabe wurde wiederhergestellt."
    except mysql.connector.Error as e:
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def delete_tasks(task_ids):
    """Löscht Aufgaben."""
    if not task_ids: return False, "Keine IDs zum Löschen übergeben."
    conn = create_connection()
    if conn is None: return False, "Keine Datenbankverbindung."
    try:
        cursor = conn.cursor()
        placeholders = ', '.join(['%s'] * len(task_ids))
        query = f"DELETE FROM tasks WHERE id IN ({placeholders})"
        cursor.execute(query, tuple(task_ids))
        conn.commit()
        if cursor.rowcount > 0:
            return True, f"{cursor.rowcount} Aufgabe(n) endgültig gelöscht."
        else:
            return False, "Keine passenden Aufgaben zum Löschen gefunden."
    except mysql.connector.Error as e:
        conn.rollback()
        return False, f"Datenbankfehler: {e}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()