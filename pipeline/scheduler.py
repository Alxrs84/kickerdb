"""
Dauerhaft laufender Scheduler-Prozess im Docker-Container.

Ablauf alle POLL_INTERVAL Sekunden:
  1. autodownload.py aufrufen → lädt neue CSV herunter (falls geändert)
  2. ingest.py aufrufen → verarbeitet die neueste CSV

Läuft als eigener Service im docker-compose.yml.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

POLL_INTERVAL = 600  # seconds between download attempts
PYTHON = sys.executable
BASE_DIR = Path(__file__).parent.parent


def run(script: Path, *args: str) -> int:
    cmd = [PYTHON, str(script)] + list(args)
    log.info("Starte: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        log.warning("%s beendet mit Code %d", script.name, result.returncode)
    return result.returncode


def main() -> None:
    log.info("Scheduler gestartet (Intervall: %ds)", POLL_INTERVAL)
    autodownload = BASE_DIR / "pipeline" / "autodownload.py"
    ingest = BASE_DIR / "pipeline" / "ingest.py"

    while True:
        try:
            run(autodownload)
            run(ingest)
        except Exception as e:
            log.error("Unerwarteter Fehler im Scheduler-Loop: %s", e, exc_info=True)

        log.info("Nächster Lauf in %ds …", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
