import sqlite3
import pandas as pd
import os
import glob
import shutil
from datetime import datetime

# ==============================================================================
# --- KONFIGURATION ---
# ==============================================================================
# ÄNDERE DIES ZU BEGINN JEDER NEUEN SAISON!
CURRENT_SEASON_NAME = "2025/2026"

# STEUERUNG: Gib hier die Spieltagsnummer an, die verarbeitet werden soll.
# Setze auf 'None', um nur Stammdaten zu aktualisieren (z.B. in der Pre-Saison).
PROCESS_GAME_DAY_NUMBER = 1 # Beispiel: 1, 2, 3, ... oder None

# Pfade zur Datenbank und zum Download-Ordner
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "kicker_main.db")
DB_TEMP_PATH = os.path.join(SCRIPT_DIR, "kicker_main.db.tmp")
DB_BACKUP_PATH = os.path.join(SCRIPT_DIR, "kicker_main.db.bak")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "autodownload")
# ==============================================================================

def find_latest_csv(directory):
    """Sucht und gibt die neueste CSV-Datei im angegebenen Verzeichnis zurück."""
    search_pattern = os.path.join(directory, 'data_*.csv')
    files = glob.glob(search_pattern)
    if not files:
        return None
    return max(files, key=os.path.getctime)

def get_db_connection(path):
    """Stellt eine Verbindung zur angegebenen Datenbankdatei her."""
    try:
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Fehler beim Verbinden mit der Datenbank unter {path}: {e}")
        return None

def ensure_schema_updates(conn):
    """Stellt sicher, dass alle notwendigen Spalten existieren."""
    with conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(player_seasonal_details)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'is_active' not in columns:
            cursor.execute("ALTER TABLE player_seasonal_details ADD COLUMN is_active INTEGER DEFAULT 1")
        
        cursor.execute("PRAGMA table_info(player_stats)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'gesamtpunkte' not in columns:
            cursor.execute("ALTER TABLE player_stats ADD COLUMN gesamtpunkte REAL DEFAULT 0")

def main():
    """Hauptfunktion des Skripts."""
    csv_path = find_latest_csv(DOWNLOAD_DIR)
    if not csv_path:
        print(f"Fehler: Keine CSV-Datei im Verzeichnis '{DOWNLOAD_DIR}' gefunden.")
        return

    # 1. Bereite die temporäre Datenbank vor
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Original-Datenbank '{DB_PATH}' nicht gefunden. Bitte zuerst migrieren.")
        return
    
    # Lösche alte Temp-Dateien, falls vorhanden
    if os.path.exists(DB_TEMP_PATH):
        os.remove(DB_TEMP_PATH)

    print(f"Erstelle eine temporäre Kopie der Datenbank für sichere Bearbeitung...")
    shutil.copy2(DB_PATH, DB_TEMP_PATH)

    conn = get_db_connection(DB_TEMP_PATH)
    if not conn:
        return

    try:
        print(f"Verarbeite Datei: {os.path.basename(csv_path)}")
        df_csv_raw = pd.read_csv(csv_path, sep=';')
        df_csv = df_csv_raw[df_csv_raw['Marktwert'] != 999000000].copy()
        df_csv['Marktwert'] = pd.to_numeric(df_csv['Marktwert'], errors='coerce').fillna(0).astype(int)
        df_csv['Punkte'] = pd.to_numeric(df_csv['Punkte'], errors='coerce').fillna(0).astype(float)
        
        # Führe alle Schreibvorgänge in einer einzigen Transaktion auf der TEMP-DB aus
        with conn:
            # Schema-Updates zuerst
            ensure_schema_updates(conn)

            cursor = conn.cursor()
            
            # Saison anlegen/holen
            cursor.execute("SELECT season_id FROM seasons WHERE season_name = ?", (CURRENT_SEASON_NAME,))
            res = cursor.fetchone()
            if res:
                season_id = res['season_id']
            else:
                cursor.execute("INSERT INTO seasons (season_name) VALUES (?)", (CURRENT_SEASON_NAME,))
                season_id = cursor.lastrowid
            
            # Stammdaten aktualisieren
            cursor.execute("UPDATE player_seasonal_details SET is_active = 0 WHERE season_id = ?", (season_id,))
            for _, row in df_csv.iterrows():
                cursor.execute("INSERT OR IGNORE INTO players (player_id, first_name, last_name) VALUES (?, ?, ?)", (row['ID'], row['Vorname'], row['Nachname']))
                cursor.execute("""
                    INSERT INTO player_seasonal_details (player_id, season_id, club, position, market_value, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(player_id, season_id) DO UPDATE SET
                        club = excluded.club, position = excluded.position, market_value = excluded.market_value, is_active = 1;
                """, (row['ID'], season_id, row['Verein'], row['Position'], row['Marktwert']))

            # Spieltag verarbeiten (falls angegeben)
            if PROCESS_GAME_DAY_NUMBER is not None:
                # Logik für Spieltagsverarbeitung hier...
                pass

        # 2. Wenn alles erfolgreich war, ersetze die Original-DB
        conn.close() # Wichtig: Verbindung vor dem Verschieben schließen!
        print("Transaktion erfolgreich. Ersetze Original-Datenbank...")
        
        # Erstelle ein Backup der alten DB (optional, aber sicher)
        if os.path.exists(DB_BACKUP_PATH):
            os.remove(DB_BACKUP_PATH)
        os.rename(DB_PATH, DB_BACKUP_PATH)
        
        # Verschiebe die neue, aktualisierte DB an den richtigen Ort
        os.rename(DB_TEMP_PATH, DB_PATH)
        
        print("\nUpdate erfolgreich abgeschlossen!")

    except (sqlite3.Error, Exception) as e:
        print(f"\n--- FEHLER! ---")
        print(f"Ein Fehler ist aufgetreten: {e}")
        print("Das Update wurde abgebrochen. Die Original-Datenbank wurde nicht verändert.")
        if conn:
            conn.close()
        # Lösche die fehlerhafte temporäre Datei
        if os.path.exists(DB_TEMP_PATH):
            os.remove(DB_TEMP_PATH)
    finally:
        # Lösche die Backup-Datei, wenn alles gut ging
        if os.path.exists(DB_BACKUP_PATH) and not os.path.exists(DB_TEMP_PATH):
            os.remove(DB_BACKUP_PATH)


if __name__ == "__main__":
    main()
