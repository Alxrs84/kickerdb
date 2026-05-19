"""
Einmaliges Migrationsskript: Baut die neue DB vollständig aus dem CSV-Archiv auf.

Ablauf:
  1. Alle CSVs in autodownload/ chronologisch einlesen
  2. Saison-Grenzen erkennen (drastischer Punkte-Abfall = neue Saison)
  3. Spieltage erkennen (Punkte-Delta > Schwellwert)
  4. DB mit neuem Schema befüllen

Aufruf:
  python scripts/rebuild_from_csv.py [--dry-run] [--threshold 1500]
"""

import argparse
import glob
import hashlib
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Saison-Konfiguration: chronologisch geordnet.
# 'start' und 'end' sind inklusive Datums-Präfixe der CSV-Dateinamen (YYYY-MM-DD).
SEASON_CONFIG = [
    {
        "name": "2024/2025",
        "api_url": "https://www.kicker-libero.de/api/sportsdata/v1/players-details/se-k00012024.csv",
        "start": "2024-01-01",
        # API resets to 0 on 2025-08-23. Include all CSVs until the day before.
        "end":   "2025-08-22",
    },
    {
        "name": "2025/2026",
        "api_url": "https://www.kicker-libero.de/api/sportsdata/v1/players-details/se-k00012025.csv",
        # Start from the reset day so the first CSV has total=0 → clean slate.
        "start": "2025-08-23",
        "end":   "2026-12-31",
    },
]

SEASON_BREAK_RATIO = 0.25  # If new total < prev_total * ratio → season break detected


def csv_date(path: str) -> str:
    """Extract date prefix 'YYYY-MM-DD' from filename like data_2025-01-22_14-30-00.csv."""
    name = Path(path).stem  # data_2025-01-22_14-30-00
    return name[5:15]       # 2025-01-22


def file_hash(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_csv(path: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, sep=";", dtype=str)
        df["Punkte"] = pd.to_numeric(df["Punkte"], errors="coerce").fillna(0)
        df["Notendurchschnitt"] = pd.to_numeric(df["Notendurchschnitt"], errors="coerce").fillna(0.0)
        df["Marktwert"] = pd.to_numeric(df["Marktwert"], errors="coerce").fillna(0).astype(int)
        df = df[df["Marktwert"] != config.MARKTWERT_PLACEHOLDER].copy()
        return df
    except Exception as e:
        log.warning("Überspringe %s: %s", Path(path).name, e)
        return None


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    schema = config.SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
    return conn


def ensure_season(conn: sqlite3.Connection, season_cfg: dict) -> int:
    row = conn.execute(
        "SELECT season_id FROM seasons WHERE season_name = ?", (season_cfg["name"],)
    ).fetchone()
    if row:
        return row["season_id"]
    conn.execute(
        "INSERT INTO seasons (season_name, api_url) VALUES (?, ?)",
        (season_cfg["name"], season_cfg["api_url"]),
    )
    conn.commit()
    return conn.execute(
        "SELECT season_id FROM seasons WHERE season_name = ?", (season_cfg["name"],)
    ).fetchone()["season_id"]


def upsert_master_data(conn: sqlite3.Connection, df: pd.DataFrame, season_id: int, timestamp: str) -> Dict[str, int]:
    """Insert/update players and player_seasonal_details. Returns {player_id: psd_id}."""
    psd_map = {}
    conn.execute("UPDATE player_seasonal_details SET is_active = 0 WHERE season_id = ?", (season_id,))

    for _, row in df.iterrows():
        pid = row["ID"]
        conn.execute(
            "INSERT OR IGNORE INTO players (player_id, first_name, last_name) VALUES (?, ?, ?)",
            (pid, row["Vorname"], row["Nachname"]),
        )
        conn.execute(
            """
            INSERT INTO player_seasonal_details (player_id, season_id, club, position, market_value, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(player_id, season_id) DO UPDATE SET
                club         = excluded.club,
                position     = excluded.position,
                market_value = excluded.market_value,
                is_active    = 1
            """,
            (pid, season_id, row["Verein"], row["Position"], int(row["Marktwert"])),
        )
        psd_id = conn.execute(
            "SELECT id FROM player_seasonal_details WHERE player_id = ? AND season_id = ?",
            (pid, season_id),
        ).fetchone()["id"]
        psd_map[pid] = psd_id

        # Record market value snapshot (only if changed or first entry)
        last_mv = conn.execute(
            "SELECT market_value FROM market_value_history WHERE player_seasonal_details_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (psd_id,),
        ).fetchone()
        if last_mv is None or last_mv["market_value"] != int(row["Marktwert"]):
            conn.execute(
                "INSERT INTO market_value_history (player_seasonal_details_id, market_value, recorded_at) VALUES (?, ?, ?)",
                (psd_id, int(row["Marktwert"]), timestamp),
            )

    conn.commit()
    return psd_map


def process_gameday(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    season_id: int,
    game_day_number: int,
    prev_points: dict[str, float],
    psd_map: Dict[str, int],
    timestamp: str,
    dry_run: bool,
) -> int:
    """Insert game_days + player_stats. Returns count of inserted stats."""
    if dry_run:
        count = sum(1 for _, row in df.iterrows() if row["ID"] in psd_map)
        log.info("  [DRY RUN] Spieltag %d: würde %d Spieler-Stats einfügen", game_day_number, count)
        return count

    conn.execute(
        "INSERT OR IGNORE INTO game_days (season_id, game_day_number, processed_at) VALUES (?, ?, ?)",
        (season_id, game_day_number, timestamp),
    )
    conn.commit()

    gd_id = conn.execute(
        "SELECT game_day_id FROM game_days WHERE season_id = ? AND game_day_number = ?",
        (season_id, game_day_number),
    ).fetchone()["game_day_id"]

    count = 0
    for _, row in df.iterrows():
        pid = row["ID"]
        if pid not in psd_map:
            continue
        spieltagspunkte = float(row["Punkte"]) - prev_points.get(pid, 0.0)
        conn.execute(
            """
            INSERT OR IGNORE INTO player_stats
                (player_seasonal_details_id, game_day_id, points, grade)
            VALUES (?, ?, ?, ?)
            """,
            (psd_map[pid], gd_id, round(spieltagspunkte), float(row["Notendurchschnitt"]) or None),
        )
        count += 1

    conn.execute(
        """
        INSERT INTO ingestion_log
            (csv_file, csv_hash, ingested_at, action, season_id, game_day_number, players_added)
        VALUES (?, ?, ?, 'gameday', ?, ?, ?)
        """,
        ("rebuild", "rebuild", timestamp, season_id, game_day_number, count),
    )
    conn.commit()
    return count


def main():
    parser = argparse.ArgumentParser(description="Rebuild KickerDB from CSV archive")
    parser.add_argument("--dry-run", action="store_true", help="Keine DB-Änderungen, nur Analyse")
    parser.add_argument("--threshold", type=int, default=config.SPIELTAG_SCHWELLWERT,
                        help=f"Punkte-Delta für Spieltag-Erkennung (default: {config.SPIELTAG_SCHWELLWERT})")
    parser.add_argument("--csv-dir", default=str(config.AUTODOWNLOAD_DIR),
                        help="Verzeichnis mit den CSV-Dateien")
    parser.add_argument("--db", default=str(config.DB_PATH),
                        help="Ausgabe-Datenbankpfad")
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    db_path = Path(args.db)
    threshold = args.threshold

    files = sorted(glob.glob(str(csv_dir / "data_*.csv")))
    if not files:
        log.error("Keine CSV-Dateien in %s gefunden.", csv_dir)
        sys.exit(1)

    log.info("Gefunden: %d CSV-Dateien (%s … %s)", len(files),
             Path(files[0]).name, Path(files[-1]).name)

    if args.dry_run:
        log.info("=== DRY-RUN Modus – keine DB-Änderungen ===")
        conn = init_db(Path(args.db).with_suffix(".dryrun.db"))
    else:
        if db_path.exists():
            backup = db_path.with_suffix(".backup.db")
            shutil.copy2(db_path, backup)
            log.info("Backup erstellt: %s", backup)
            db_path.unlink()
        conn = init_db(db_path)

    # Pre-insert seasons
    season_ids = {}
    for scfg in SEASON_CONFIG:
        if not args.dry_run:
            season_ids[scfg["name"]] = ensure_season(conn, scfg)

    # --- Main pass: process CSVs ---
    prev_total: float = 0.0
    prev_points: Dict[str, float] = {}      # player_id → cumulative points at last processed CSV
    current_season_cfg: Optional[dict] = None
    current_season_id: int = 0
    current_game_day: int = 0
    psd_map: Dict[str, int] = {}

    total_gamedays = 0
    total_stats = 0

    for csv_path in files:
        date_str = csv_date(csv_path)
        df = load_csv(csv_path)
        if df is None or df.empty:
            continue

        new_total = float(df["Punkte"].sum())
        # data_2026-05-18_17-00-02 → 2026-05-18T17:00:02
        raw = Path(csv_path).stem[5:]           # 2026-05-18_17-00-02
        date_part, time_raw = raw.split("_", 1) # 2026-05-18 | 17-00-02
        timestamp = f"{date_part}T{time_raw.replace('-', ':')}"

        # Determine which season this CSV belongs to
        matched_season = next(
            (s for s in SEASON_CONFIG if s["start"] <= date_str <= s["end"]), None
        )
        if matched_season is None:
            log.debug("  Kein Saison-Match für %s, überspringe.", Path(csv_path).name)
            continue

        # Season change
        if matched_season != current_season_cfg:
            log.info("--- Saison: %s ---", matched_season["name"])
            current_season_cfg = matched_season
            if not args.dry_run:
                current_season_id = season_ids[matched_season["name"]]
                psd_map = upsert_master_data(conn, df, current_season_id, timestamp)
            prev_total = 0.0
            prev_points = {}
            current_game_day = 0

        delta = new_total - prev_total

        if delta >= threshold:
            current_game_day += 1
            log.info(
                "  Spieltag %2d erkannt: delta=+%6.0f  (csv: %s)",
                current_game_day, delta, Path(csv_path).name,
            )

            if not args.dry_run and current_season_id:
                # Refresh master data for this Spieltag's CSV
                psd_map = upsert_master_data(conn, df, current_season_id, timestamp)

            count = process_gameday(
                conn, df, current_season_id, current_game_day,
                prev_points, psd_map, timestamp, args.dry_run,
            )
            total_stats += count
            total_gamedays += 1

            # Update prev_points to current cumulative totals
            prev_points = {row["ID"]: float(row["Punkte"]) for _, row in df.iterrows()}
            prev_total = new_total

        elif delta > 0:
            # Minor change (master data / market value update) — update but no new Spieltag
            if not args.dry_run and current_season_id:
                psd_map = upsert_master_data(conn, df, current_season_id, timestamp)

    conn.close()

    log.info("")
    log.info("=== Rebuild abgeschlossen ===")
    log.info("  Erkannte Spieltage: %d", total_gamedays)
    log.info("  Eingefügte Stats:   %d", total_stats)
    if not args.dry_run:
        log.info("  Datenbank:          %s", db_path)
    else:
        log.info("  [DRY RUN] – keine Änderungen an %s", db_path)


if __name__ == "__main__":
    main()
