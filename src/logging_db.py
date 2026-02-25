"""SQLite audit log for the insurance claim processing pipeline."""

import logging
import sqlite3
from pathlib import Path

from src.schemas import ClaimData, ProcessingResult

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("audit.db")

CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source_file TEXT NOT NULL,
    status TEXT NOT NULL,
    policyholder_name TEXT,
    policy_number TEXT,
    claim_amount REAL,
    error_message TEXT,
    screenshot_path TEXT
)"""

INSERT_SQL = """\
INSERT INTO processing_log
    (timestamp, source_file, status, policyholder_name, policy_number,
     claim_amount, error_message, screenshot_path)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a connection and ensure the table exists."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn


def log_result(
    result: ProcessingResult,
    claim: ClaimData | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Write a processing result to the audit log."""
    conn = _get_connection(db_path)
    try:
        conn.execute(
            INSERT_SQL,
            (
                result.timestamp,
                result.source_file,
                result.status,
                claim.policyholder_name if claim else None,
                claim.policy_number if claim else None,
                claim.claim_amount if claim else None,
                result.error_message,
                result.screenshot_path,
            ),
        )
        conn.commit()
        logger.info("Logged %s for %s", result.status, result.source_file)
    except sqlite3.Error as exc:
        logger.error("Failed to log result for %s: %s", result.source_file, exc)
    finally:
        conn.close()


def get_logs(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Retrieve all processing log entries as a list of dicts."""
    conn = _get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM processing_log ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("Failed to read logs: %s", exc)
        return []
    finally:
        conn.close()
