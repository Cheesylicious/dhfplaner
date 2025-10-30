# database/db_schema_helpers.py
# NEU: Ausgelagerte Schema-Helfer, um Abhängigkeiten aufzulösen.

def _add_column_if_not_exists(cursor, db_name, table_name, column_name, column_type):
    """Fügt eine Spalte hinzu, falls sie nicht existiert."""
    if not db_name:
        raise ValueError("Datenbank-Name nicht in DB_CONFIG gefunden.")

    cursor.execute(f"""
        SELECT COUNT(*) AS count_result FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (db_name, table_name, column_name))

    result_dict = cursor.fetchone()

    if result_dict and result_dict['count_result'] == 0:
        print(f"Füge Spalte '{column_name}' zur Tabelle '{table_name}' hinzu...")
        # Backticks um Tabellen- und Spaltennamen für Sicherheit
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_type}")


def _add_index_if_not_exists(cursor, table_name, index_name, columns):
    """Fügt einen Index hinzu, falls er nicht existiert."""
    cursor.execute(f"""
        SELECT COUNT(*) AS count_result FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}' AND INDEX_NAME = '{index_name}'
    """)

    result_dict = cursor.fetchone()

    if result_dict and result_dict['count_result'] == 0:
        print(f"Füge Index '{index_name}' zur Tabelle '{table_name}' hinzu...")
        # Backticks um Index- und Tabellennamen
        cursor.execute(f"CREATE INDEX `{index_name}` ON `{table_name}` ({columns})")