"""Tests for the SQLite audit log module."""

from pathlib import Path

import pytest

from src.logging_db import get_logs, log_result
from src.schemas import ClaimData, ProcessingResult


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path for each test."""
    return tmp_path / "test_audit.db"


SAMPLE_CLAIM = ClaimData(
    policyholder_name="Maria Santos",
    policy_number="POL-2024-001",
    claim_amount=15000.00,
    incident_date="2024-11-15",
    raw_source="claim_standard_01.pdf",
    confidence=0.85,
)

SUCCESS_RESULT = ProcessingResult(
    status="success",
    timestamp="2024-11-20T10:00:00+00:00",
    source_file="claim_standard_01.pdf",
)

EXTRACTION_FAILED_RESULT = ProcessingResult(
    status="extraction_failed",
    timestamp="2024-11-20T10:01:00+00:00",
    source_file="claim_messy_03.pdf",
    error_message="LLM returned invalid JSON",
)

AUTOMATION_FAILED_RESULT = ProcessingResult(
    status="automation_failed",
    timestamp="2024-11-20T10:02:00+00:00",
    source_file="claim_standard_02.pdf",
    error_message="Timeout waiting for #confirmation",
    screenshot_path="screenshots/2024-11-20T10-02-00_POL-002.png",
)


class TestLogResult:
    """Tests for writing records to the audit log."""

    def test_log_success_with_claim(self, db_path: Path) -> None:
        log_result(SUCCESS_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)

        logs = get_logs(db_path=db_path)
        assert len(logs) == 1
        row = logs[0]
        assert row["status"] == "success"
        assert row["policyholder_name"] == "Maria Santos"
        assert row["policy_number"] == "POL-2024-001"
        assert row["claim_amount"] == 15000.00
        assert row["error_message"] is None
        assert row["screenshot_path"] is None

    def test_log_extraction_failure_without_claim(self, db_path: Path) -> None:
        log_result(EXTRACTION_FAILED_RESULT, claim=None, db_path=db_path)

        logs = get_logs(db_path=db_path)
        assert len(logs) == 1
        row = logs[0]
        assert row["status"] == "extraction_failed"
        assert row["policyholder_name"] is None
        assert row["policy_number"] is None
        assert row["claim_amount"] is None
        assert row["error_message"] == "LLM returned invalid JSON"

    def test_log_automation_failure_with_screenshot(self, db_path: Path) -> None:
        log_result(AUTOMATION_FAILED_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)

        logs = get_logs(db_path=db_path)
        assert len(logs) == 1
        row = logs[0]
        assert row["status"] == "automation_failed"
        assert row["screenshot_path"] == "screenshots/2024-11-20T10-02-00_POL-002.png"

    def test_multiple_records(self, db_path: Path) -> None:
        log_result(SUCCESS_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)
        log_result(EXTRACTION_FAILED_RESULT, claim=None, db_path=db_path)
        log_result(AUTOMATION_FAILED_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)

        logs = get_logs(db_path=db_path)
        assert len(logs) == 3
        assert [r["status"] for r in logs] == [
            "success",
            "extraction_failed",
            "automation_failed",
        ]


class TestGetLogs:
    """Tests for reading records from the audit log."""

    def test_empty_database(self, db_path: Path) -> None:
        logs = get_logs(db_path=db_path)
        assert logs == []

    def test_returns_dicts_with_all_columns(self, db_path: Path) -> None:
        log_result(SUCCESS_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)

        logs = get_logs(db_path=db_path)
        row = logs[0]
        expected_keys = {
            "id",
            "timestamp",
            "source_file",
            "status",
            "policyholder_name",
            "policy_number",
            "claim_amount",
            "error_message",
            "screenshot_path",
        }
        assert set(row.keys()) == expected_keys

    def test_records_ordered_by_id(self, db_path: Path) -> None:
        log_result(SUCCESS_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)
        log_result(EXTRACTION_FAILED_RESULT, claim=None, db_path=db_path)

        logs = get_logs(db_path=db_path)
        assert logs[0]["id"] < logs[1]["id"]

    def test_autoincrement_ids(self, db_path: Path) -> None:
        log_result(SUCCESS_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)
        log_result(SUCCESS_RESULT, claim=SAMPLE_CLAIM, db_path=db_path)

        logs = get_logs(db_path=db_path)
        assert logs[0]["id"] == 1
        assert logs[1]["id"] == 2
