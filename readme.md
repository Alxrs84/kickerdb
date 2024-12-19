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

## Lizenz

MIT License

Copyright (c) [2024] [Alxrs84]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.