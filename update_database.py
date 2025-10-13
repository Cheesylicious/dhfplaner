import mysql.connector
from mysql.connector import errorcode

# WICHTIG: Trage hier exakt die gleichen Datenbank-Zugangsdaten ein,
# die auch in deiner 'db_core.py' verwendet werden.
DB_CONFIG = {
    'user': 'planer_user',
    'password': 'PlanerNeu-2025#',
    'host': '100.118.148.97',  # oder die IP-Adresse deines Servers
    'database': 'planer_db',  # der Name deiner Datenbank
    'raise_on_warnings': True
}

# Definitionen der Spalten, die wir prüfen und ggf. hinzufügen wollen
COLUMNS_TO_ADD = {
    'bug_reports': {
        'category': "VARCHAR(50) DEFAULT 'Kleiner Fehler'",
        'user_notes': "TEXT"  # NEUE SPALTE für User-Feedback
    }
}


def update_schema():
    """
    Stellt sicher, dass alle notwendigen Spalten in den Tabellen existieren.
    """
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("✅ Erfolgreich mit der Datenbank verbunden.")

        for table_name, columns in COLUMNS_TO_ADD.items():
            for column_name, column_definition in columns.items():
                print(f"Prüfe Spalte '{column_name}' in Tabelle '{table_name}'...")
                cursor.execute(f"""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                    AND table_name = '{table_name}' AND column_name = '{column_name}'
                """)

                if cursor.fetchone()[0] == 0:
                    print(f"Spalte '{column_name}' nicht gefunden. Füge sie hinzu...")
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
                    print(f"🚀 Spalte '{column_name}' erfolgreich zu Tabelle '{table_name}' hinzugefügt.")
                else:
                    print(f"👍 Spalte '{column_name}' existiert bereits.")

        conn.commit()

    except mysql.connector.Error as err:
        print(f"❌ Datenbankfehler: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("Verbindung zur Datenbank geschlossen.")


if __name__ == "__main__":
    update_schema()