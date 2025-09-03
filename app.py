import streamlit as st
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from itertools import combinations

# Setze die Page-Konfiguration
st.set_page_config(
    page_title="KickerDB Analyse",
    page_icon="⚽",
    layout="wide",
)

# Dateipfad zur Datenbank
DB_FILE = "kicker_main.db"

# Caching-Funktion, um Daten aus der Datenbank zu laden
@st.cache_data
def load_data(query, params=None):
    """
    Lädt Daten aus der SQLite-Datenbank.
    Verwendet Caching, um Abfragen bei wiederholtem Laden zu beschleunigen.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        if params:
            df = pd.read_sql_query(query, conn, params=params)
        else:
            df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Datenbankfehler: {e}")
        return pd.DataFrame()

@st.cache_data
def load_all_seasons():
    """Lädt alle Saisons aus der Datenbank."""
    return load_data("SELECT season_name, season_id FROM seasons ORDER BY season_name DESC")

@st.cache_data
def load_seasonal_data(season_id):
    """
    Lädt Spielerdaten für eine bestimmte Saison, einschließlich Gesamtpunkten und Marktwert.
    Berechnet die Effizienz (Punkte pro Million).
    """
    query = f"""
    SELECT
        p.player_id,
        p.first_name || ' ' || p.last_name AS player_name,
        psd.club AS club,
        psd.position AS position,
        psd.market_value AS market_value_eur,
        MAX(ps.gesamtpunkte) AS points
    FROM
        player_seasonal_details psd
    JOIN
        players p ON psd.player_id = p.player_id
    JOIN
        player_stats ps ON psd.id = ps.player_seasonal_details_id
    WHERE
        psd.season_id = {season_id}
    GROUP BY
        psd.id
    HAVING
        points IS NOT NULL
    """
    df = load_data(query)
    if not df.empty:
        df['efficiency_points_per_mil'] = df.apply(
            lambda row: round(row['points'] / (row['market_value_eur'] / 1_000_000), 2)
            if row['market_value_eur'] > 0 else 0, axis=1
        )
    return df

@st.cache_data
def load_player_gameday_stats(season_id, player_names):
    """
    Lädt die kumulierten Gesamtpunkte pro Spieltag für ausgewählte Spieler.
    Korrigierte Abfrage ohne JOIN auf game_days.
    """
    if not player_names:
        return pd.DataFrame()

    placeholders = ', '.join('?' for name in player_names)
    query = f"""
    SELECT
        p.first_name || ' ' || p.last_name AS player_name,
        ps.game_day_id as game_day_number,
        ps.gesamtpunkte as points
    FROM
        player_stats ps
    JOIN
        player_seasonal_details psd ON ps.player_seasonal_details_id = psd.id
    JOIN
        players p ON psd.player_id = p.player_id
    WHERE
        psd.season_id = {season_id}
        AND p.first_name || ' ' || p.last_name IN ({placeholders})
    ORDER BY
        player_name, game_day_number
    """
    df = load_data(query, params=player_names)
    return df

@st.cache_data
def load_all_players_for_analysis():
    """
    Lädt alle Spieler mit ihrer Position und ihrem Verein für alle Saisons,
    um sie in der Spieler-Analyse-Seite auszuwählen.
    """
    query = """
    SELECT DISTINCT
        p.first_name || ' ' || p.last_name AS player_name,
        psd.club AS club,
        psd.position AS position
    FROM
        players p
    JOIN
        player_seasonal_details psd ON p.player_id = psd.player_id
    ORDER BY
        player_name
    """
    return load_data(query)

@st.cache_data
def load_player_seasonal_overview(player_name):
    """
    Lädt saisonübergreifende Daten für einen bestimmten Spieler.
    """
    query = """
    SELECT
        s.season_name,
        psd.club,
        psd.position,
        psd.market_value AS market_value_eur,
        MAX(ps.gesamtpunkte) AS points
    FROM
        player_seasonal_details psd
    JOIN
        players p ON psd.player_id = p.player_id
    JOIN
        player_stats ps ON psd.id = ps.player_seasonal_details_id
    JOIN
        seasons s ON psd.season_id = s.season_id
    WHERE
        p.first_name || ' ' || p.last_name = ?
    GROUP BY
        s.season_name, psd.club, psd.position, psd.market_value
    ORDER BY
        s.season_name
    """
    return load_data(query, params=(player_name,))

def get_unique_values(df, column):
    """Gibt eine Liste der eindeutigen Werte einer Spalte zurück."""
    if df.empty or column not in df.columns:
        return []
    return sorted(df[column].unique().tolist())

@st.cache_data
def load_gameday_data(season_id, gameday_number):
    """
    Lädt alle Spielerdaten für einen bestimmten Spieltag in einer Saison.
    Korrigierte Abfrage: Bezieht alle Spieler der Saison ein und weist 0 Punkte zu, wenn keine Stats vorhanden sind.
    """
    query = f"""
    SELECT
        p.player_id,
        p.first_name || ' ' || p.last_name AS player_name,
        psd.club,
        psd.position,
        psd.market_value AS market_value_eur,
        COALESCE(ps.points, 0) AS points
    FROM
        player_seasonal_details psd
    JOIN
        players p ON psd.player_id = p.player_id
    LEFT JOIN
        player_stats ps ON psd.id = ps.player_seasonal_details_id AND ps.game_day_id = {gameday_number}
    WHERE
        psd.season_id = {season_id}
    ORDER BY
        points DESC
    """
    return load_data(query)

def get_best_team(player_data, formation_counts, kader_size, budget_limit):
    """
    Findet das beste Team unter den gegebenen Restriktionen mittels dynamischer Programmierung.
    """
    if player_data.empty:
        st.warning("Keine Spielerdaten für die ausgewählte Saison/Spieltag vorhanden.")
        return None

    # Daten vorbereiten
    player_data['market_value_eur'] = player_data['market_value_eur'].fillna(500000).astype(int)
    player_data = player_data.drop_duplicates(subset=['player_id'])
    
    positions = {
        'GOALKEEPER': player_data[player_data['position'] == 'GOALKEEPER'],
        'DEFENDER': player_data[player_data['position'] == 'DEFENDER'],
        'MIDFIELDER': player_data[player_data['position'] == 'MIDFIELDER'],
        'FORWARD': player_data[player_data['position'] == 'FORWARD']
    }
    
    formation_map = {
        'GOALKEEPER': formation_counts[0], 'DEFENDER': formation_counts[1],
        'MIDFIELDER': formation_counts[2], 'FORWARD': formation_counts[3]
    }

    # Schritt 1: Günstigste Ersatzbank auffüllen und Spielerpools für Startelf erstellen
    starter_pools = {}
    ersatzbank_players = []
    ersatzbank_value = 0

    for pos, df in positions.items():
        if len(df) < kader_size[pos]:
            st.error(f"Nicht genügend Spieler für die Position {pos}, um den Kader zu füllen. Benötigt: {kader_size[pos]}, Verfügbar: {len(df)}")
            return None
        
        df_sorted = df.sort_values('market_value_eur', ascending=True)
        num_starters = formation_map[pos]
        num_bench = kader_size[pos] - num_starters
        
        bench = df_sorted.head(num_bench)
        ersatzbank_players.append(bench)
        ersatzbank_value += bench['market_value_eur'].sum()
        
        starter_pools[pos] = df[~df['player_id'].isin(bench['player_id'])].to_dict('records')

    # Performance-Optimierung: Reduziere die Größe der Spieler-Pools
    PRUNING_LIMITS = {'GOALKEEPER': 8, 'DEFENDER': 8, 'MIDFIELDER': 8, 'FORWARD': 8}
    st.sidebar.info("Performance-Hinweis: Es werden nur die Top-Spieler (nach Punkten) pro Position berücksichtigt.")

    for pos in positions.keys():
        pool = starter_pools[pos]
        limit = PRUNING_LIMITS[pos]
        if len(pool) > limit:
            # Sortiere nach Punkten absteigend (primär) und Marktwert aufsteigend (sekundär)
            sorted_pool = sorted(pool, key=lambda x: (x.get('points', 0), -x.get('market_value_eur', 999999999)), reverse=True)
            starter_pools[pos] = sorted_pool[:limit]
            st.sidebar.write(f"{pos}: Pool von {len(pool)} auf {len(starter_pools[pos])} reduziert.")
        else:
            st.sidebar.write(f"{pos}: Pool hat {len(pool)} Spieler.")

    budget_for_eleven = budget_limit - ersatzbank_value
    st.info(f"Budget für Ersatzbank: {ersatzbank_value:,.0f} €. Verbleibendes Budget für Startelf: {budget_for_eleven:,.0f} €.")

    # Schritt 2: Beste Startelf per Dynamic Programming (Knapsack-Problem) finden
    dp = {0: (0.0, [])}
    
    for pos in ['GOALKEEPER', 'DEFENDER', 'MIDFIELDER', 'FORWARD']:
        new_dp = {}
        num_to_pick = formation_map[pos]
        
        if len(starter_pools[pos]) < num_to_pick:
             st.error(f"Nicht genügend Spieler im Starter-Pool für Position {pos}. Benötigt: {num_to_pick}, Verfügbar: {len(starter_pools[pos])}")
             return None

        for combo in combinations(starter_pools[pos], num_to_pick):
            combo_cost = sum(p['market_value_eur'] for p in combo)
            combo_points = sum(p.get('points', 0) for p in combo)
            combo_players = [p['player_id'] for p in combo]

            for cost, (points, players) in dp.items():
                new_cost = cost + combo_cost
                if new_cost <= budget_for_eleven:
                    new_points = points + combo_points
                    if new_cost not in new_dp or new_points > new_dp[new_cost][0]:
                        new_dp[new_cost] = (new_points, players + combo_players)
        
        if not new_dp:
            st.warning(f"Konnte nach Hinzufügen von {pos} keine gültige Mannschaft mehr bilden.")
            dp = {}
            break
        dp = new_dp
    
    if not dp:
        st.error("Konnte keine Startelf finden, die das Budget einhält.")
        return None

    best_cost, (best_points, best_player_ids) = max(dp.items(), key=lambda item: item[1][0])

    startelf_df = player_data[player_data['player_id'].isin(best_player_ids)]
    ersatzbank_df = pd.concat(ersatzbank_players)
    ersatzbank_df['points'] = 0.0
    
    final_kader_df = pd.concat([startelf_df, ersatzbank_df])
    
    return {
        'team': final_kader_df,
        'playing_eleven': startelf_df,
        'total_points': best_points,
        'total_cost': final_kader_df['market_value_eur'].sum()
    }

# --- Layout der Streamlit-App ---

st.title("⚽ KickerDB Analyse-App")

st.markdown("""
    Diese App dient der Analyse von Spielerdaten aus der deutschen Fußball-Bundesliga. 
    Wähle links in der Seitenleiste zwischen den Analyse-Seiten.
    ---
""")

# Seitenleiste
st.sidebar.title("App-Navigation")
page = st.sidebar.radio("Wähle eine Seite", ["Saison-Analyse", "Spieler-Analyse", "Bestes Team"])

# --- Seite: Saison-Analyse ---
if page == "Saison-Analyse":
    st.header("Saison-Analyse")
    st.write("Detaillierte Analyse der Spielerleistungen innerhalb einer ausgewählten Saison.")

    seasons_df = load_all_seasons()
    if seasons_df.empty:
        st.error("Keine Saisons in der Datenbank gefunden.")
    else:
        selected_season_name = st.sidebar.selectbox("Saison wählen", seasons_df['season_name'])
        selected_season_id = int(seasons_df[seasons_df['season_name'] == selected_season_name]['season_id'].iloc[0])
        
        seasonal_data = load_seasonal_data(selected_season_id)

        st.sidebar.subheader("Filter")
        all_clubs = ['Alle'] + get_unique_values(seasonal_data, 'club')
        selected_club = st.sidebar.selectbox("Verein", all_clubs)
        
        all_positions = ['Alle'] + get_unique_values(seasonal_data, 'position')
        selected_position = st.sidebar.selectbox("Position", all_positions)
        
        min_points_filter = st.sidebar.slider("Minimale Gesamtpunkte", 
                                              int(seasonal_data['points'].min()) if not seasonal_data.empty else 0, 
                                              int(seasonal_data['points'].max()) if not seasonal_data.empty else 1000, 
                                              0)
        
        min_market_value = float(seasonal_data['market_value_eur'].min()) if not seasonal_data.empty else 0.0
        max_market_value = float(seasonal_data['market_value_eur'].max()) if not seasonal_data.empty else 200000000.0
        market_value_range = st.sidebar.slider(
            "Marktwert (in Mio. €)",
            min_market_value / 1_000_000, max_market_value / 1_000_000, 
            (min_market_value / 1_000_000, max_market_value / 1_000_000)
        )

        filtered_data = seasonal_data.copy()
        if selected_club != 'Alle':
            filtered_data = filtered_data[filtered_data['club'] == selected_club]
        if selected_position != 'Alle':
            filtered_data = filtered_data[filtered_data['position'] == selected_position]
        
        filtered_data = filtered_data[filtered_data['points'] >= min_points_filter]
        filtered_data = filtered_data[
            (filtered_data['market_value_eur'] >= market_value_range[0] * 1_000_000) & 
            (filtered_data['market_value_eur'] <= market_value_range[1] * 1_000_000)
        ]

        if not filtered_data.empty:
            display_data = filtered_data.rename(columns={
                'player_name': 'Spieler', 'club': 'Verein', 'position': 'Position',
                'market_value_eur': 'Marktwert (€)', 'points': 'Gesamtpunkte',
                'efficiency_points_per_mil': 'Effizienz (P/Mio.€)'
            })
            
            display_data['Marktwert (€)'] = display_data['Marktwert (€)'].apply(lambda x: f"{x:,.0f} €".replace(",", "."))
            st.subheader("Spieler-Übersicht")
            st.dataframe(display_data.drop(columns=['player_id']), use_container_width=True, hide_index=True)
        else:
            st.warning("Keine Spieler gefunden, die den Filterkriterien entsprechen.")

        st.subheader("Detaillierter Spielervergleich")
        player_options = filtered_data['player_name'].tolist()
        if player_options:
            selected_players = st.multiselect("Wähle Spieler für den Vergleich", player_options)
            if selected_players:
                comparison_data = load_player_gameday_stats(selected_season_id, selected_players)
                if not comparison_data.empty:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    for player in selected_players:
                        player_data = comparison_data[comparison_data['player_name'] == player]
                        ax.plot(player_data['game_day_number'], player_data['points'], label=player)
                    
                    ax.set_title(f"Kumulierte Gesamtpunkte pro Spieltag ({selected_season_name})")
                    ax.set_xlabel("Spieltag")
                    ax.set_ylabel("Gesamtpunkte")
                    ax.legend(loc='best')
                    ax.grid(True)
                    st.pyplot(fig)
                else:
                    st.warning("Keine Spieltagsdaten für die Auswahl in dieser Saison.")

# --- Seite: Spieler-Analyse ---
elif page == "Spieler-Analyse":
    st.header("Saisonübergreifende Spieler-Analyse")
    st.write("Wähle einen Spieler aus, um seine Leistung über die Saisons hinweg zu verfolgen.")

    all_players_df = load_all_players_for_analysis()
    if not all_players_df.empty:
        selected_player = st.selectbox("Wähle einen Spieler", all_players_df['player_name'].unique())
        if selected_player:
            player_overview_df = load_player_seasonal_overview(selected_player)
            if not player_overview_df.empty:
                st.subheader(f"Saisonale Übersicht für {selected_player}")
                display_df = player_overview_df.rename(columns={
                    'season_name': 'Saison', 'club': 'Verein', 'position': 'Position',
                    'market_value_eur': 'Marktwert (€)', 'points': 'Gesamtpunkte'
                })
                display_df['Marktwert (€)'] = display_df['Marktwert (€)'].apply(lambda x: f"{x:,.0f} €".replace(",", "."))
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.warning(f"Keine Daten für {selected_player} gefunden.")
    else:
        st.error("Keine Spielerdaten zum Laden vorhanden.")

# --- Seite: Bestes Team ---
elif page == "Bestes Team":
    st.header("Bestes Team ermitteln")
    st.write("Finde das Team mit der höchsten Punktzahl unter den gegebenen Restriktionen.")

    seasons_df = load_all_seasons()
    if seasons_df.empty:
        st.error("Keine Saisons in der Datenbank gefunden.")
    else:
        selected_season_name = st.selectbox("Saison wählen", seasons_df['season_name'])
        selected_season_id = int(seasons_df[seasons_df['season_name'] == selected_season_name]['season_id'].iloc[0])

        # Korrigierte Abfrage für die Spieltagsauswahl
        gamedays_query = f"""
        SELECT DISTINCT ps.game_day_id FROM player_stats ps
        JOIN player_seasonal_details psd ON psd.id = ps.player_seasonal_details_id
        WHERE psd.season_id = {selected_season_id}
        ORDER BY ps.game_day_id
        """
        gamedays_df = load_data(gamedays_query)

        gameday_options = ['Gesamte Saison'] + gamedays_df['game_day_id'].tolist()
        selected_gameday = st.selectbox("Spieltag wählen", gameday_options)

        formations = {
            '4-4-2': (1, 4, 4, 2), '3-5-2': (1, 3, 5, 2), '4-3-3': (1, 4, 3, 3),
            '3-4-3': (1, 3, 4, 3), '4-5-1': (1, 4, 5, 1), '5-3-2': (1, 5, 3, 2),
            '5-4-1': (1, 5, 4, 1),
        }
        selected_formation_name = st.selectbox("Wähle eine Formation", list(formations.keys()))
        
        if st.button("Bestes Team berechnen"):
            with st.spinner("Berechne das beste Team... Das kann einen Moment dauern."):
                if selected_gameday == 'Gesamte Saison':
                    player_data = load_seasonal_data(selected_season_id)
                else:
                    player_data = load_gameday_data(selected_season_id, int(selected_gameday))
                
                kader_size = {'GOALKEEPER': 3, 'DEFENDER': 7, 'MIDFIELDER': 7, 'FORWARD': 5}
                budget_limit = 42_000_000
                formation_counts = formations[selected_formation_name]

                best_team_result = get_best_team(player_data, formation_counts, kader_size, budget_limit)
                
                if best_team_result:
                    st.success("Berechnung abgeschlossen!")
                    st.subheader(f"Bestes Team für: {selected_season_name}, Spieltag: {selected_gameday}")
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Formation", selected_formation_name)
                    col2.metric("Gesamtpunkte (Startelf)", f"{best_team_result['total_points']:,.2f}".replace(",", "."))
                    col3.metric("Gesamtkosten (Kader)", f"{best_team_result['total_cost']:,.0f} €".replace(",", "."))
                    
                    st.markdown("### Startelf")
                    playing_eleven_df = best_team_result['playing_eleven'].rename(columns={
                        'player_name': 'Spieler', 'club': 'Verein', 'position': 'Position', 
                        'market_value_eur': 'Marktwert (€)', 'points': 'Punkte'
                    })
                    playing_eleven_df['Marktwert (€)'] = playing_eleven_df['Marktwert (€)'].apply(lambda x: f"{x:,.0f} €".replace(",", "."))
                    st.dataframe(playing_eleven_df[['Spieler', 'Verein', 'Position', 'Punkte', 'Marktwert (€)']].sort_values('Punkte', ascending=False), 
                                 use_container_width=True, hide_index=True)
                    
                    st.markdown("### Kompletter Kader (inkl. Ersatzbank)")
                    kader_df = best_team_result['team'].rename(columns={
                        'player_name': 'Spieler', 'club': 'Verein', 'position': 'Position', 
                        'market_value_eur': 'Marktwert (€)', 'points': 'Punkte'
                    })
                    kader_df['Marktwert (€)'] = kader_df['Marktwert (€)'].apply(lambda x: f"{x:,.0f} €".replace(",", "."))
                    st.dataframe(kader_df[['Spieler', 'Verein', 'Position', 'Punkte', 'Marktwert (€)']].sort_values(['Punkte', 'Marktwert (€)'], ascending=False), 
                                 use_container_width=True, hide_index=True)
                else:
                    st.error("Es konnte kein Team gefunden werden, das die Kriterien erfüllt.")

