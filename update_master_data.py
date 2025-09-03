import sqlite3
import pandas as pd
import os
import glob
import shutil

# ==============================================================================
# --- KONFIGURATION ---
# ==============================================================================
CURRENT_SEASON_NAME = "2025/2026"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "kicker_main.db")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "autodownload")
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

def get_current_state(conn, season_id):
    """Holt den aktuellen Stand der Spielerdaten für die Saison aus der DB."""
    if not season_id:
        return {}
    query = "SELECT player_id, club, position FROM player_seasonal_details WHERE season_id = ? AND is_active = 1"
    df = pd.read_sql_query(query, conn, params=(season_id,))
    return {row['player_id']: {'club': row['club'], 'position': row['position']} for _, row in df.iterrows()}

def main():
    print("Starte Skript zur Aktualisierung der Spieler-Stammdaten...")
    
    DB_TEMP_PATH = DB_PATH + ".tmp"
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Original-Datenbank '{DB_PATH}' nicht gefunden.")
        return
    shutil.copy2(DB_PATH, DB_TEMP_PATH)
    
    conn = get_db_connection(DB_TEMP_PATH)
    if not conn: return

    try:
        csv_path = find_latest_csv(DOWNLOAD_DIR)
        if not csv_path:
            raise FileNotFoundError(f"Keine CSV-Datei im Verzeichnis '{DOWNLOAD_DIR}' gefunden.")
        
        print(f"INFO: Verwendete CSV-Datei: {os.path.basename(csv_path)}")
        
        df_csv_raw = pd.read_csv(csv_path, sep=';')
        print(f"INFO: CSV enthält insgesamt {len(df_csv_raw)} Spieler.")
        
        df_csv = df_csv_raw[df_csv_raw['Marktwert'] != 999000000].copy()
        print(f"INFO: {len(df_csv_raw) - len(df_csv)} Spieler mit Platzhalter-Marktwert werden ignoriert.")
        
        df_csv['Marktwert'] = pd.to_numeric(df_csv['Marktwert'], errors='coerce').fillna(0).astype(int)
        
        with conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT season_id FROM seasons WHERE season_name = ?", (CURRENT_SEASON_NAME,))
            res = cursor.fetchone()
            season_id = res['season_id'] if res else None
            if not season_id:
                cursor.execute("INSERT INTO seasons (season_name) VALUES (?)", (CURRENT_SEASON_NAME,))
                season_id = cursor.lastrowid

            state_before = get_current_state(conn, season_id)
            ids_before = set(state_before.keys())
            ids_csv = set(df_csv['ID'])

            cursor.execute("UPDATE player_seasonal_details SET is_active = 0 WHERE season_id = ?", (season_id,))
            
            changed_club_or_pos = 0
            for _, row in df_csv.iterrows():
                player_id = row['ID']
                
                if player_id in state_before:
                    if (state_before[player_id]['club'] != row['Verein'] or
                        state_before[player_id]['position'] != row['Position']):
                        changed_club_or_pos += 1
                
                cursor.execute("INSERT OR IGNORE INTO players (player_id, first_name, last_name) VALUES (?, ?, ?)", (row['ID'], row['Vorname'], row['Nachname']))
                
                cursor.execute("""
                    INSERT INTO player_seasonal_details (player_id, season_id, club, position, market_value, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(player_id, season_id) DO UPDATE SET
                        club = excluded.club, position = excluded.position, market_value = excluded.market_value, is_active = 1;
                """, (row['ID'], season_id, row['Verein'], row['Position'], row['Marktwert']))

            newly_added_players = len(ids_csv - ids_before)
            deactivated_players = len(ids_before - ids_csv)

            print("\n--- Update-Zusammenfassung ---")
            print(f"Verarbeitete Saison: {CURRENT_SEASON_NAME}")
            print(f"Anzahl gültiger Spieler in CSV: {len(ids_csv)}")
            print("-" * 30)
            print(f"✅ Neu hinzugefügte Spieler: {newly_added_players}")
            print(f"🔄 Spieler mit Vereins- oder Positionswechsel: {changed_club_or_pos}")
            print(f"❌ Deaktivierte Spieler (Liga verlassen): {deactivated_players}")
            print("-" * 30)
            print("INFO: Es wurde nur eine Stammdaten-Aktualisierung durchgeführt.")
            print("INFO: Es wurden keine Spieltagspunkte berechnet oder gespeichert.")
            print("--- Ende der Zusammenfassung ---\n")

        conn.close()
        os.replace(DB_TEMP_PATH, DB_PATH)
        print("Datenbank erfolgreich aktualisiert.")

    except (sqlite3.Error, FileNotFoundError, Exception) as e:
        print(f"\n--- FEHLER! ---")
        print(f"Ein Fehler ist aufgetreten: {e}")
        print("Das Update wurde abgebrochen. Die Original-Datenbank wurde nicht verändert.")
        if conn: conn.close()
        if os.path.exists(DB_TEMP_PATH): os.remove(DB_TEMP_PATH)

if __name__ == "__main__":
    main()
