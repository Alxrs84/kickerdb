"""
Lädt die aktuelle Spieler-CSV von der Kicker-API herunter.
Speichert nur, wenn sich der Inhalt (SHA-256) geändert hat.
"""

import hashlib
import logging
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DOWNLOAD_DIR = config.AUTODOWNLOAD_DIR
HASH_FILE = DOWNLOAD_DIR / "last_hash.txt"


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_last_hash() -> str:
    if HASH_FILE.exists():
        return HASH_FILE.read_text().strip()
    return ""


def main() -> None:
    import sqlite3

    # Determine download URL from the active season in the DB
    try:
        conn = sqlite3.connect(config.DB_PATH)
        row = conn.execute(
            "SELECT api_url FROM seasons ORDER BY season_id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        url = row[0] if row else None
    except Exception:
        url = None

    if not url:
        log.error("Keine API-URL in der Datenbank gefunden. Bitte Saison mit api_url einrichten.")
        sys.exit(1)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = DOWNLOAD_DIR / "temp.csv"

    try:
        log.info("Lade CSV von: %s", url)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        temp_path.write_bytes(r.content)
    except requests.RequestException as e:
        log.error("Download fehlgeschlagen: %s", e)
        temp_path.unlink(missing_ok=True)
        sys.exit(1)

    new_hash = file_hash(temp_path)
    old_hash = load_last_hash()

    if new_hash == old_hash:
        log.info("Keine Änderung festgestellt.")
        temp_path.unlink(missing_ok=True)
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = DOWNLOAD_DIR / f"data_{timestamp}.csv"
    temp_path.rename(dest)
    HASH_FILE.write_text(new_hash)
    log.info("Neue Version gespeichert: %s", dest.name)


if __name__ == "__main__":
    main()
