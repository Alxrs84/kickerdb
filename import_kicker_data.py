import sqlite3
import csv

DB_PATH = "kicker-data.sqlite"
CSV_PATH = "autodownload/data_2024-12-23_10-17-03.csv"  # CSV während der Transferphase

# Datum und Spieltag (nur wenn es tatsächlich einen neuen Spieltag gibt)
# Wenn Sie noch nicht wissen, ob Sie einen neuen Spieltag anlegen, können Sie diesen Wert dynamisch festlegen oder weglassen
SPIELTAG_NUM = 15
SPIELTAG_DATUM = "2024-12-22 10:17:02"  # Beispiel

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Tabellen sicherstellen
cur.execute("""
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    vorname TEXT,
    nachname TEXT,
    name_kurz TEXT,
    name_lang TEXT,
    verein TEXT,
    position TEXT,
    marktwert INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS matchdays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spieltag INTEGER,
    datum_import TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS player_points (
    player_id TEXT,
    matchday_id INTEGER,
    gesamtpunkte REAL,
    spieltagspunkte REAL,
    PRIMARY KEY (player_id, matchday_id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (matchday_id) REFERENCES matchdays(id)
)
""")

# Schritt 1: CSV-Daten einlesen, ohne sofort zu schreiben
players_data = []
with open(CSV_PATH, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        players_data.append({
            'id': row['ID'],
            'vorname': row['Vorname'],
            'nachname': row['Nachname'],
            'name_kurz': row['Angezeigter Name (kurz)'],
            'name_lang': row['Angezeigter Name'],
            'verein': row['Verein'],
            'position': row['Position'],
            'marktwert': int(row['Marktwert']),
            'total_points': float(row['Punkte'])
        })

# Schritt 2: Prüfen, ob es eine Punktedifferenz gibt
any_points_changed = False

for p in players_data:
    player_id = p['id']
    total_points = p['total_points']

    # Letzten Gesamtpunktestand holen
    cur.execute("""
        SELECT p.gesamtpunkte
        FROM player_points p
        JOIN matchdays m ON p.matchday_id = m.id
        WHERE p.player_id = ?
        ORDER BY m.spieltag DESC
        LIMIT 1
    """, (player_id,))
    last_points_res = cur.fetchone()

    if last_points_res is None:
        # Noch kein Eintrag vorhanden -> jede Gesamtpunktzahl wäre "neu"
        if total_points != 0:
            # Wenn der Spieler neu ist und direkt Punkte hat, dann ist das eine Veränderung
            any_points_changed = True
    else:
        previous_points = last_points_res[0]
        if total_points != previous_points:
            # Punktedifferenz gefunden
            any_points_changed = True
            break

# Schritt 3: Entscheidung basierend auf `any_points_changed`
if any_points_changed:
    # Neuer Spieltag wird angelegt, falls noch nicht vorhanden
    cur.execute("SELECT id FROM matchdays WHERE spieltag = ?", (SPIELTAG_NUM,))
    res = cur.fetchone()
    if res is None:
        # Neuen Spieltag anlegen
        cur.execute("INSERT INTO matchdays (spieltag, datum_import) VALUES (?, ?)", (SPIELTAG_NUM, SPIELTAG_DATUM))
        matchday_id = cur.lastrowid
    else:
        matchday_id = res[0]

    # Punkte und Spieler aktualisieren
    for p in players_data:
        player_id = p['id']
        vorname = p['vorname']
        nachname = p['nachname']
        name_kurz = p['name_kurz']
        name_lang = p['name_lang']
        verein = p['verein']
        position = p['position']
        marktwert = p['marktwert']
        total_points = p['total_points']

        # Player einfügen oder aktualisieren
        cur.execute("SELECT id FROM players WHERE id = ?", (player_id,))
        player_exists = cur.fetchone()
        if player_exists is None:
            cur.execute("""
                INSERT INTO players (id, vorname, nachname, name_kurz, name_lang, verein, position, marktwert)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_id, vorname, nachname, name_kurz, name_lang, verein, position, marktwert))
        else:
            cur.execute("""
                UPDATE players
                SET vorname = ?, nachname = ?, name_kurz = ?, name_lang = ?, verein = ?, position = ?
                WHERE id = ?
            """, (vorname, nachname, name_kurz, name_lang, verein, position, player_id))

        # Spieltagspunkte berechnen
        cur.execute("""
            SELECT p.gesamtpunkte
            FROM player_points p
            JOIN matchdays m ON p.matchday_id = m.id
            WHERE p.player_id = ?
            ORDER BY m.spieltag DESC
            LIMIT 1
        """, (player_id,))
        last_points_res = cur.fetchone()

        if last_points_res is None:
            spieltagspunkte = total_points  # Spieler ist neu oder hat bisher 0 Punkte
        else:
            previous_points = last_points_res[0]
            spieltagspunkte = total_points - previous_points

        # Neue Punkte eintragen (Spieltag angelegt, also normaler Ablauf)
        cur.execute("""
            INSERT OR REPLACE INTO player_points (player_id, matchday_id, gesamtpunkte, spieltagspunkte)
            VALUES (?, ?, ?, ?)
        """, (player_id, matchday_id, total_points, spieltagspunkte))

    print(f"Daten für Spieltag {SPIELTAG_NUM} erfolgreich importiert!")
else:
    # Keine Punkteveränderung festgestellt -> kein neuer Spieltag
    # Nur `players` Tabelle updaten, um Vereins-/Positionsänderungen zu übernehmen
    for p in players_data:
        player_id = p['id']
        vorname = p['vorname']
        nachname = p['nachname']
        name_kurz = p['name_kurz']
        name_lang = p['name_lang']
        verein = p['verein']
        position = p['position']
        marktwert = p['marktwert']

        cur.execute("SELECT id FROM players WHERE id = ?", (player_id,))
        player_exists = cur.fetchone()
        if player_exists is None:
            # Neuer Spieler taucht ohne Punkteveränderung auf -> wir fügen ihn hinzu
            cur.execute("""
                INSERT INTO players (id, vorname, nachname, name_kurz, name_lang, verein, position, marktwert)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_id, vorname, nachname, name_kurz, name_lang, verein, position, marktwert))
        else:
            # Spieler existiert -> aktualisieren
            cur.execute("""
                UPDATE players
                SET vorname = ?, nachname = ?, name_kurz = ?, name_lang = ?, verein = ?, position = ?
                WHERE id = ?
            """, (vorname, nachname, name_kurz, name_lang, verein, position, player_id))

    print("Keine Punkteveränderung: Kein neuer Spieltag angelegt. Nur Vereins-/Positionswechsel aktualisiert.")

conn.commit()
conn.close()
