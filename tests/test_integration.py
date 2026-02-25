"""Integration tests: real PDFs, real Playwright, mocked LLM.

These tests exercise the full pipeline end-to-end, only mocking the
LLM client to avoid requiring a real API key during CI.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.extraction import LLMClient
from src.logging_db import get_logs
from src.pipeline import run_pipeline
from src.schemas import ClaimData

INBOUND_DIR = Path(__file__).resolve().parent.parent / "inbound_claims"
FORM_PATH = Path(__file__).resolve().parent.parent / "web_form" / "index.html"
FORM_URL = f"file://{FORM_PATH}"

KNOWN_PDFS = [
    "claim_messy_03.pdf",
    "claim_standard_01.pdf",
    "claim_standard_02.pdf",
]

# LLM responses matching the 3 dummy PDFs
LLM_RESPONSES = {
    "claim_standard_01.pdf": json.dumps({
        "policyholder_name": "Maria Santos",
        "policy_number": "POL-2024-78432",
        "claim_amount": 12500.00,
        "incident_date": "2025-11-03",
    }),
    "claim_standard_02.pdf": json.dumps({
        "policyholder_name": "John Rivera",
        "policy_number": "POL-2025-00193",
        "claim_amount": 8750.50,
        "incident_date": "2026-01-15",
    }),
    "claim_messy_03.pdf": json.dumps({
        "policyholder_name": "Patricia Almeida",
        "policy_number": "POL-2023-55671",
        "claim_amount": 23100.00,
        "incident_date": "2025-08-22",
    }),
}


def _mock_llm_client(responses: dict[str, str]) -> MagicMock:
    """Create a mock LLMClient that returns responses based on PDF content."""
    client = MagicMock(spec=LLMClient)

    def chat_side_effect(system: str, user_text: str) -> str:
        for filename, response_json in responses.items():
            data = json.loads(response_json)
            if data["policyholder_name"].split()[0].lower() in user_text.lower():
                return response_json
        return "not valid json"

    client.chat.side_effect = chat_side_effect
    return client


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "integration_audit.db"


class TestFullPipelineIntegration:
    """E2E tests using real PDFs and real Playwright with mocked LLM."""

    @pytest.fixture()
    def known_inbox(self, tmp_path: Path) -> Path:
        """Create a temp inbox with only the 3 known test PDFs."""
        import shutil
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        for name in KNOWN_PDFS:
            shutil.copy(INBOUND_DIR / name, inbox / name)
        return inbox

    def test_all_three_pdfs_succeed(self, known_inbox: Path) -> None:
        """All 3 dummy PDFs should be processed successfully."""
        client = _mock_llm_client(LLM_RESPONSES)

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result"),
        ):
            results = run_pipeline(known_inbox, FORM_URL, headless=True)

        assert len(results) == 3
        assert all(r.status == "success" for r in results)

    def test_results_contain_correct_source_files(self, known_inbox: Path) -> None:
        client = _mock_llm_client(LLM_RESPONSES)

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result"),
        ):
            results = run_pipeline(known_inbox, FORM_URL, headless=True)

        source_files = sorted(r.source_file for r in results)
        assert source_files == sorted(KNOWN_PDFS)

    def test_log_result_called_for_each_pdf(self, known_inbox: Path) -> None:
        client = _mock_llm_client(LLM_RESPONSES)

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result") as mock_log,
        ):
            run_pipeline(known_inbox, FORM_URL, headless=True)

        assert mock_log.call_count == 3
        for call in mock_log.call_args_list:
            assert isinstance(call.kwargs.get("claim") or call.args[1], ClaimData)


class TestFailureScenarios:
    """Ensure the pipeline handles every failure gracefully."""

    def test_corrupted_pdf_pipeline_continues(self, tmp_path: Path) -> None:
        """A corrupted PDF should not crash the pipeline."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        (inbox / "corrupted.pdf").write_bytes(b"not a pdf at all")
        import shutil
        shutil.copy(INBOUND_DIR / "claim_standard_01.pdf", inbox / "valid.pdf")

        client = _mock_llm_client(LLM_RESPONSES)

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result"),
        ):
            results = run_pipeline(inbox, FORM_URL, headless=True)

        assert len(results) == 2
        statuses = {r.source_file: r.status for r in results}
        assert statuses["corrupted.pdf"] == "extraction_failed"
        assert statuses["valid.pdf"] == "success"

    def test_llm_returns_garbage_both_attempts(self, tmp_path: Path) -> None:
        """LLM returns invalid JSON on both attempts -> extraction_failed."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        import shutil
        shutil.copy(INBOUND_DIR / "claim_standard_01.pdf", inbox / "claim.pdf")

        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "totally garbage {{{ not json"

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result"),
        ):
            results = run_pipeline(inbox, FORM_URL, headless=True)

        assert len(results) == 1
        assert results[0].status == "extraction_failed"

    def test_form_with_missing_field(self, tmp_path: Path) -> None:
        """A broken form missing a field -> automation_failed."""
        broken_html = FORM_PATH.read_text().replace(
            'id="claim_amount"', 'id="amount_renamed"'
        )
        broken_form = tmp_path / "broken.html"
        broken_form.write_text(broken_html)
        broken_url = f"file://{broken_form}"

        inbox = tmp_path / "inbox"
        inbox.mkdir()
        import shutil
        shutil.copy(INBOUND_DIR / "claim_standard_01.pdf", inbox / "claim.pdf")

        client = _mock_llm_client(LLM_RESPONSES)

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result"),
        ):
            results = run_pipeline(inbox, broken_url, headless=True)

        assert len(results) == 1
        assert results[0].status == "automation_failed"
        assert results[0].error_message is not None

    def test_empty_inbox_folder(self, tmp_path: Path) -> None:
        """Empty inbox returns empty list, no errors."""
        inbox = tmp_path / "empty_inbox"
        inbox.mkdir()

        results = run_pipeline(inbox, FORM_URL, headless=True)
        assert results == []

    def test_nonexistent_inbox_folder(self) -> None:
        """Non-existent inbox path returns empty list, no crash."""
        results = run_pipeline(Path("/nonexistent/path"), FORM_URL, headless=True)
        assert results == []

    def test_no_api_connection(self, tmp_path: Path) -> None:
        """API connection error -> extraction_failed, pipeline continues."""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        import shutil
        shutil.copy(INBOUND_DIR / "claim_standard_01.pdf", inbox / "claim.pdf")

        client = MagicMock(spec=LLMClient)
        client.chat.side_effect = httpx.ConnectError("Connection refused")

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result"),
        ):
            results = run_pipeline(inbox, FORM_URL, headless=True)

        assert len(results) == 1
        assert results[0].status == "extraction_failed"


class TestAuditLogIntegration:
    """Verify audit logging works end-to-end with real DB."""

    def test_results_persisted_to_sqlite(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        import shutil
        shutil.copy(INBOUND_DIR / "claim_standard_01.pdf", inbox / "claim.pdf")

        db = tmp_path / "audit.db"
        client = _mock_llm_client(LLM_RESPONSES)

        with (
            patch("src.extraction.LLMClient", return_value=client),
            patch("src.pipeline.log_result", wraps=lambda result, claim=None: _real_log(result, claim, db)),
        ):
            results = run_pipeline(inbox, FORM_URL, headless=True)

        logs = get_logs(db_path=db)
        assert len(logs) == 1
        assert logs[0]["status"] == "success"
        assert logs[0]["policyholder_name"] == "Maria Santos"


def _real_log(result, claim, db_path):
    """Call the real log_result with a custom db_path."""
    from src.logging_db import log_result
    log_result(result, claim=claim, db_path=db_path)
