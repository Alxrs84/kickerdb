import sqlite3
import pandas as pd

# --- Konfiguration ---
OLD_DB_PATH = 'kicker-data.sqlite'
NEW_DB_PATH = 'kicker_main.db'
SEASON_NAME_FOR_OLD_DATA = "2024/2025" # Muss mit dem Namen im Migrationsskript übereinstimmen

def run_tests():
    """Verbindet sich zu beiden Datenbanken und führt eine Reihe von Tests durch."""
    try:
        conn_old = sqlite3.connect(OLD_DB_PATH)
        conn_new = sqlite3.connect(NEW_DB_PATH)
        print("✅ Datenbankverbindungen erfolgreich hergestellt.")
    except sqlite3.Error as e:
        print(f"❌ Datenbankverbindungsfehler: {e}")
        return

    # --- Test 1: Anzahl der Einträge vergleichen ---
    print("\n--- Test 1: Anzahl der Einträge ---")
    try:
        # Alte DB Zählungen
        old_player_count = pd.read_sql("SELECT COUNT(*) FROM players", conn_old).iloc[0, 0]
        old_stats_count = pd.read_sql("SELECT COUNT(*) FROM player_points", conn_old).iloc[0, 0]

        # Neue DB Zählungen
        new_player_count = pd.read_sql("SELECT COUNT(*) FROM players", conn_new).iloc[0, 0]
        new_seasonal_details_count = pd.read_sql("SELECT COUNT(*) FROM player_seasonal_details", conn_new).iloc[0, 0]
        new_stats_count = pd.read_sql("SELECT COUNT(*) FROM player_stats", conn_new).iloc[0, 0]

        print(f"Spieler in alter DB: {old_player_count}")
        print(f"Spieler in neuer DB ('players'): {new_player_count}")
        print(f"Saison-Details in neuer DB: {new_seasonal_details_count}")
        if old_player_count == new_player_count == new_seasonal_details_count:
            print("✅ Spieler-Anzahl stimmt überein.")
        else:
            print("❌ FEHLER: Spieler-Anzahl stimmt NICHT überein.")

        print(f"\nStatistik-Einträge in alter DB: {old_stats_count}")
        print(f"Statistik-Einträge in neuer DB: {new_stats_count}")
        if old_stats_count == new_stats_count:
            print("✅ Statistik-Anzahl stimmt überein.")
        else:
            print("❌ FEHLER: Statistik-Anzahl stimmt NICHT überein.")

    except pd.io.sql.DatabaseError as e:
        print(f"❌ FEHLER bei Zähl-Abfrage: {e}")


    # --- Test 2: Summe der Spieltagspunkte vergleichen ---
    print("\n--- Test 2: Summe der Spieltagspunkte ---")
    try:
        old_total_points = pd.read_sql("SELECT SUM(spieltagspunkte) FROM player_points", conn_old).iloc[0, 0]
        new_total_points = pd.read_sql("SELECT SUM(points) FROM player_stats", conn_new).iloc[0, 0]

        print(f"Summe der Punkte in alter DB: {old_total_points}")
        print(f"Summe der Punkte in neuer DB: {new_total_points}")

        if old_total_points == new_total_points:
            print("✅ Punktesumme stimmt exakt überein.")
        else:
            print("❌ FEHLER: Punktesumme stimmt NICHT überein.")
    except pd.io.sql.DatabaseError as e:
        print(f"❌ FEHLER bei Summen-Abfrage: {e}")


    # --- Test 3: Stichproben-Vergleich eines zufälligen Spielers ---
    print("\n--- Test 3: Stichproben-Vergleich ---")
    try:
        # Wähle einen zufälligen Spieler aus der alten DB, der Punkte hat
        random_player_id = pd.read_sql("SELECT player_id FROM player_points WHERE spieltagspunkte > 0 ORDER BY RANDOM() LIMIT 1", conn_old).iloc[0, 0]
        print(f"Teste mit zufälligem Spieler: {random_player_id}")

        # Daten aus alter DB holen
        old_player_df = pd.read_sql(f"SELECT * FROM players WHERE id = '{random_player_id}'", conn_old)
        old_points_df = pd.read_sql(f"SELECT * FROM player_points WHERE player_id = '{random_player_id}'", conn_old)
        
        # Daten aus neuer DB holen
        new_player_query = f"""
            SELECT
                p.player_id,
                p.first_name,
                p.last_name,
                psd.club,
                psd.position,
                psd.market_value
            FROM players p
            JOIN player_seasonal_details psd ON p.player_id = psd.player_id
            WHERE p.player_id = '{random_player_id}'
        """
        new_player_df = pd.read_sql(new_player_query, conn_new)

        new_points_query = f"""
            SELECT
                ps.game_day_id,
                ps.points
            FROM player_stats ps
            JOIN player_seasonal_details psd ON ps.player_seasonal_details_id = psd.id
            WHERE psd.player_id = '{random_player_id}'
        """
        new_points_df = pd.read_sql(new_points_query, conn_new)

        # Vergleiche
        print("\nAlte Spielerdaten:")
        print(old_player_df[['id', 'name_lang', 'verein', 'marktwert']].to_string(index=False))
        
        print("\nNeue Spielerdaten:")
        print(new_player_df[['player_id', 'first_name', 'last_name', 'club', 'market_value']].to_string(index=False))

        # Einfacher Vergleich
        if old_player_df['marktwert'].iloc[0] == new_player_df['market_value'].iloc[0]:
             print("✅ Marktwert der Stichprobe stimmt überein.")
        else:
             print("❌ FEHLER: Marktwert der Stichprobe stimmt NICHT überein.")

        if len(old_points_df) == len(new_points_df):
             print(f"✅ Anzahl der Spieltags-Einträge für Stichprobe ({len(old_points_df)}) stimmt überein.")
        else:
             print(f"❌ FEHLER: Anzahl der Spieltags-Einträge für Stichprobe stimmt NICHT überein ({len(old_points_df)} vs {len(new_points_df)}).")

    except (pd.io.sql.DatabaseError, IndexError) as e:
        print(f"❌ FEHLER bei Stichproben-Abfrage: {e}")


    # --- Verbindungen schließen ---
    conn_old.close()
    conn_new.close()

# --- Skript ausführen ---
if __name__ == "__main__":
    run_tests()
