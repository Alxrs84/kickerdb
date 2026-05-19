import sqlite3
import sys
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

st.set_page_config(page_title="KickerDB Analyse", page_icon="⚽")

DB_FILE = str(config.DB_PATH)

POSITION_DE = {
    "GOALKEEPER": "Torwart",
    "DEFENDER": "Abwehr",
    "MIDFIELDER": "Mittelfeld",
    "FORWARD": "Sturm",
}
POS_ORDER = ["Sturm", "Mittelfeld", "Abwehr", "Torwart"]

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _last_ingestion_ts() -> Optional[str]:
    try:
        conn = sqlite3.connect(DB_FILE)
        row = conn.execute(
            "SELECT ingested_at FROM ingestion_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


@st.cache_data(ttl=300)
def _db_ts() -> str:
    """Changing return value invalidates all caches after 5 min or on DB change."""
    return _last_ingestion_ts() or "static"


@st.cache_data
def load_data(query: str, params: tuple = ()) -> pd.DataFrame:
    _ = _db_ts()
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Datenbankfehler: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

@st.cache_data
def load_seasons() -> pd.DataFrame:
    return load_data(
        "SELECT season_id, season_name, budget_limit, kader_gk, kader_def, kader_mid, kader_fwd "
        "FROM seasons ORDER BY season_id DESC"
    )


@st.cache_data
def load_seasonal_data(season_id: int) -> pd.DataFrame:
    df = load_data(
        """
        SELECT
            player_id,
            full_name AS player_name,
            club,
            position,
            market_value AS market_value_eur,
            total_points AS points
        FROM player_season_stats
        WHERE season_id = ?
          AND games_played > 0
        """,
        (season_id,),
    )
    if not df.empty and df["market_value_eur"].gt(0).any():
        df["efficiency"] = (
            df["points"] / (df["market_value_eur"] / 1_000_000)
        ).where(df["market_value_eur"] > 0, 0).round(2)
    return df


@st.cache_data
def load_gameday_data(season_id: int, game_day_number: int) -> pd.DataFrame:
    return load_data(
        """
        SELECT
            p.player_id,
            p.first_name || ' ' || p.last_name AS player_name,
            psd.club,
            psd.position,
            psd.market_value AS market_value_eur,
            COALESCE(ps.points, 0) AS points
        FROM player_seasonal_details psd
        JOIN players p ON psd.player_id = p.player_id
        LEFT JOIN player_stats ps
            ON psd.id = ps.player_seasonal_details_id
           AND ps.game_day_id = (
               SELECT game_day_id FROM game_days
               WHERE season_id = ? AND game_day_number = ?
           )
        WHERE psd.season_id = ?
        ORDER BY points DESC
        """,
        (season_id, game_day_number, season_id),
    )


@st.cache_data
def load_gamedays(season_id: int) -> pd.DataFrame:
    return load_data(
        "SELECT game_day_number FROM game_days WHERE season_id = ? ORDER BY game_day_number",
        (season_id,),
    )


@st.cache_data
def load_player_gameday_progression(season_id: int, player_names: tuple) -> pd.DataFrame:
    if not player_names:
        return pd.DataFrame()
    placeholders = ",".join("?" * len(player_names))
    return load_data(
        f"""
        SELECT
            p.first_name || ' ' || p.last_name AS player_name,
            gd.game_day_number,
            SUM(ps.points) OVER (
                PARTITION BY p.player_id
                ORDER BY gd.game_day_number
            ) AS cumulative_points
        FROM player_stats ps
        JOIN player_seasonal_details psd ON ps.player_seasonal_details_id = psd.id
        JOIN players p ON psd.player_id = p.player_id
        JOIN game_days gd ON ps.game_day_id = gd.game_day_id
        WHERE psd.season_id = ?
          AND p.first_name || ' ' || p.last_name IN ({placeholders})
        ORDER BY player_name, game_day_number
        """,
        (season_id, *player_names),
    )


@st.cache_data
def load_player_seasonal_overview(player_name: str) -> pd.DataFrame:
    return load_data(
        """
        SELECT
            s.season_name,
            psd.club,
            psd.position,
            psd.market_value AS market_value_eur,
            pss.total_points AS points
        FROM player_seasonal_details psd
        JOIN players p ON psd.player_id = p.player_id
        JOIN seasons s ON psd.season_id = s.season_id
        JOIN player_season_stats pss ON pss.player_id = p.player_id AND pss.season_id = s.season_id
        WHERE p.first_name || ' ' || p.last_name = ?
        ORDER BY s.season_id
        """,
        (player_name,),
    )


@st.cache_data
def load_market_value_history(player_name: str) -> pd.DataFrame:
    return load_data(
        """
        SELECT
            s.season_name,
            mvh.recorded_at,
            mvh.market_value
        FROM market_value_history mvh
        JOIN player_seasonal_details psd ON mvh.player_seasonal_details_id = psd.id
        JOIN players p ON psd.player_id = p.player_id
        JOIN seasons s ON psd.season_id = s.season_id
        WHERE p.first_name || ' ' || p.last_name = ?
        ORDER BY mvh.recorded_at
        """,
        (player_name,),
    )


@st.cache_data
def load_all_players() -> pd.DataFrame:
    return load_data(
        """
        SELECT DISTINCT
            p.first_name || ' ' || p.last_name AS player_name,
            psd.club,
            psd.position
        FROM players p
        JOIN player_seasonal_details psd ON p.player_id = psd.player_id
        ORDER BY player_name
        """
    )


# ---------------------------------------------------------------------------
# LP Team Optimizer
# ---------------------------------------------------------------------------

def get_best_team_lp(player_data: pd.DataFrame, formation_counts: tuple,
                     kader_size: dict, budget_limit: int):
    try:
        import pulp
    except ImportError:
        st.error("PuLP nicht installiert. Bitte 'pip install pulp' ausführen.")
        return None

    if player_data.empty:
        st.warning("Keine Spielerdaten vorhanden.")
        return None

    player_data = player_data.copy()
    player_data["market_value_eur"] = player_data["market_value_eur"].fillna(500_000).astype(int)
    player_data = player_data.drop_duplicates(subset=["player_id"])

    formation_map = {
        "GOALKEEPER": formation_counts[0],
        "DEFENDER": formation_counts[1],
        "MIDFIELDER": formation_counts[2],
        "FORWARD": formation_counts[3],
    }

    # Step 1: Select cheapest bench players per position
    bench_frames = []
    bench_total_cost = 0
    bench_ids = set()

    for pos, df_pos in player_data.groupby("position"):
        n_starters = formation_map.get(pos, 0)
        n_total = kader_size.get(pos, n_starters)
        n_bench = n_total - n_starters

        if len(df_pos) < n_total:
            st.error(f"Nicht genug Spieler für {pos}: benötigt {n_total}, verfügbar {len(df_pos)}")
            return None

        bench = df_pos.nsmallest(n_bench, "market_value_eur")
        bench_frames.append(bench)
        bench_total_cost += bench["market_value_eur"].sum()
        bench_ids.update(bench["player_id"].tolist())

    budget_for_xi = budget_limit - bench_total_cost
    candidates = player_data[~player_data["player_id"].isin(bench_ids)].reset_index(drop=True)

    # Step 2: ILP — maximize points within budget + position constraints
    prob = pulp.LpProblem("best_xi", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(len(candidates))]

    prob += pulp.lpSum(x[i] * candidates.loc[i, "points"] for i in range(len(candidates)))
    prob += pulp.lpSum(x[i] * candidates.loc[i, "market_value_eur"] for i in range(len(candidates))) <= budget_for_xi

    for pos, count in formation_map.items():
        idx = [i for i, row in candidates.iterrows() if row["position"] == pos]
        if len(idx) < count:
            st.error(f"Nicht genug Kandidaten für Startelf-Position {pos}")
            return None
        prob += pulp.lpSum(x[i] for i in idx) == count

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    if pulp.LpStatus[prob.status] != "Optimal":
        st.error("Konnte keine optimale Lösung finden.")
        return None

    selected_ids = {candidates.loc[i, "player_id"] for i in range(len(candidates)) if pulp.value(x[i]) == 1}
    startelf = player_data[player_data["player_id"].isin(selected_ids)]
    bench_df = pd.concat(bench_frames) if bench_frames else pd.DataFrame()
    bench_df = bench_df.copy()
    if not bench_df.empty:
        bench_df["points"] = 0.0

    kader_df = pd.concat([startelf, bench_df])

    return {
        "team": kader_df,
        "playing_eleven": startelf,
        "total_points": float(startelf["points"].sum()),
        "total_cost": int(kader_df["market_value_eur"].sum()),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_sorted(df: pd.DataFrame, col: str) -> list:
    if df.empty or col not in df.columns:
        return []
    return sorted(df[col].dropna().unique().tolist())


def fmt_eur(val) -> str:
    return f"{int(val):,} €".replace(",", ".")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.title("⚽ KickerDB Analyse-App")

last_update = _last_ingestion_ts()
if last_update:
    st.caption(f"Letzte Aktualisierung: {last_update[:19].replace('T', ' ')} UTC")

st.sidebar.title("Navigation")
page = st.sidebar.radio("Seite", ["Saison-Analyse", "Spieler-Analyse", "Bestes Team"])

seasons_df = load_seasons()
if seasons_df.empty:
    st.error("Keine Saisons in der Datenbank gefunden.")
    st.stop()

# ---------------------------------------------------------------------------
# Saison-Analyse
# ---------------------------------------------------------------------------
if page == "Saison-Analyse":
    st.header("Saison-Analyse")

    selected_season = st.sidebar.selectbox("Saison", seasons_df["season_name"])
    sid = int(seasons_df.loc[seasons_df["season_name"] == selected_season, "season_id"].iloc[0])

    data = load_seasonal_data(sid)

    st.sidebar.subheader("Filter")
    clubs = ["Alle"] + unique_sorted(data, "club")
    sel_club = st.sidebar.selectbox("Verein", clubs)

    data["position_de"] = data["position"].map(POSITION_DE)
    positions = ["Alle"] + unique_sorted(data, "position_de")
    sel_pos = st.sidebar.selectbox("Position", positions)

    min_pts = int(data["points"].min()) if not data.empty else 0
    max_pts = int(data["points"].max()) if not data.empty else 1000
    pts_filter = st.sidebar.slider("Min. Gesamtpunkte", min_pts, max_pts, min_pts)

    filtered = data.copy()
    if sel_club != "Alle":
        filtered = filtered[filtered["club"] == sel_club]
    if sel_pos != "Alle":
        filtered = filtered[filtered["position_de"] == sel_pos]
    filtered = filtered[filtered["points"] >= pts_filter]

    if not filtered.empty:
        display = filtered.rename(columns={
            "player_name": "Spieler", "club": "Verein", "position_de": "Position",
            "market_value_eur": "Marktwert", "points": "Punkte", "efficiency": "Effizienz (P/Mio.€)",
        })
        display["Marktwert"] = display["Marktwert"].apply(fmt_eur)
        display["Position"] = pd.Categorical(display["Position"], categories=POS_ORDER, ordered=True)
        display = display.sort_values(["Position", "Punkte"], ascending=[True, False])
        st.dataframe(
            display[["Spieler", "Verein", "Position", "Marktwert", "Punkte", "Effizienz (P/Mio.€)"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.warning("Keine Spieler für diese Filter.")

    st.subheader("Punkteverlauf")
    if not filtered.empty:
        sel_players = st.multiselect("Spieler auswählen", filtered["player_name"].tolist())
        if sel_players:
            prog = load_player_gameday_progression(sid, tuple(sel_players))
            if not prog.empty:
                fig, ax = plt.subplots(figsize=(10, 5))
                for player in sel_players:
                    d = prog[prog["player_name"] == player]
                    ax.plot(d["game_day_number"], d["cumulative_points"], label=player)
                ax.set_xlabel("Spieltag")
                ax.set_ylabel("Kumulierte Punkte")
                ax.set_title(f"Punkteverlauf — {selected_season}")
                ax.legend(loc="best")
                ax.grid(True, alpha=0.4)
                st.pyplot(fig)

# ---------------------------------------------------------------------------
# Spieler-Analyse
# ---------------------------------------------------------------------------
elif page == "Spieler-Analyse":
    st.header("Saisonübergreifende Spieler-Analyse")

    all_players = load_all_players()

    st.sidebar.subheader("Filter")
    all_players["position_de"] = all_players["position"].map(POSITION_DE)
    sel_pos_p = st.sidebar.selectbox("Position", ["Alle"] + unique_sorted(all_players, "position_de"))
    sel_club_p = st.sidebar.selectbox("Verein", ["Alle"] + unique_sorted(all_players, "club"))

    fp = all_players.copy()
    if sel_pos_p != "Alle":
        fp = fp[fp["position_de"] == sel_pos_p]
    if sel_club_p != "Alle":
        fp = fp[fp["club"] == sel_club_p]

    if fp.empty:
        st.warning("Keine Spieler für diese Filter.")
    else:
        player_list = sorted(fp["player_name"].unique().tolist())
        selected_player = st.selectbox("Spieler", player_list)

        if selected_player:
            col1, col2 = st.columns(2)

            with col1:
                overview = load_player_seasonal_overview(selected_player)
                if not overview.empty:
                    st.subheader("Saisonüberblick")
                    ov = overview.rename(columns={
                        "season_name": "Saison", "club": "Verein", "position": "Position",
                        "market_value_eur": "Marktwert", "points": "Punkte",
                    })
                    ov["Position"] = ov["Position"].map(POSITION_DE).fillna(ov["Position"])
                    ov["Marktwert"] = ov["Marktwert"].apply(fmt_eur)
                    st.dataframe(ov, use_container_width=True, hide_index=True)

            with col2:
                mv_hist = load_market_value_history(selected_player)
                if not mv_hist.empty and len(mv_hist) > 1:
                    st.subheader("Marktwert-Verlauf")
                    fig, ax = plt.subplots(figsize=(6, 4))
                    for season_name, grp in mv_hist.groupby("season_name"):
                        ax.plot(
                            pd.to_datetime(grp["recorded_at"]),
                            grp["market_value"] / 1_000_000,
                            label=season_name,
                            marker="o", markersize=3,
                        )
                    ax.set_ylabel("Marktwert (Mio. €)")
                    ax.set_title(f"Marktwert: {selected_player}")
                    ax.legend(loc="best")
                    ax.grid(True, alpha=0.4)
                    fig.autofmt_xdate()
                    st.pyplot(fig)
                else:
                    st.info("Zu wenige Datenpunkte für Marktwert-Chart.")

# ---------------------------------------------------------------------------
# Bestes Team
# ---------------------------------------------------------------------------
elif page == "Bestes Team":
    st.header("Bestes Team ermitteln")

    selected_season = st.selectbox("Saison", seasons_df["season_name"])
    season_row = seasons_df[seasons_df["season_name"] == selected_season].iloc[0]
    sid = int(season_row["season_id"])
    budget = int(season_row["budget_limit"])
    kader_size = {
        "GOALKEEPER": int(season_row["kader_gk"]),
        "DEFENDER":   int(season_row["kader_def"]),
        "MIDFIELDER": int(season_row["kader_mid"]),
        "FORWARD":    int(season_row["kader_fwd"]),
    }

    gamedays_df = load_gamedays(sid)
    gameday_options = ["Gesamte Saison"] + gamedays_df["game_day_number"].tolist()
    sel_gameday = st.selectbox("Spieltag", gameday_options)

    FORMATIONS = {
        "4-4-2": (1, 4, 4, 2), "3-5-2": (1, 3, 5, 2), "4-3-3": (1, 4, 3, 3),
        "3-4-3": (1, 3, 4, 3), "4-5-1": (1, 4, 5, 1), "5-3-2": (1, 5, 3, 2),
    }
    sel_formation = st.selectbox("Formation", list(FORMATIONS.keys()))

    col_budget, col_kader = st.columns(2)
    with col_budget:
        budget = st.number_input("Budget (€)", value=budget, step=1_000_000, format="%d")
    with col_kader:
        st.caption(f"Kader: {kader_size['GOALKEEPER']} TW / {kader_size['DEFENDER']} ABW / {kader_size['MIDFIELDER']} MF / {kader_size['FORWARD']} ST")

    if st.button("Bestes Team berechnen"):
        with st.spinner("Berechne …"):
            if sel_gameday == "Gesamte Saison":
                player_data = load_seasonal_data(sid)
            else:
                player_data = load_gameday_data(sid, int(sel_gameday))

            result = get_best_team_lp(player_data, FORMATIONS[sel_formation], kader_size, budget)

        if result:
            st.success("Fertig!")
            c1, c2, c3 = st.columns(3)
            c1.metric("Formation", sel_formation)
            c2.metric("Startelf-Punkte", f"{result['total_points']:.0f}")
            c3.metric("Kader-Kosten", fmt_eur(result["total_cost"]))

            def fmt_team(df: pd.DataFrame) -> pd.DataFrame:
                out = df.rename(columns={
                    "player_name": "Spieler", "club": "Verein", "position": "Position",
                    "market_value_eur": "Marktwert", "points": "Punkte",
                })
                out["Position"] = out["Position"].map(POSITION_DE).fillna(out["Position"])
                out["Marktwert"] = out["Marktwert"].apply(fmt_eur)
                out["Position"] = pd.Categorical(out["Position"], categories=POS_ORDER, ordered=True)
                return out.sort_values(["Position", "Punkte"], ascending=[True, False])

            st.subheader("Startelf")
            st.dataframe(
                fmt_team(result["playing_eleven"])[["Spieler", "Verein", "Position", "Punkte", "Marktwert"]],
                use_container_width=True, hide_index=True, height=420,
            )
            st.subheader("Kompletter Kader")
            st.dataframe(
                fmt_team(result["team"])[["Spieler", "Verein", "Position", "Punkte", "Marktwert"]],
                use_container_width=True, hide_index=True,
            )
