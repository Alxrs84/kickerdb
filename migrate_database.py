import sqlite3
import pandas as pd

# --- KONFIGURATION ---
OLD_DB_PATH = 'kicker-data.sqlite'
NEW_DB_PATH = 'kicker_main.db'
SEASON_NAME_FOR_OLD_DATA = "2024/2025" # Passe dies bei Bedarf für die nächste Saison an

# --- 1. NEUE DATENBANK MIT DEM PERFEKTEN SCHEMA ERSTELLEN ---
def create_new_schema(conn):
    """Erstellt die 5 Tabellen im neuen, saisonübergreifenden Schema."""
    cursor = conn.cursor()
    print("Erstelle neues Datenbankschema...")

    cursor.execute('DROP TABLE IF EXISTS player_stats')
    cursor.execute('DROP TABLE IF EXISTS game_days')
    cursor.execute('DROP TABLE IF EXISTS player_seasonal_details')
    cursor.execute('DROP TABLE IF EXISTS seasons')
    cursor.execute('DROP TABLE IF EXISTS players')

    cursor.execute('''
        CREATE TABLE players (
            player_id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE seasons (
            season_id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_name TEXT UNIQUE
        )
    ''')
    cursor.execute('''
        CREATE TABLE player_seasonal_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT,
            season_id INTEGER,
            club TEXT,
            position TEXT,
            market_value INTEGER,
            is_active INTEGER DEFAULT 1,
            UNIQUE(player_id, season_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE game_days (
            game_day_id INTEGER PRIMARY KEY,
            season_id INTEGER,
            game_day_number INTEGER,
            FOREIGN KEY (season_id) REFERENCES seasons (season_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE player_stats (
            stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_seasonal_details_id INTEGER,
            game_day_id INTEGER,
            points INTEGER,
            grade REAL,
            gesamtpunkte REAL DEFAULT 0,
            FOREIGN KEY (player_seasonal_details_id) REFERENCES player_seasonal_details (id),
            FOREIGN KEY (game_day_id) REFERENCES game_days (game_day_id)
        )
    ''')
    conn.commit()
    print("Neues Schema erfolgreich erstellt.")

# --- 2. DATEN MIGRATION ---
def migrate_data():
    """Liest Daten aus der alten 3-Tabellen-DB und schreibt sie in die neue 5-Tabellen-DB."""
    try:
        conn_old = sqlite3.connect(OLD_DB_PATH)
        conn_new = sqlite3.connect(NEW_DB_PATH)
    except sqlite3.Error as e:
        print(f"Datenbankverbindungsfehler: {e}")
        return

    create_new_schema(conn_new)
    
    cursor_new = conn_new.cursor()
    
    print("Starte Datenmigration...")

    # Saison einfügen und season_id holen
    cursor_new.execute("INSERT OR IGNORE INTO seasons (season_name) VALUES (?)", (SEASON_NAME_FOR_OLD_DATA,))
    season_id = cursor_new.execute("SELECT season_id FROM seasons WHERE season_name = ?", (SEASON_NAME_FOR_OLD_DATA,)).fetchone()[0]

    # Lade Daten aus alten Tabellen
    df_players_old = pd.read_sql_query("SELECT * FROM players", conn_old)
    df_matchdays_old = pd.read_sql_query("SELECT * FROM matchdays", conn_old)
    df_points_old = pd.read_sql_query("SELECT * FROM player_points", conn_old)
    print("Daten aus alter Datenbank erfolgreich geladen.")

    # 1. 'players' Tabelle füllen
    for _, row in df_players_old.iterrows():
        cursor_new.execute("INSERT OR IGNORE INTO players (player_id, first_name, last_name) VALUES (?, ?, ?)",
                         (row['id'], row['vorname'], row['nachname']))

    # 2. 'player_seasonal_details' Tabelle füllen
    for _, row in df_players_old.iterrows():
        cursor_new.execute("""
            INSERT OR IGNORE INTO player_seasonal_details (player_id, season_id, club, position, market_value)
            VALUES (?, ?, ?, ?, ?)
        """, (row['id'], season_id, row['verein'], row['position'], row['marktwert']))

    # 3. 'game_days' Tabelle füllen und alte zu neuen IDs mappen
    game_day_id_map = {}
    for _, row in df_matchdays_old.iterrows():
        new_game_day_id = row['spieltag']
        game_day_id_map[row['id']] = new_game_day_id
        cursor_new.execute("INSERT OR IGNORE INTO game_days (game_day_id, season_id, game_day_number) VALUES (?, ?, ?)",
                         (new_game_day_id, season_id, row['spieltag']))

    # 4. 'player_stats' Tabelle füllen
    print("Füge Spieltags-Statistiken ein...")
    for _, row in df_points_old.iterrows():
        seasonal_details_id_res = cursor_new.execute("""
            SELECT id FROM player_seasonal_details WHERE player_id = ? AND season_id = ?
        """, (row['player_id'], season_id)).fetchone()
        
        if seasonal_details_id_res:
            seasonal_details_id = seasonal_details_id_res[0]
            new_game_day_id = game_day_id_map.get(row['matchday_id'])
            
            if new_game_day_id is not None:
                # KORREKTUR HIER: Füge jetzt auch 'gesamtpunkte' ein
                cursor_new.execute("""
                    INSERT INTO player_stats (player_seasonal_details_id, game_day_id, points, grade, gesamtpunkte)
                    VALUES (?, ?, ?, NULL, ?)
                """, (seasonal_details_id, new_game_day_id, row['spieltagspunkte'], row['gesamtpunkte']))

    conn_new.commit()
    conn_old.close()
    conn_new.close()
    print("\nDatenmigration erfolgreich abgeschlossen!")
    print(f"Deine geretteten Daten befinden sich jetzt in '{NEW_DB_PATH}'.")

# --- Skript ausführen ---
if __name__ == "__main__":
    migrate_data()
