# database/db_core.py
import sqlite3
import hashlib
from datetime import datetime

DATABASE_NAME = 'planer.db'
ROLE_HIERARCHY = {"Gast": 1, "Benutzer": 2, "Admin": 3, "SuperAdmin": 4}


def hash_password(password):
    """Hashes the password using SHA256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_connection():
    """Creates a database connection."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Adds a column to a table if it does not exist."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row['name'] for row in cursor.fetchall()]
    if column_name not in columns:
        print(f"Füge Spalte '{column_name}' zur Tabelle '{table_name}' hinzu...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def initialize_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = create_connection()
    try:
        cursor = conn.cursor()
        # --- Create Tables ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                vorname TEXT NOT NULL,
                name TEXT NOT NULL,
                geburtstag TEXT,
                telefon TEXT,
                diensthund TEXT,
                urlaub_gesamt INTEGER DEFAULT 30,
                urlaub_rest INTEGER DEFAULT 30,
                entry_date TEXT,
                has_seen_tutorial INTEGER DEFAULT 0,
                password_changed INTEGER DEFAULT 0,
                last_ausbildung TEXT,
                last_schiessen TEXT,
                UNIQUE (vorname, name)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacation_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL,
                request_date TEXT NOT NULL,
                archived INTEGER DEFAULT 0,
                user_notified INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wunschfrei_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                request_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ausstehend',
                notified INTEGER DEFAULT 0,
                rejection_reason TEXT,
                requested_shift TEXT,
                requested_by TEXT DEFAULT 'user',
                UNIQUE(user_id, request_date),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                breed TEXT,
                birth_date TEXT,
                chip_number TEXT UNIQUE,
                acquisition_date TEXT,
                departure_date TEXT,
                last_dpo_date TEXT,
                vaccination_info TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                abbreviation TEXT UNIQUE NOT NULL,
                hours INTEGER NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#FFFFFF',
                start_time TEXT,
                end_time TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                shift_date TEXT NOT NULL,
                shift_abbrev TEXT NOT NULL,
                UNIQUE (user_id, shift_date),
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (shift_abbrev) REFERENCES shift_types (abbreviation)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_order (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL,
                is_visible INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shift_order (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                abbreviation TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL,
                is_visible INTEGER DEFAULT 1,
                check_for_understaffing INTEGER DEFAULT 0
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER,
                action_type TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bug_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Neu',
                is_read INTEGER NOT NULL DEFAULT 0,
                user_notified INTEGER NOT NULL DEFAULT 1,
                archived INTEGER NOT NULL DEFAULT 0,
                admin_notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ausstehend',
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS locked_months (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                PRIMARY KEY (year, month)
            );
        """)

        # --- Add Columns if not exists ---
        _add_column_if_not_exists(cursor, "users", "entry_date", "TEXT")
        _add_column_if_not_exists(cursor, "shift_types", "color", "TEXT DEFAULT '#FFFFFF'")
        _add_column_if_not_exists(cursor, "user_order", "is_visible", "INTEGER DEFAULT 1")
        _add_column_if_not_exists(cursor, "shift_order", "is_visible", "INTEGER DEFAULT 1")
        _add_column_if_not_exists(cursor, "shift_order", "check_for_understaffing", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "notified", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "rejection_reason", "TEXT")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "requested_shift", "TEXT")
        _add_column_if_not_exists(cursor, "wunschfrei_requests", "requested_by", "TEXT DEFAULT 'user'")
        _add_column_if_not_exists(cursor, "shift_types", "start_time", "TEXT")
        _add_column_if_not_exists(cursor, "shift_types", "end_time", "TEXT")
        _add_column_if_not_exists(cursor, "bug_reports", "user_notified", "INTEGER NOT NULL DEFAULT 1")
        _add_column_if_not_exists(cursor, "bug_reports", "archived", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_not_exists(cursor, "bug_reports", "admin_notes", "TEXT")
        _add_column_if_not_exists(cursor, "users", "has_seen_tutorial", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "vacation_requests", "archived", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "vacation_requests", "user_notified", "INTEGER DEFAULT 1")
        _add_column_if_not_exists(cursor, "users", "password_changed", "INTEGER DEFAULT 0")
        _add_column_if_not_exists(cursor, "users", "last_ausbildung", "TEXT")
        _add_column_if_not_exists(cursor, "users", "last_schiessen", "TEXT")

        conn.commit()
    finally:
        conn.close()

def _log_activity(cursor, user_id, action_type, details):
    """Logs an activity to the activity_log table."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO activity_log (timestamp, user_id, action_type, details) VALUES (?, ?, ?, ?)",
        (timestamp, user_id, action_type, details)
    )

def _create_admin_notification(cursor, message):
    """Creates a notification for the admin."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "INSERT INTO admin_notifications (message, timestamp) VALUES (?, ?)",
        (message, timestamp)
    )