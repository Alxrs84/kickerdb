import sqlite3
import pandas as pd
import os
import glob
import shutil

# ==============================================================================
# --- KONFIGURATION ---
# ==============================================================================
CURRENT_SEASON_NAME = "2025/2026"

# STEUERUNG: Gib hier die Spieltagsnummer an, die verarbeitet werden soll.
# DIESES SKRIPT FUNKTIONIERT NUR, WENN HIER EINE ZAHL EINGETRAGEN IST.
PROCESS_GAME_DAY_NUMBER = 9 # Beispiel: 1, 2, 3, ...

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "kicker_main.db")
# NEUE ORDNERSTRUKTUR
PROCESS_DIR = os.path.join(SCRIPT_DIR, "process_gameday")
DONE_DIR = os.path.join(PROCESS_DIR, "done")
# ==============================================================================

def get_db_connection(path):
    try:
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Fehler beim Verbinden mit der Datenbank unter {path}: {e}")
        return None

def find_latest_csv(directory):
    search_pattern = os.path.join(directory, 'data_*.csv')
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_last_total_points(conn, season_id):
    """Holt die letzten bekannten Gesamtpunkte für jeden Spieler in der aktuellen Saison."""
    if not season_id:
        return {}
    query = """
        WITH LastStats AS (
            SELECT psd.player_id, ps.gesamtpunkte,
                   ROW_NUMBER() OVER(PARTITION BY psd.player_id ORDER BY gd.game_day_number DESC) as rn
            FROM player_stats ps
            JOIN player_seasonal_details psd ON ps.player_seasonal_details_id = psd.id
            JOIN game_days gd ON ps.game_day_id = gd.game_day_id
            WHERE psd.season_id = ?
        )
        SELECT player_id, gesamtpunkte FROM LastStats WHERE rn = 1;
    """
    df = pd.read_sql_query(query, conn, params=(season_id,))
    return pd.Series(df.gesamtpunkte.values, index=df.player_id).to_dict()

def main():
    if PROCESS_GAME_DAY_NUMBER is None:
        print("Fehler: Bitte geben Sie in der Konfiguration eine Spieltagsnummer an.")
        return

    os.makedirs(PROCESS_DIR, exist_ok=True)
    os.makedirs(DONE_DIR, exist_ok=True)

    print(f"Starte Verarbeitung für Spieltag {PROCESS_GAME_DAY_NUMBER} der Saison {CURRENT_SEASON_NAME}...")
    
    csv_path = find_latest_csv(PROCESS_DIR)
    if not csv_path:
        print(f"INFO: Keine CSV-Datei im Ordner '{PROCESS_DIR}' zur Verarbeitung gefunden. Skript beendet.")
        return
    
    print(f"INFO: Verarbeite Datei: {os.path.basename(csv_path)}")

    DB_TEMP_PATH = DB_PATH + ".tmp"
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Original-Datenbank '{DB_PATH}' nicht gefunden.")
        return
    
    conn_read = get_db_connection(DB_PATH)
    if not conn_read: return

    try:
        cursor_read = conn_read.cursor()
        cursor_read.execute("SELECT season_id FROM seasons WHERE season_name = ?", (CURRENT_SEASON_NAME,))
        res = cursor_read.fetchone()
        if not res:
            raise ValueError(f"Saison '{CURRENT_SEASON_NAME}' nicht gefunden. Bitte zuerst das Stammdaten-Skript ausführen.")
        season_id = res['season_id']

        last_points_map = get_last_total_points(conn_read, season_id)
        conn_read.close()

        df_csv_raw = pd.read_csv(csv_path, sep=';')
        df_csv = df_csv_raw[df_csv_raw['Marktwert'] != 999000000].copy()
        df_csv['Punkte'] = pd.to_numeric(df_csv['Punkte'], errors='coerce').fillna(0).astype(float)
        df_csv['Notendurchschnitt'] = pd.to_numeric(df_csv['Notendurchschnitt'], errors='coerce').fillna(0.0).astype(float)


        any_points_changed = False
        for _, row in df_csv.iterrows():
            last_total = last_points_map.get(row['ID'], 0.0)
            if row['Punkte'] != last_total:
                any_points_changed = True
                break
        
        if not any_points_changed:
            print("INFO: Keine Punkteveränderungen in der CSV-Datei festgestellt. Es wird kein neuer Spieltag angelegt.")
            return
        
        shutil.copy2(DB_PATH, DB_TEMP_PATH)
        conn_write = get_db_connection(DB_TEMP_PATH)
        if not conn_write: return

        with conn_write:
            cursor_write = conn_write.cursor()
            
            # KORREKTUR: 'id' wurde zu 'game_day_id' geändert
            cursor_write.execute("SELECT game_day_id FROM game_days WHERE season_id = ? AND game_day_number = ?", (season_id, PROCESS_GAME_DAY_NUMBER))
            if cursor_write.fetchone():
                raise sqlite3.IntegrityError(f"Spieltag {PROCESS_GAME_DAY_NUMBER} wurde bereits verarbeitet.")

            cursor_write.execute("INSERT INTO game_days (season_id, game_day_number) VALUES (?, ?)", (season_id, PROCESS_GAME_DAY_NUMBER))
            # HINWEIS: game_day_id ist jetzt die Spieltagsnummer selbst, nicht mehr lastrowid
            game_day_id = PROCESS_GAME_DAY_NUMBER
            
            points_processed_count = 0
            for _, row in df_csv.iterrows():
                cursor_write.execute("SELECT id FROM player_seasonal_details WHERE player_id = ? AND season_id = ?", (row['ID'], season_id))
                res_details = cursor_write.fetchone()
                if not res_details: continue
                
                seasonal_details_id = res_details['id']
                last_total = last_points_map.get(row['ID'], 0.0)
                spieltagspunkte = row['Punkte'] - last_total
                
                cursor_write.execute("""
                    INSERT INTO player_stats (player_seasonal_details_id, game_day_id, points, grade, gesamtpunkte)
                    VALUES (?, ?, ?, ?, ?)
                """, (seasonal_details_id, game_day_id, spieltagspunkte, row['Notendurchschnitt'], row['Punkte']))
                points_processed_count += 1

            print(f"\nSpieltag {PROCESS_GAME_DAY_NUMBER} erfolgreich verarbeitet.")
            print(f"Es wurden Punkteeinträge für {points_processed_count} Spieler gespeichert.")

        conn_write.close()
        os.replace(DB_TEMP_PATH, DB_PATH)
        print("Datenbank erfolgreich aktualisiert.")

        shutil.move(csv_path, os.path.join(DONE_DIR, os.path.basename(csv_path)))
        print(f"Datei '{os.path.basename(csv_path)}' wurde in den 'done' Ordner verschoben.")

    except (sqlite3.Error, FileNotFoundError, ValueError, Exception) as e:
        print(f"\n--- FEHLER! ---")
        print(f"Ein Fehler ist aufgetreten: {e}")
        print("Das Update wurde abgebrochen. Die Original-Datenbank wurde nicht verändert.")
        if 'conn_read' in locals() and conn_read: conn_read.close()
        if 'conn_write' in locals() and conn_write: conn_write.close()
        if os.path.exists(DB_TEMP_PATH): os.remove(DB_TEMP_PATH)

if __name__ == "__main__":
    main()
