# Kicker Managerspiel Analyse

Dieses Projekt bietet eine Streamlit-Webanwendung zur Analyse von Spielerdaten aus dem Kicker Managerspiel.
Die App wird bei Streamlit unter der URL https://kickerdb.streamlit.app/ gehostet.

## Features

* Automatischer Download der aktuellen Spielerdaten
* Speicherung der Daten in einer SQLite-Datenbank
* Berechnung von zusätzlichen Metriken (z.B. Punkte pro Million Euro Marktwert)
* Interaktive Filterung der Spielerdaten nach Verein, Position, Punkten und Marktwert
* Vergleich von Spielern anhand von Diagrammen

## Verwendung

1. **Klone das Repository:** `git clone https://github.com/dein-username/kicker-managerspiel-analyse.git`
2. **Installiere die Abhängigkeiten:** `pip install -r requirements.txt`
3. **Starte die Streamlit-App:** `streamlit run streamlit.py`

## Docker

Das Projekt kann auch als Docker Container ausgeführt werden:

1. **Baue das Image:** `docker build -t kicker-managerspiel-analyse .`
2. **Starte den Container:** `docker run -p 8501:8501 kicker-managerspiel-analyse`

## Contributing

Beiträge sind willkommen! Bitte erstelle ein Issue oder einen Pull Request.

## Lizenz

[Name der Lizenz]