# Dokumentation zum Import-Skript und zur Datenbankstruktur

## Übersicht

Dieses Skript dient dem Import von CSV-Daten aus dem Kicker-Managerspiel in eine SQLite-Datenbank. Es verarbeitet sowohl normale Spieltag-Updates (bei denen sich die Gesamtpunkte der Spieler ändern) als auch reine Änderungen während der Wintertransferperiode (bei denen keine neuen Punkte hinzukommen, Spieler aber ihren Verein oder ihre Position wechseln).

## Hauptfunktionen des Skripts

1. **CSV-Import**:  
   Das Skript liest eine CSV-Datei ein, in der folgende Daten zu den Spielern enthalten sind:
   - ID (eindeutige Spieler-ID)
   - Vorname, Nachname, Kurzname, Langname
   - Verein, Position
   - Marktwert (konstante Größe)
   - Gesamtpunkte (kumuliert bis zum aktuellen Zeitpunkt)

2. **Datenbank-Operationen**:  
   Die eingelesenen Daten werden in einer SQLite-Datenbank (`kicker-data.sqlite`) gespeichert.  
   - `players`: Stammdaten der Spieler
   - `matchdays`: Informationen zu den Spieltagen
   - `player_points`: Punkte der Spieler pro Spieltag

3. **Unterscheidung neuer Spieltag vs. reine Transfer-Updates**:  
   Das Skript prüft, ob sich die Gesamtpunkte im Vergleich zum letzten bekannten Stand verändert haben:
   - **Veränderte Gesamtpunkte**: Neuer Spieltag wird in `matchdays` angelegt (falls nicht vorhanden), und für alle Spieler werden neue Einträge in `player_points` geschrieben.
   - **Unveränderte Gesamtpunkte**: Kein neuer Spieltag. Es werden nur Vereins- und Positionswechsel (sowie etwaige Namensänderungen) in `players` aktualisiert. Keine neuen Einträge in `matchdays` oder `player_points`.

## Datenbankstruktur

### Tabelle `players`

**Aufgabe**: Speicherung der Stammdaten eines Spielers. Änderungen an Verein oder Position werden immer auf den neuesten Stand gebracht, es erfolgt keine Historisierung.

| Spalte    | Typ    | Beschreibung                                |
|-----------|---------|---------------------------------------------|
| id        | TEXT PK | Eindeutige Spieler-ID (z. B. `pl-k00030669`)|
| vorname   | TEXT    | Vorname des Spielers                        |
| nachname  | TEXT    | Nachname des Spielers                       |
| name_kurz | TEXT    | Kurzer Anzeigename                          |
| name_lang | TEXT    | Langer Anzeigename                          |
| verein    | TEXT    | Aktueller Verein                            |
| position  | TEXT    | Aktuelle Position                           |
| marktwert | INTEGER | Marktwert des Spielers                      |

### Tabelle `matchdays`

**Aufgabe**: Speicherung von Spieltagen oder Datenständen, an denen neue Punkte erfasst wurden.

| Spalte       | Typ        | Beschreibung                                         |
|--------------|------------|------------------------------------------------------|
| id           | INTEGER PK | Eindeutige ID (Autoincrement)                       |
| spieltag     | INTEGER    | Spieltagnummer                                      |
| datum_import | TEXT       | Datum/Zeit des Imports (Format `YYYY-MM-DD HH:MM:SS`)|

### Tabelle `player_points`

**Aufgabe**: Speicherung der Punkte pro Spieler und Spieltag. Neben dem Gesamtpunktestand wird auch die Punktedifferenz (Spieltagspunkte) zum vorherigen Spieltag hinterlegt.

| Spalte         | Typ    | Beschreibung                                                  |
|----------------|---------|--------------------------------------------------------------|
| player_id      | TEXT   | Referenz auf `players.id`                                    |
| matchday_id    | INTEGER| Referenz auf `matchdays.id`                                   |
| gesamtpunkte    | REAL   | Gesamtpunktestand des Spielers zum Zeitpunkt des Spieltags   |
| spieltagspunkte | REAL   | Differenz zum vorherigen Gesamtpunktestand                   |

**Primärschlüssel**:  
`(player_id, matchday_id)`

## Prozessablauf im Skript

1. **Initialisierung**:  
   - Datenbank verbinden
   - Tabellen erstellen (falls nicht vorhanden)
   
2. **CSV-Daten einlesen**:  
   - CSV mittels `csv.DictReader` parsen
   - Temporäres Speichern der Spielerinformationen in einer Liste von Dictionaries

3. **Prüfen, ob ein neuer Spieltag vorliegt**:  
   - Letzte bekannte Gesamtpunkte pro Spieler abfragen
   - Wenn für mindestens einen Spieler eine Punktedifferenz gefunden wird → neuer Spieltag
   - Wenn keine Differenz → kein neuer Spieltag

4. **Eintragen/Updaten in der Datenbank**:
   - **Neuer Spieltag**:  
     - Eintrag in `matchdays` erstellen (falls noch nicht vorhanden)  
     - Für jeden Spieler Gesamtpunkte und Spieltagspunkte in `player_points` speichern  
     - Spieler in `players` einfügen oder aktualisieren
     
   - **Kein neuer Spieltag**:  
     - Nur `players` aktualisieren (um Vereins-/Positionswechsel zu berücksichtigen)

5. **Abschluss**:  
   - Änderungen mit `commit()` bestätigen
   - Datenbankverbindung schließen

## Verwendung für grafische Auswertungen (z. B. mit Streamlit)

Mit dieser Datenbankstruktur kannst du in Streamlit verschiedene Auswertungen vornehmen:

- **Punktverlauf eines einzelnen Spielers**:  
  Über `player_points` kann pro Spieltag der Gesamtpunkteverlauf und die erzielten Spieltagspunkte eines Spielers dargestellt werden.

- **Vergleich von Spielern**:  
  Durchschnittliche Punkte, Top-Scorer, Vergleich von Marktwerten oder Vereinen – all dies lässt sich leicht mit SQL-Abfragen umsetzen.

- **Vereins- oder Positionsanalyse**:  
  Da in `players` immer der aktuelle Verein und die aktuelle Position gespeichert sind, lassen sich rasch Übersichten erstellen (z. B. wie viele Stürmer oder wie viele Spieler von Verein X zum aktuellen Zeitpunkt vorhanden sind).

Durch die klare Struktur werden die Auswertungen in Streamlit sehr einfach: SQL-Abfragen liefern die notwendigen Daten, die dann mit Pandas-DataFrames visualisiert und in Streamlit als Diagramme (Line-Charts, Bar-Charts, Pie-Charts) ausgegeben werden können.
