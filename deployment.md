# Deploymentprozess der Kicker-Datenbank-Anwendung

Diese Dokumentation beschreibt den Prozess zur Aktualisierung und Bereitstellung deiner Kicker-Datenbank-Anwendung, die aus den Skripten `autodownload.py`, `import_kicker_data.py` und `streamlit.py` besteht und als Docker-Container auf einer Synology NAS läuft.

## 1. Datenbank aktualisieren

*   **Daten herunterladen:** Führe das Skript `autodownload.py` aus, um die neuesten Kicker-Daten herunterzuladen. Das Skript prüft automatisch, ob es neue Daten gibt und speichert diese als CSV-Datei.
*   **Daten importieren:** Führe das Skript `import_kicker_data.py` aus, um die heruntergeladenen Daten in die SQLite-Datenbank zu importieren. Das Skript aktualisiert die Datenbank mit den neuen Spielerdaten und -punkten.
*   **Datenbank übertragen:** Da die Datenbank in einem gemounteten Volume liegt, ist sie sowohl für deinen lokalen Rechner als auch für den Container auf dem NAS zugänglich. Nach dem lokalen Update musst du den Container im Container Manager neu starten, damit er die aktualisierte Datenbank verwendet.

## 2. Streamlit-App aktualisieren

*   **Änderungen vornehmen:** Bearbeite die Datei `streamlit.py`, um die gewünschten Änderungen an der Streamlit-App vorzunehmen.
*   **Docker-Image erstellen:** Öffne ein Terminal, navigiere zum Verzeichnis mit dem Dockerfile und erstelle ein neues Docker-Image mit dem Befehl:

    ```bash
    docker build -t alxrs/kickerdb:v2 .
    ```

*   **Image hochladen:** Lade das neue Image mit dem Befehl `docker push alxrs/kickerdb:v2` zu Docker Hub hoch.
*   **Container aktualisieren:**
    *   Öffne den Container Manager auf deiner Synology NAS.
    *   Stoppe den laufenden `kicker-container`.
    *   Lösche den `kicker-container`.
    *   Erstelle einen neuen Container mit dem aktualisierten Image `alxrs/kickerdb:v2`.
    *   Konfiguriere die Port-Einstellungen und gemounteten Volumes wie beim ersten Erstellen des Containers.
    *   Starte den neuen Container.

## Zusätzliche Hinweise:

*   **Automatische Updates:** Aktiviere die Option "Automatische Aktualisierung" im Container Manager, um das Image automatisch zu aktualisieren, wenn eine neue Version verfügbar ist.
*   **Sicherung:** Erstelle vor dem Aktualisieren der Datenbank oder der App ein Backup, um Datenverlust zu vermeiden.
*   **Versionsverwaltung:** Verwende ein Versionsverwaltungssystem wie Git, um die Änderungen an deinen Skripten zu verfolgen und bei Bedarf zu einem früheren Zustand zurückkehren zu können.
*   **Monitoring:** Überwache die Logs des Containers und der Anwendung, um Fehler und Probleme frühzeitig zu erkennen.

## Kontakt:

Bei Fragen oder Problemen wende dich an den Entwickler der Anwendung oder an die Synology Community.

## Versionshistorie:

*   1.0: Erste Version der Dokumentation.
*   1.1: Aktualisierung des Docker Hub Image-Namens.

## Autor:

*   Bard, der hilfreiche Assistent