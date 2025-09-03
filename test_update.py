import sqlite3
import pandas as pd
import os
import glob
import time

# ==============================================================================
# --- KONFIGURATION ---
# ==============================================================================
DB_PATH = "kicker_main.db"
DOWNLOAD_DIR = "autodownload"
CURRENT_SEASON_NAME = "2025/2026"
PREVIOUS_SEASON_NAME = "2024/2025"
# ==============================================================================

def find_latest_csv(directory):
    """Sucht und gibt die neueste CSV-Datei im angegebenen Verzeichnis zurück."""
    search_pattern = os.path.join(directory, 'data_*.csv')
    files = glob.glob(search_pattern)
    if not files:
        return None
    return max(files, key=os.path.getctime)

def run_tests():
    """Führt eine Reihe von Tests durch, um die Datenintegrität nach dem Update zu prüfen."""
    print("Starte Tests für das Pre-Saison-Update...")
    print("Warte 1 Sekunde zur Synchronisierung...")
    time.sleep(1)

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        integrity_check = cursor.execute("PRAGMA integrity_check").fetchone()
        if integrity_check[0] != 'ok':
            print(f"❌ KRITISCHER FEHLER: Datenbank-Integritätsprüfung fehlgeschlagen! Ergebnis: {integrity_check[0]}")
            return
        print("✅ Datenbank-Integritätsprüfung bestanden.")
        
        latest_csv = find_latest_csv(DOWNLOAD_DIR)
        if not latest_csv:
            print(f"❌ FEHLER: Keine CSV-Datei in '{DOWNLOAD_DIR}' gefunden.")
            return
        
        df_csv_raw = pd.read_csv(latest_csv, sep=';')
        df_csv = df_csv_raw[df_csv_raw['Marktwert'] != 999000000].copy()
        print(f"Referenz-CSV für Tests: {os.path.basename(latest_csv)} ({len(df_csv)} gültige Spieler)")

        # --- Test 1: Existenz der neuen Saison ---
        print("\n--- Test 1: Wurde die neue Saison angelegt? ---")
        cursor.execute("SELECT season_id FROM seasons WHERE season_name = ?", (CURRENT_SEASON_NAME,))
        season_res = cursor.fetchone()
        if season_res:
            season_id = season_res[0]
            print(f"✅ ERFOLG: Saison '{CURRENT_SEASON_NAME}' (ID: {season_id}) wurde in der Datenbank gefunden.")
        else:
            print(f"❌ FEHLER: Saison '{CURRENT_SEASON_NAME}' konnte nicht gefunden werden.")
            return

        # --- Test 2: Anzahl der aktiven Spieler ---
        print("\n--- Test 2: Stimmt die Anzahl der aktiven Spieler? ---")
        cursor.execute("SELECT COUNT(*) FROM player_seasonal_details WHERE season_id = ? AND is_active = 1", (season_id,))
        active_players_in_db = cursor.fetchone()[0]
        players_in_csv = len(df_csv)
        print(f"Anzahl gültiger Spieler in CSV-Datei: {players_in_csv}")
        print(f"Anzahl als 'aktiv' markierter Spieler in DB: {active_players_in_db}")
        if players_in_csv == active_players_in_db:
            print("✅ ERFOLG: Die Anzahl der Spieler stimmt überein.")
        else:
            print("❌ FEHLER: Die Anzahl der Spieler stimmt NICHT überein.")

        # --- Test 3: Überprüfung eines Spielers, der die Liga verlassen hat ---
        print("\n--- Test 3: Wurden Spieler, die die Liga verlassen haben, korrekt deaktiviert? ---")
        # Logik bleibt gleich, da sie auf Pandas DataFrames basiert, die wir sowieso benötigen
        prev_season_id_df = pd.read_sql("SELECT season_id FROM seasons WHERE season_name = ?", conn, params=(PREVIOUS_SEASON_NAME,))
        if prev_season_id_df.empty:
            print("INFO: Vorherige Saison nicht gefunden, Test wird übersprungen.")
        else:
            prev_season_id = prev_season_id_df.iloc[0, 0]
            players_last_season_df = pd.read_sql("SELECT player_id FROM player_seasonal_details WHERE season_id = ?", conn, params=(prev_season_id,))
            players_last_season = set(players_last_season_df['player_id'])
            players_current_season = set(df_csv['ID'])
            leavers = players_last_season - players_current_season
            
            if not leavers:
                print("INFO: Keine Spieler gefunden, die die Liga verlassen haben. Test wird übersprungen.")
            else:
                leaver_id = list(leavers)[0]
                print(f"Teste mit Spieler '{leaver_id}', der die Liga verlassen hat...")
                cursor.execute("SELECT is_active FROM player_seasonal_details WHERE player_id = ? AND season_id = ?", (leaver_id, season_id))
                leaver_status_res = cursor.fetchone()
                if leaver_status_res is None:
                     print("✅ ERFOLG: Für den Spieler wurde korrekterweise kein Eintrag für die neue Saison angelegt.")
                elif leaver_status_res[0] == 0:
                    print("✅ ERFOLG: Der Spieler wurde für die neue Saison korrekt als inaktiv (is_active = 0) markiert.")
                else:
                    print(f"❌ FEHLER: Der Spieler '{leaver_id}' ist für die neue Saison fälschlicherweise noch als aktiv markiert.")

        # --- Test 4: Marktwert-Stichprobe ---
        print("\n--- Test 4: Stimmt der Marktwert eines zufälligen Spielers? ---")
        if df_csv.empty:
            print("INFO: Keine gültigen Spieler in der CSV, Test wird übersprungen.")
        else:
            random_player_csv = df_csv.sample(1).iloc[0]
            player_id = random_player_csv['ID']
            market_value_csv = int(random_player_csv['Marktwert'])
            
            print(f"Teste mit Spieler '{random_player_csv['Angezeigter Name']}' (ID: {player_id})")
            print(f"Marktwert laut CSV: {market_value_csv}")

            cursor.execute("SELECT market_value FROM player_seasonal_details WHERE player_id = ? AND season_id = ?", (player_id, season_id))
            market_value_res = cursor.fetchone()
            
            if market_value_res is None:
                print("❌ FEHLER: Spieler wurde in der Datenbank nicht gefunden.")
            else:
                market_value_db = market_value_res[0]
                print(f"Marktwert laut DB:   {market_value_db}")
                if market_value_csv == market_value_db:
                    print("✅ ERFOLG: Der Marktwert stimmt überein.")
                else:
                    print("❌ FEHLER: Der Marktwert stimmt NICHT überein.")

    except (sqlite3.Error, Exception) as e:
        print(f"❌ EIN ALLGEMEINER FEHLER IST AUFGETRETEN: {e}")
    finally:
        if conn:
            conn.close()
            print("\nAlle Tests abgeschlossen.")

if __name__ == "__main__":
    run_tests()
