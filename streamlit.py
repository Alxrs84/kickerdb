import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.colors as mcolors

# Datenbankverbindung herstellen
DB_PATH = "kicker-data.sqlite"
conn = sqlite3.connect(DB_PATH)

# Funktion, um Daten aus der Datenbank zu laden
def load_data():
    """
    Lädt die Spieler- und Punktedaten aus der SQLite-Datenbank.
    Führt eine SQL-Abfrage aus, die Daten aus den Tabellen `player_points`, `players` und `matchdays` kombiniert.
    Gibt die abgerufenen Daten als Pandas DataFrame zurück.
    
    Returns:
        pd.DataFrame: Ein DataFrame mit den Spalten:
            - player_id: Eindeutige Spieler-ID
            - name: Spielername
            - club: Aktueller Verein
            - position: Position des Spielers
            - market_value: Marktwert des Spielers
            - total_points: Gesamtpunkte des Spielers
            - matchday_points: Punkte für den aktuellen Spieltag
            - matchday: Spieltagsnummer
    """
    query = """
    SELECT 
        pp.player_id AS player_id, 
        pl.name_kurz AS name, 
        pl.verein AS club, 
        pl.position AS position,
        pl.marktwert AS market_value, 
        pp.gesamtpunkte AS total_points, 
        pp.spieltagspunkte AS matchday_points, 
        m.spieltag AS matchday
    FROM player_points pp
    JOIN players pl ON pp.player_id = pl.id
    JOIN matchdays m ON pp.matchday_id = m.id
    """
    return pd.read_sql_query(query, conn)

# Daten laden
data = load_data()

# Berechnungen hinzufügen
if not data.empty:
    # Marktwert prüfen und Berechnung korrigieren
    data['points_per_million'] = data.apply(
        lambda row: row['total_points'] / (row['market_value'] / 1_000_000) if row['market_value'] > 0 else 0,
        axis=1
    )
else:
    st.warning("Die Datenbank enthält keine Daten oder die Abfrage lieferte keine Ergebnisse.")

# Hauptfunktionalität der Streamlit-App
# Diese App visualisiert Spielerstatistiken aus dem Kicker Managerspiel
# Es bietet Filtermöglichkeiten und die Möglichkeit, Spieler zu vergleichen
# Die Statistiken umfassen Punkte pro Spieltag, Gesamtpunkte und Effizienz (Punkte pro Million Euro Marktwert)

# Streamlit-UI
st.title("Kicker Managerspiel: Spieler-Analyse")
st.sidebar.header("Filter")

# Filteroptionen
selected_club = st.sidebar.selectbox("Verein", ["Alle"] + sorted(data['club'].unique()))
selected_position = st.sidebar.selectbox("Position", ["Alle"] + sorted(data['position'].unique()))
selected_min_points = st.sidebar.slider("Minimale Punkte", min_value=0, max_value=int(data['total_points'].max()), value=0)
selected_market_value = st.sidebar.slider("Marktwert", min_value=0, max_value=int(data['market_value'].max()), value=(0, int(data['market_value'].max())), step=100000)

# Daten filtern
filtered_data = data.copy()
if selected_club != "Alle":
    filtered_data = filtered_data[filtered_data['club'] == selected_club]
if selected_position != "Alle":
    filtered_data = filtered_data[filtered_data['position'] == selected_position]
filtered_data = filtered_data[(filtered_data['total_points'] >= selected_min_points) &
                              (filtered_data['market_value'] >= selected_market_value[0]) &
                              (filtered_data['market_value'] <= selected_market_value[1])]

# Für die Tabelle: Nur die aktuellsten Daten je Spieler behalten und nach Punkte pro Million Euro sortieren
latest_data = filtered_data.sort_values(by='matchday', ascending=False).drop_duplicates(subset=['player_id'])
latest_data = latest_data.sort_values(by='points_per_million', ascending=False)

# Übersicht anzeigen
st.header("Spieler-Daten")
if not latest_data.empty:
    # Tabellenüberschriften anpassen und Werte runden
    latest_data_display = latest_data.rename(columns={
        'position': 'Position',
        'name': 'Name',
        'club': 'Verein',
        'market_value': 'Marktwert',
        'total_points': 'Gesamtpunkte',
        'points_per_million': 'Punkte/Mio'
    })
    latest_data_display['Punkte/Mio'] = latest_data_display['Punkte/Mio'].round(1)
    st.dataframe(latest_data_display[['Position', 'Name', 'Verein', 'Marktwert', 'Gesamtpunkte', 'Punkte/Mio']], hide_index=True, height=400)
else:
    st.warning("Keine Daten entsprechen den ausgewählten Filtern.")

# Eingabefeld für die Spielerauswahl
st.header("Punkte pro Million Euro Marktwert")
selected_players = st.multiselect(
    "Wähle Spieler für den Vergleich aus:",
    options=latest_data_display['Name'].unique(),
    default=[]
)

# Für den Plot: Originaldaten nur für die ausgewählten Spieler anzeigen
if selected_players:
    # Checkboxen für Diagramme
    show_line_chart = st.checkbox("Punkte pro Million Euro anzeigen", value=True)
    show_bar_chart = st.checkbox("Punkte je Spieltag anzeigen", value=True)

    if show_line_chart or show_bar_chart:
        fig, ax = plt.subplots()
        ax.set_xlabel('Spieltag')
        ax.set_ylabel('Punkte', color='black')

        colors = list(mcolors.TABLEAU_COLORS.values())  # Farbskala für konsistente Farben
        width = 0.2  # Breite der Balken für nebeneinanderliegende Darstellung
        all_matchdays = range(1, filtered_data['matchday'].max() + 1)

        for i, player in enumerate(selected_players):
            player_data = data[data['name'] == player]

            if not player_data.empty:
                # Fehlende Spieltage auffüllen und sortieren
                player_data = player_data.sort_values(by='matchday').reset_index(drop=True)
                matchdays_df = pd.DataFrame({'matchday': all_matchdays})
                player_data = matchdays_df.merge(player_data, on='matchday', how='left').fillna(0)

                base_color = colors[i % len(colors)]  # Farbe aus der Palette
                bar_color = mcolors.to_rgba(base_color, alpha=0.5)  # Transparent für Balken

                # Linie für Punkte pro Million
                if show_line_chart:
                    ax.plot(player_data['matchday'], player_data['points_per_million'], 
                            label=f'{player} - Punkte pro Million Euro', color=base_color, marker='o')
                # Balkendiagramm für Spieltagspunkte (nebeneinander)
                if show_bar_chart:
                    ax.bar(player_data['matchday'] + i * width, player_data['matchday_points'], 
                           width=width, label=f'{player} - Punkte je Spieltag', color=bar_color)

        # Achsen anpassen für nebeneinanderliegende Balken
        ax.set_xticks(np.array(all_matchdays) + width * (len(selected_players) - 1) / 2)
        ax.set_xticklabels(all_matchdays)
        
        # Legende hinzufügen, falls Diagramme aktiv sind
        ax.legend()
        fig.tight_layout()
        st.pyplot(fig)
    else:
        st.info("Aktiviere mindestens eines der Diagramme, um die Visualisierung anzuzeigen.")
else:
    st.info("Bitte wähle Spieler über das Eingabefeld aus, um den Plot anzuzeigen.")

# Copyright-Informationen anzeigen
st.markdown("---")
st.text("© 2024 Kicker Managerspiel Analyse. Alle Rechte vorbehalten.")

# Verbindung schließen
conn.close()
