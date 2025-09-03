import pandas as pd
import random
import os

# ==============================================================================
# --- KONFIGURATION ---
# ==============================================================================
# Gib hier den Namen der CSV-Datei an, die als Vorlage dienen soll.
# Diese Datei muss sich im selben Ordner wie das Skript befinden.
SOURCE_CSV_NAME = "data_2025-08-15_13-17-02.csv"

# Gib hier an, für welchen Spieltag die Testdaten generiert werden sollen.
# Das Skript simuliert die Punkte von Spieltag 1 bis zu diesem Wert.
TARGET_GAME_DAY = 2 # Beispiel: 1, 2, 3, ...
# ==============================================================================

def generate_test_data():
    """
    Liest eine Quell-CSV, simuliert die Punkte bis zu einem Ziel-Spieltag
    und speichert das Ergebnis in einer neuen Datei.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(script_dir, SOURCE_CSV_NAME)
    output_dir = os.path.join(script_dir, "testfiles")

    # Stelle sicher, dass der Quell- und Zielordner existiert
    if not os.path.exists(source_path):
        print(f"❌ FEHLER: Die Quelldatei '{SOURCE_CSV_NAME}' wurde nicht im Skript-Verzeichnis gefunden.")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Lese Quelldatei: {SOURCE_CSV_NAME}")
    df = pd.read_csv(source_path, sep=';')

    print(f"Simuliere Punkte für {TARGET_GAME_DAY} Spieltage...")

    # Setze die Punkte aller Spieler initial auf 0
    df['Punkte'] = 0

    # Simuliere jeden Spieltag bis zum Ziel-Spieltag
    for i in range(1, TARGET_GAME_DAY + 1):
        # Addiere für jeden Spieler eine zufällige Punktzahl für diesen Spieltag
        # lambda row: ... wird auf jede Zeile des DataFrames angewendet
        df['Punkte'] += df.apply(lambda row: random.randint(0, 16), axis=1)
        print(f"  -> Spieltag {i} simuliert.")

    # Erstelle den neuen Dateinamen und Speicherpfad
    output_filename = f"test_data_spieltag_{TARGET_GAME_DAY}.csv"
    output_path = os.path.join(output_dir, output_filename)

    # Speichere das Ergebnis als neue CSV-Datei
    df.to_csv(output_path, sep=';', index=False, encoding='utf-8')

    print(f"\n✅ ERFOLG: Test-Datei wurde erfolgreich erstellt!")
    print(f"   -> Gespeichert unter: {output_path}")
    print(f"   -> Gesamtpunkte simuliert für Spieltag: {TARGET_GAME_DAY}")

if __name__ == "__main__":
    generate_test_data()
