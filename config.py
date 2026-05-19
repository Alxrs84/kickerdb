import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

DB_PATH = Path(os.getenv("KICKERDB_PATH", BASE_DIR / "db" / "kicker_main.db"))
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
AUTODOWNLOAD_DIR = Path(os.getenv("AUTODOWNLOAD_DIR", BASE_DIR / "autodownload"))

# How much the sum of all player points must increase to count as a new Spieltag.
# ~530 active players * avg ~2 pts = ~1100 pts per Spieltag. 700 is a safe lower bound
# that avoids counting minor corrections (which are typically <200 pts total).
SPIELTAG_SCHWELLWERT = int(os.getenv("SPIELTAG_SCHWELLWERT", "700"))

# Market value above this is treated as "no data" placeholder
MARKTWERT_PLACEHOLDER = int(os.getenv("MARKTWERT_PLACEHOLDER", "999000000"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
