"""
Vereinte Ingestion-Pipeline: Verarbeitet eine neue Kicker-CSV.

Entscheidet automatisch ob nur Stammdaten aktualisiert oder ein neuer Spieltag
verarbeitet wird, indem es den Punkte-Delta aller Spieler berechnet.

Aufruf:
  python pipeline/ingest.py [--csv PATH] [--dry-run] [--force-gameday N]
"""

import argparse
import hashlib
import logging
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def already_ingested(conn: sqlite3.Connection, csv_hash: str) -> bool:
    row = conn.execute(
        "SELECT id FROM ingestion_log WHERE csv_hash = ? AND action != 'error'", (csv_hash,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", dtype=str)
    df["Punkte"] = pd.to_numeric(df["Punkte"], errors="coerce").fillna(0)
    df["Notendurchschnitt"] = pd.to_numeric(df["Notendurchschnitt"], errors="coerce").fillna(0.0)
    df["Marktwert"] = pd.to_numeric(df["Marktwert"], errors="coerce").fillna(0).astype(int)
    df = df[df["Marktwert"] != config.MARKTWERT_PLACEHOLDER].copy()
    return df


def find_latest_csv(directory: Path) -> Optional[Path]:
    files = sorted(directory.glob("data_*.csv"))
    return files[-1] if files else None


# ---------------------------------------------------------------------------
# Season resolution
# ---------------------------------------------------------------------------

def get_active_season(conn: sqlite3.Connection) -> Tuple[int, str]:
    """Returns (season_id, season_name) of the most recently created season."""
    row = conn.execute(
        "SELECT season_id, season_name FROM seasons ORDER BY season_id DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("Keine Saison in der Datenbank gefunden. Bitte zuerst rebuild_from_csv.py ausführen.")
    return row["season_id"], row["season_name"]


# ---------------------------------------------------------------------------
# Master data update
# ---------------------------------------------------------------------------

def update_master_data(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    season_id: int,
    timestamp: str,
) -> Tuple[int, int, Dict[str, int]]:
    """
    Update players and player_seasonal_details for the given season.
    Returns (added, updated, psd_map) where psd_map is {player_id: psd_id}.
    """
    psd_map: Dict[str, int] = {}
    added = 0
    updated = 0

    # Deactivate all, re-activate those present in CSV
    conn.execute("UPDATE player_seasonal_details SET is_active = 0 WHERE season_id = ?", (season_id,))

    for _, row in df.iterrows():
        pid = str(row["ID"])

        # Upsert player
        existing = conn.execute("SELECT player_id FROM players WHERE player_id = ?", (pid,)).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO players (player_id, first_name, last_name) VALUES (?, ?, ?)",
            (pid, str(row["Vorname"]), str(row["Nachname"])),
        )

        # Upsert seasonal details
        existing_psd = conn.execute(
            "SELECT id, club, position, market_value FROM player_seasonal_details WHERE player_id = ? AND season_id = ?",
            (pid, season_id),
        ).fetchone()

        new_club = str(row["Verein"])
        new_pos = str(row["Position"])
        new_mv = int(row["Marktwert"])

        if existing_psd is None:
            conn.execute(
                """
                INSERT INTO player_seasonal_details (player_id, season_id, club, position, market_value, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (pid, season_id, new_club, new_pos, new_mv),
            )
            added += 1
        else:
            changed = (
                existing_psd["club"] != new_club
                or existing_psd["position"] != new_pos
                or existing_psd["market_value"] != new_mv
            )
            conn.execute(
                """
                UPDATE player_seasonal_details
                SET club = ?, position = ?, market_value = ?, is_active = 1
                WHERE player_id = ? AND season_id = ?
                """,
                (new_club, new_pos, new_mv, pid, season_id),
            )
            if changed:
                updated += 1

        psd_id = conn.execute(
            "SELECT id FROM player_seasonal_details WHERE player_id = ? AND season_id = ?",
            (pid, season_id),
        ).fetchone()["id"]
        psd_map[pid] = psd_id

        # Market value history: only record if changed
        last_mv_row = conn.execute(
            "SELECT market_value FROM market_value_history WHERE player_seasonal_details_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (psd_id,),
        ).fetchone()
        if last_mv_row is None or last_mv_row["market_value"] != new_mv:
            conn.execute(
                "INSERT INTO market_value_history (player_seasonal_details_id, market_value, recorded_at) VALUES (?, ?, ?)",
                (psd_id, new_mv, timestamp),
            )

    return added, updated, psd_map


# ---------------------------------------------------------------------------
# Spieltag detection
# ---------------------------------------------------------------------------

def get_db_total_points(conn: sqlite3.Connection, season_id: int) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(ps.points), 0) AS total
        FROM player_stats ps
        JOIN player_seasonal_details psd ON ps.player_seasonal_details_id = psd.id
        WHERE psd.season_id = ?
        """,
        (season_id,),
    ).fetchone()
    return float(row["total"])


def get_last_cumulative_points(conn: sqlite3.Connection, season_id: int) -> Dict[str, float]:
    """Returns {player_id: cumulative_points} based on SUM of all stored stats."""
    rows = conn.execute(
        """
        SELECT p.player_id, COALESCE(SUM(ps.points), 0) AS cumulative
        FROM players p
        JOIN player_seasonal_details psd ON p.player_id = psd.player_id AND psd.season_id = ?
        LEFT JOIN player_stats ps ON psd.id = ps.player_seasonal_details_id
        GROUP BY p.player_id
        """,
        (season_id,),
    ).fetchall()
    return {r["player_id"]: float(r["cumulative"]) for r in rows}


def get_next_game_day_number(conn: sqlite3.Connection, season_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(game_day_number), 0) AS last FROM game_days WHERE season_id = ?",
        (season_id,),
    ).fetchone()
    return int(row["last"]) + 1


# ---------------------------------------------------------------------------
# Spieltag processing
# ---------------------------------------------------------------------------

def process_gameday(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    season_id: int,
    game_day_number: int,
    prev_points: Dict[str, float],
    psd_map: Dict[str, int],
    timestamp: str,
) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO game_days (season_id, game_day_number, processed_at) VALUES (?, ?, ?)",
        (season_id, game_day_number, timestamp),
    )

    gd_id = conn.execute(
        "SELECT game_day_id FROM game_days WHERE season_id = ? AND game_day_number = ?",
        (season_id, game_day_number),
    ).fetchone()["game_day_id"]

    count = 0
    for _, row in df.iterrows():
        pid = str(row["ID"])
        if pid not in psd_map:
            continue
        spieltagspunkte = float(row["Punkte"]) - prev_points.get(pid, 0.0)
        grade = float(row["Notendurchschnitt"]) if float(row["Notendurchschnitt"]) > 0 else None
        conn.execute(
            """
            INSERT OR IGNORE INTO player_stats (player_seasonal_details_id, game_day_id, points, grade)
            VALUES (?, ?, ?, ?)
            """,
            (psd_map[pid], gd_id, round(spieltagspunkte), grade),
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Ingestion log
# ---------------------------------------------------------------------------

def log_ingestion(
    conn: sqlite3.Connection,
    csv_file: str,
    csv_hash: str,
    timestamp: str,
    action: str,
    season_id: Optional[int],
    game_day_number: Optional[int],
    players_added: int,
    players_updated: int,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ingestion_log
            (csv_file, csv_hash, ingested_at, action, season_id, game_day_number,
             players_added, players_updated, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (csv_file, csv_hash, timestamp, action, season_id, game_day_number,
         players_added, players_updated, error_message),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def ingest(csv_path: Path, dry_run: bool = False, force_gameday: Optional[int] = None) -> str:
    """
    Process a single CSV. Returns the action taken: 'skipped', 'master_update', 'gameday', 'error'.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    csv_hash = file_hash(csv_path)

    db_path = config.DB_PATH
    db_tmp = db_path.with_suffix(".ingest.tmp.db")

    if dry_run:
        conn = open_db(db_path)
    else:
        shutil.copy2(db_path, db_tmp)
        conn = open_db(db_tmp)

    try:
        # 1. Skip already-processed CSVs
        if already_ingested(conn, csv_hash):
            log.info("CSV bereits verarbeitet, überspringe: %s", csv_path.name)
            conn.close()
            if not dry_run:
                db_tmp.unlink(missing_ok=True)
            return "skipped"

        # 2. Load CSV
        df = load_csv(csv_path)
        if df.empty:
            log.warning("CSV ist leer nach Filterung: %s", csv_path.name)
            conn.close()
            if not dry_run:
                db_tmp.unlink(missing_ok=True)
            return "skipped"

        # 3. Determine active season
        season_id, season_name = get_active_season(conn)
        log.info("Aktive Saison: %s | CSV: %s", season_name, csv_path.name)

        # 4. Determine current DB total and player totals
        db_total = get_db_total_points(conn, season_id)
        csv_total = float(df["Punkte"].sum())
        delta = csv_total - db_total

        log.info("DB-Gesamt: %.0f | CSV-Gesamt: %.0f | Delta: %+.0f", db_total, csv_total, delta)

        # 5. Update master data (always)
        prev_points = get_last_cumulative_points(conn, season_id)
        added, updated, psd_map = update_master_data(conn, df, season_id, timestamp)
        log.info("Stammdaten: +%d neu, ~%d geändert", added, updated)

        # 6. Decide: new Spieltag?
        action = "master_update"
        game_day_number: Optional[int] = None

        if force_gameday is not None:
            game_day_number = force_gameday
            log.info("Erzwinge Spieltag %d", game_day_number)
        elif delta >= config.SPIELTAG_SCHWELLWERT:
            game_day_number = get_next_game_day_number(conn, season_id)
            log.info("Spieltag erkannt: delta=+%.0f → Spieltag %d", delta, game_day_number)

        if game_day_number is not None:
            action = "gameday"
            if not dry_run:
                count = process_gameday(conn, df, season_id, game_day_number, prev_points, psd_map, timestamp)
                log.info("Spieltag %d: %d Spieler-Stats gespeichert", game_day_number, count)
            else:
                count = sum(1 for _, r in df.iterrows() if str(r["ID"]) in psd_map)
                log.info("[DRY RUN] Spieltag %d: würde %d Stats einfügen", game_day_number, count)

        # 7. Write ingestion log + commit
        if not dry_run:
            log_ingestion(conn, csv_path.name, csv_hash, timestamp, action,
                          season_id, game_day_number, added, updated)
            conn.commit()
            conn.close()
            db_tmp.replace(db_path)
            log.info("Datenbank aktualisiert: %s", action)
        else:
            log.info("[DRY RUN] Keine DB-Änderungen. Aktion wäre: %s", action)
            conn.close()

        return action

    except Exception as e:
        log.error("Fehler bei Ingestion: %s", e, exc_info=True)
        try:
            conn.close()
        except Exception:
            pass
        if not dry_run and db_tmp.exists():
            db_tmp.unlink()
        return "error"


def main() -> None:
    parser = argparse.ArgumentParser(description="Kicker CSV ingestion pipeline")
    parser.add_argument("--csv", help="Pfad zur CSV-Datei (default: neueste in autodownload/)")
    parser.add_argument("--dry-run", action="store_true", help="Keine DB-Änderungen")
    parser.add_argument(
        "--force-gameday", type=int, metavar="N",
        help="Spieltag N erzwingen (überspringt Delta-Prüfung)"
    )
    args = parser.parse_args()

    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_latest_csv(config.AUTODOWNLOAD_DIR)

    if not csv_path or not csv_path.exists():
        log.error("Keine CSV-Datei gefunden.")
        sys.exit(1)

    result = ingest(csv_path, dry_run=args.dry_run, force_gameday=args.force_gameday)
    sys.exit(0 if result != "error" else 1)


if __name__ == "__main__":
    main()
