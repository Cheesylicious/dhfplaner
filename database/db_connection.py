# database/db_connection.py
# NEUE DATEI: Isoliert die Verbindungslogik, um zirkuläre Imports zu verhindern.

import mysql.connector
from mysql.connector import pooling
import json
import sys
import os
import threading

# Importiert die Schema-Logik
from . import db_schema

# ==============================================================================
# 💥 DATENBANK-KONFIGURATION WIRD JETZT AUS 'db_config.json' GELADEN 💥
# ==============================================================================

CONFIG_FILE_NAME = "db_config.json"


def load_db_config():
    """Lädt die DB-Konfiguration aus einer externen JSON-Datei."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))

    if not hasattr(sys, '_MEIPASS'):
        base_path = os.path.dirname(base_path)

    config_path = os.path.join(base_path, CONFIG_FILE_NAME)

    default_config = {
        "host": "IHRE_SERVER_IP_HIER",
        "user": "planer_user",
        "password": "IhrPasswortHier",
        "database": "planer_db",
        "raise_on_warnings": False,  # Bleibt False
        "auth_plugin": "mysql_native_password"
    }

    if not os.path.exists(config_path):
        print(f"FEHLER: Konfigurationsdatei nicht gefunden.")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            msg = (f"Eine Standard-Konfigurationsdatei wurde erstellt: {config_path}\n\n"
                   "BITTE BEARBEITEN SIE DIESE DATEI mit Ihren Datenbank-Zugangsdaten und starten Sie das Programm neu.")
            print(msg)
            raise ConnectionError(msg)
        except Exception as e:
            msg = f"Konnte keine Standard-Konfigurationsdatei erstellen: {e}\nBitte erstellen Sie die Datei 'db_config.json' manuell im Programmverzeichnis."
            print(msg)
            raise ConnectionError(msg)

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        config["raise_on_warnings"] = False

        if config["host"] == "IHRE_SERVER_IP_HIER" or config["password"] == "IhrPasswortHier":
            msg = f"BITTE BEARBEITEN SIE 'db_config.json' mit Ihren Datenbank-Zugangsdaten."
            print(msg)
            raise ConnectionError(msg)

        return config
    except json.JSONDecodeError:
        msg = f"FEHLER: Die Datei '{config_path}' enthält ungültiges JSON."
        print(msg)
        raise ConnectionError(msg)
    except KeyError:
        msg = f"FEHLER: Die Datei '{config_path}' ist unvollständig. Stellen Sie sicher, dass alle Schlüssel vorhanden sind."
        print(msg)
        raise ConnectionError(msg)
    except Exception as e:
        msg = f"Ein unerwarteter Fehler beim Lesen der Konfiguration ist aufgetreten: {e}"
        print(msg)
        raise ConnectionError(msg)


try:
    DB_CONFIG = load_db_config()
except Exception as e:
    DB_CONFIG = None
    raise

# --- INNOVATION: Lazy-Loading des Connection-Pools ---

# Global-Variablen für den Pool und ein Lock
db_pool = None
_pool_init_lock = threading.Lock()
_db_initialized = False  # Flag, um initialize_db() nur einmal auszuführen


# ==============================================================================
# --- POOL- UND VERBINDUNGS-LOGIK (LAZY LOADING) ---
# ==============================================================================

def create_connection():
    """
    Stellt eine Verbindung aus dem Pool her.
    Initialisiert den Pool "lazy" (erst bei der ersten Anfrage),
    um den Programmstart zu beschleunigen.
    Initialisiert das DB-Schema (Tabellen) einmalig nach Pool-Erstellung.
    """
    global db_pool, _db_initialized

    # 1. Schnelle Prüfung (ohne Lock)
    if db_pool is not None:
        try:
            return db_pool.get_connection()
        except mysql.connector.Error as err:
            print(f"❌ Fehler beim Abrufen einer Verbindung aus dem Pool: {err}")
            return None
        except Exception as e:
            print(f"❌ Unerwarteter Fehler beim Abrufen der Verbindung: {e}")
            db_pool = None
            return None

    # 2. Pool existiert nicht. Wir müssen ihn erstellen (Thread-sicher).
    with _pool_init_lock:
        # 3. Erneute Prüfung (Double-Checked Locking)
        if db_pool is not None:
            try:
                return db_pool.get_connection()
            except mysql.connector.Error as err:
                print(f"❌ Fehler beim Abrufen einer Verbindung aus dem Pool (nach Lock): {err}")
                return None

        # 4. Der Pool muss jetzt wirklich erstellt werden.
        try:
            print("Versuche, den Datenbank-Connection-Pool (lazy) zu erstellen...")
            if DB_CONFIG is None:
                raise ConnectionError("DB_CONFIG wurde aufgrund eines Fehlers nicht geladen.")

            db_pool = pooling.MySQLConnectionPool(pool_name="dhf_pool",
                                                  pool_size=10,
                                                  **DB_CONFIG)
            print("✅ Datenbank-Connection-Pool erfolgreich erstellt.")

            # 5. Datenbank-Schema (Tabellen) initialisieren
            if not _db_initialized:
                print("[DB Connection] Führe erstmalige Schema-Initialisierung (initialize_db) durch...")
                conn = None
                try:
                    conn = db_pool.get_connection()

                    # Ruft die ausgelagerte Funktion aus db_schema.py auf
                    db_schema._run_initialize_db(conn, DB_CONFIG)

                    _db_initialized = True
                    print("✅ Schema-Initialisierung abgeschlossen.")
                except Exception as init_e:
                    print(f"❌ KRITISCHER FEHLER bei initialize_db: {init_e}")
                    db_pool = None
                    raise init_e
                finally:
                    if conn and conn.is_connected():
                        conn.close()

            # 6. Finale Verbindung zurückgeben
            return db_pool.get_connection()

        except mysql.connector.Error as err:
            print(f"❌ KRITISCHER FEHLER beim Erstellen des Connection-Pools: {err}")
            print("Überprüfen Sie Ihre 'db_config.json' und die Erreichbarkeit der Datenbank.")
            db_pool = None
            raise ConnectionError(f"Fehler beim Erstellen des DB-Pools: {err}")
        except Exception as e:
            print(f"❌ KRITISCHER FEHLER (Allgemein) beim Initialisieren von db_connection: {e}")
            db_pool = None
            raise


def prewarm_connection_pool():
    """
    Ruft create_connection() einmal auf, um den Pool und das Schema im Hintergrund
    zu initialisieren.
    """
    global _db_initialized
    if db_pool is not None and _db_initialized:
        print("[DB Connection] Pre-Warming übersprungen (Pool & Schema bereits initialisiert).")
        return

    print("[DB Connection] Starte Pre-Warming des Connection-Pools im Hintergrund...")
    conn = None
    try:
        conn = create_connection()
        if conn:
            print("[DB Connection] Pre-Warming erfolgreich. Pool und Schema sind jetzt initialisiert.")
        else:
            print("[DB Connection] Pre-Warming fehlgeschlagen (create_connection gab None zurück).")
    except Exception as e:
        print(f"[DB Connection] Pre-Warming THREAD FEHLER: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()


def close_pool():
    print("Der Datenbank-Connection-Pool wird bei Programmende verwaltet.")


def initialize_db():
    """
    Öffentlicher Wrapper, der sicherstellt, dass die Initialisierung
    über den 'create_connection'-Mechanismus läuft.
    """
    print("Starte öffentliche initialize_db()...")
    conn = create_connection()
    if conn:
        print("DB-Verbindung für initialize_db() erhalten, Schema sollte bereits initialisiert sein.")
        conn.close()
    else:
        print("Fehler beim Abrufen der DB-Verbindung für initialize_db().")
        raise ConnectionError("DB-Initialisierung fehlgeschlagen.")