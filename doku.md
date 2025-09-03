Dokumentation: Kicker Managerspiel Datenprojekt
1. Übersicht
Dieses Projekt dient der automatisierten Erfassung, Speicherung und Analyse von Spielerdaten des Kicker Managerspiels über mehrere Saisons hinweg. Das Kernstück ist eine robuste SQLite-Datenbank, die für historische Auswertungen optimiert ist, sowie ein Python-Skript, das die Daten aus den offiziellen CSV-Dateien importiert und verarbeitet.

Das Ziel ist es, eine saubere und zuverlässige Datenbasis für detaillierte Analysen und Visualisierungen (z.B. mit Streamlit) zu schaffen, um Spielerleistungen, Marktwertentwicklungen und Team-Zusammensetzungen über die Zeit zu verfolgen.

2. Das Import-Skript (import_kicker_data_saisonübergreifend.py)
Das Skript ist die zentrale Komponente zur Datenverarbeitung. Es ist so konzipiert, dass es die Datenbank sicher und intelligent aktualisiert.

Hauptfunktionen
Saison-Management: Das Skript arbeitet saisonbasiert. Über die Variable CURRENT_SEASON_NAME wird festgelegt, für welche Saison die Daten verarbeitet werden. Neue Saisons werden automatisch in der Datenbank angelegt.

Zwei-Modi-Betrieb: Das Skript kann in zwei Modi ausgeführt werden, gesteuert über die Variable PROCESS_GAME_DAY_NUMBER:

Pre-Saison / Transfer-Modus (PROCESS_GAME_DAY_NUMBER = None): In diesem Modus werden nur die Spieler-Stammdaten aktualisiert. Dies ist ideal für die Zeit zwischen den Spieltagen oder vor Saisonbeginn, um Vereinswechsel, neue Spieler oder Abgänge zu erfassen. Es werden keine Punkte berechnet.

Spieltags-Modus (PROCESS_GAME_DAY_NUMBER = 1, 2, etc.): In diesem Modus werden zusätzlich zu den Stammdaten die Punkte für den angegebenen Spieltag berechnet. Das Skript ermittelt die Punktedifferenz zum vorherigen Spieltag und speichert diese als Spieltagspunkte.

Aktiv/Inaktiv-Logik: Um "Karteileichen" zu vermeiden, werden vor jeder Aktualisierung alle Spieler der aktuellen Saison als inaktiv markiert. Nur die Spieler, die in der neuesten CSV-Datei enthalten sind, werden anschließend wieder als aktiv markiert. So spiegelt die Datenbank immer den exakten, aktuellen Kader der Bundesliga wider.

Datensicherheit ("Atomic Write"): Um eine Beschädigung der Datenbank zu verhindern, arbeitet das Skript nach dem "Alles-oder-Nichts"-Prinzip. Alle Änderungen werden auf einer temporären Kopie der Datenbank durchgeführt. Nur wenn der gesamte Prozess fehlerfrei verläuft, wird die Original-Datenbank durch die aktualisierte Kopie ersetzt. Bei einem Fehler bleibt die Original-Datenbank unberührt.

3. Datenbankstruktur (kicker_main.db)
Die Datenbank ist auf eine saisonübergreifende, normalisierte Struktur ausgelegt, um Datenredundanz zu vermeiden und komplexe Abfragen zu ermöglichen.

Tabelle players
Aufgabe: Speichert absolut unveränderliche Spielerdaten.

Spalte

Typ

Beschreibung

player_id

TEXT PK

Eindeutige Kicker-ID (z.B. pl-k00030669)

first_name

TEXT

Vorname des Spielers

last_name

TEXT

Nachname des Spielers

Tabelle seasons
Aufgabe: Definiert die verschiedenen Saisons.

Spalte

Typ

Beschreibung

season_id

INTEGER PK

Eindeutige ID (Autoincrement)

season_name

TEXT

Name der Saison (z.B. "2024/2025")

Tabelle player_seasonal_details
Aufgabe: Die zentrale Verknüpfungstabelle. Sie speichert alle Daten eines Spielers, die für eine bestimmte Saison gültig sind.

Spalte

Typ

Beschreibung

id

INTEGER PK

Eindeutige ID (Autoincrement)

player_id

TEXT FK

Referenz auf players.player_id

season_id

INTEGER FK

Referenz auf seasons.season_id

club

TEXT

Der Verein des Spielers in dieser Saison

position

TEXT

Die Position des Spielers in dieser Saison

market_value

INTEGER

Der Marktwert des Spielers für diese Saison

is_active

INTEGER

Status (1 = aktiv in der Liga, 0 = inaktiv/verlassen)

Tabelle game_days
Aufgabe: Definiert die einzelnen Spieltage und ordnet sie einer Saison zu.

Spalte

Typ

Beschreibung

game_day_id

INTEGER PK

Eindeutige ID

season_id

INTEGER FK

Referenz auf seasons.season_id

game_day_number

INTEGER

Die Nummer des Spieltags (1-34)

Tabelle player_stats
Aufgabe: Speichert die Leistung eines Spielers an einem konkreten Spieltag.

Spalte

Typ

Beschreibung

stat_id

INTEGER PK

Eindeutige ID (Autoincrement)

player_seasonal_details_id

INTEGER FK

Referenz auf player_seasonal_details.id

game_day_id

INTEGER FK

Referenz auf game_days.game_day_id

points

INTEGER

Die an diesem Spieltag erzielten Punkte

grade

REAL

Die an diesem Spieltag erhaltene Note

gesamtpunkte

REAL

Der kumulierte Gesamtpunktestand nach diesem Spieltag

4. Verwendung für Auswertungen (z.B. mit Streamlit)
Diese Struktur ermöglicht komplexe und interessante Analysen:

Marktwertentwicklung: Vergleiche den Marktwert eines Spielers über mehrere Saisons hinweg.

Leistungsvergleich: Analysiere, ob ein Spieler nach einem Vereinswechsel besser oder schlechter punktet.

Effizienz-Analyse: Berechne die Effizienz (Punkte pro Mio. € Marktwert) für jede Saison und identifiziere konstante "Schnäppchen".

Team-Analyse: Zeige den kompletten, aktiven Kader eines Vereins für eine beliebige Saison an.

Durch SQL-JOIN-Abfragen über die Tabellen können alle diese Informationen einfach verknüpft und in Streamlit als interaktive Diagramme und Tabellen dargestellt werden.