PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS players (
    player_id   TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seasons (
    season_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    season_name      TEXT UNIQUE NOT NULL,
    api_url          TEXT NOT NULL,
    budget_limit     INTEGER NOT NULL DEFAULT 42000000,
    kader_gk         INTEGER NOT NULL DEFAULT 3,
    kader_def        INTEGER NOT NULL DEFAULT 7,
    kader_mid        INTEGER NOT NULL DEFAULT 7,
    kader_fwd        INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS player_seasonal_details (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    season_id    INTEGER NOT NULL REFERENCES seasons(season_id),
    club         TEXT,
    position     TEXT CHECK(position IN ('GOALKEEPER','DEFENDER','MIDFIELDER','FORWARD')),
    market_value INTEGER,
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    UNIQUE(player_id, season_id)
);

CREATE TABLE IF NOT EXISTS market_value_history (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_seasonal_details_id INTEGER NOT NULL REFERENCES player_seasonal_details(id),
    market_value               INTEGER NOT NULL,
    recorded_at                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_days (
    game_day_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id       INTEGER NOT NULL REFERENCES seasons(season_id),
    game_day_number INTEGER NOT NULL,
    processed_at    TEXT,
    UNIQUE(season_id, game_day_number)
);

CREATE TABLE IF NOT EXISTS player_stats (
    stat_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    player_seasonal_details_id INTEGER NOT NULL REFERENCES player_seasonal_details(id),
    game_day_id                INTEGER NOT NULL REFERENCES game_days(game_day_id),
    points                     INTEGER NOT NULL DEFAULT 0,
    grade                      REAL,
    UNIQUE(player_seasonal_details_id, game_day_id)
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    csv_file        TEXT NOT NULL,
    csv_hash        TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    action          TEXT NOT NULL CHECK(action IN ('master_update','gameday','skipped','error')),
    season_id       INTEGER,
    game_day_number INTEGER,
    players_added   INTEGER DEFAULT 0,
    players_updated INTEGER DEFAULT 0,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_psd_player ON player_seasonal_details(player_id);
CREATE INDEX IF NOT EXISTS idx_psd_season ON player_seasonal_details(season_id);
CREATE INDEX IF NOT EXISTS idx_gd_season  ON game_days(season_id);
CREATE INDEX IF NOT EXISTS idx_ps_psd     ON player_stats(player_seasonal_details_id);
CREATE INDEX IF NOT EXISTS idx_ps_gd      ON player_stats(game_day_id);
CREATE INDEX IF NOT EXISTS idx_mvh_psd    ON market_value_history(player_seasonal_details_id);
CREATE INDEX IF NOT EXISTS idx_mvh_time   ON market_value_history(recorded_at);

CREATE VIEW IF NOT EXISTS player_season_stats AS
    SELECT
        p.player_id,
        p.first_name || ' ' || p.last_name AS full_name,
        s.season_id,
        s.season_name,
        psd.id AS seasonal_details_id,
        psd.club,
        psd.position,
        psd.market_value,
        psd.is_active,
        COUNT(ps.stat_id)  AS games_played,
        COALESCE(SUM(ps.points), 0) AS total_points,
        AVG(NULLIF(ps.grade, 0))    AS avg_grade
    FROM players p
    JOIN player_seasonal_details psd ON p.player_id = psd.player_id
    JOIN seasons s ON psd.season_id = s.season_id
    LEFT JOIN player_stats ps ON psd.id = ps.player_seasonal_details_id
    GROUP BY p.player_id, s.season_id;
