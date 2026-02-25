"""Tests for the pipeline orchestrator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline import _print_summary, run_pipeline
from src.schemas import ClaimData, ProcessingResult

SAMPLE_CLAIM = ClaimData(
    policyholder_name="Maria Santos",
    policy_number="POL-2024-001",
    claim_amount=15000.00,
    incident_date="2024-11-15",
    raw_source="claim_01.pdf",
    confidence=0.85,
)

SUCCESS_RESULT = ProcessingResult(
    status="success",
    timestamp="2024-11-20T10:00:00+00:00",
    source_file="claim_01.pdf",
)

AUTOMATION_FAILED_RESULT = ProcessingResult(
    status="automation_failed",
    timestamp="2024-11-20T10:01:00+00:00",
    source_file="claim_02.pdf",
    error_message="Timeout",
)


@pytest.fixture()
def mock_pipeline(tmp_path: Path):
    """Patch all pipeline dependencies and yield the mocks."""
    db_path = tmp_path / "test.db"
    with (
        patch("src.pipeline.scan_inbox") as mock_scan,
        patch("src.pipeline.extract_text") as mock_extract_text,
        patch("src.pipeline.extract_claim_data") as mock_extract_claim,
        patch("src.pipeline.fill_web_form") as mock_fill,
        patch("src.pipeline.log_result") as mock_log,
    ):
        yield {
            "scan_inbox": mock_scan,
            "extract_text": mock_extract_text,
            "extract_claim_data": mock_extract_claim,
            "fill_web_form": mock_fill,
            "log_result": mock_log,
            "tmp_path": tmp_path,
        }


class TestRunPipeline:
    """Tests for the main run_pipeline function."""

    def test_empty_inbox(self, mock_pipeline: dict) -> None:
        mock_pipeline["scan_inbox"].return_value = []

        results = run_pipeline(Path("inbox"), "http://localhost/form")

        assert results == []
        mock_pipeline["extract_text"].assert_not_called()

    def test_single_pdf_success(self, mock_pipeline: dict) -> None:
        mock_pipeline["scan_inbox"].return_value = [Path("inbox/claim_01.pdf")]
        mock_pipeline["extract_text"].return_value = "raw text from pdf"
        mock_pipeline["extract_claim_data"].return_value = SAMPLE_CLAIM
        mock_pipeline["fill_web_form"].return_value = SUCCESS_RESULT

        results = run_pipeline(Path("inbox"), "http://localhost/form")

        assert len(results) == 1
        assert results[0].status == "success"
        mock_pipeline["log_result"].assert_called_once_with(
            SUCCESS_RESULT, claim=SAMPLE_CLAIM
        )

    def test_text_extraction_fails(self, mock_pipeline: dict) -> None:
        mock_pipeline["scan_inbox"].return_value = [Path("inbox/bad.pdf")]
        mock_pipeline["extract_text"].return_value = None

        results = run_pipeline(Path("inbox"), "http://localhost/form")

        assert len(results) == 1
        assert results[0].status == "extraction_failed"
        assert "text from PDF" in results[0].error_message
        mock_pipeline["extract_claim_data"].assert_not_called()
        mock_pipeline["fill_web_form"].assert_not_called()

    def test_llm_extraction_fails(self, mock_pipeline: dict) -> None:
        mock_pipeline["scan_inbox"].return_value = [Path("inbox/messy.pdf")]
        mock_pipeline["extract_text"].return_value = "some messy text"
        mock_pipeline["extract_claim_data"].return_value = None

        results = run_pipeline(Path("inbox"), "http://localhost/form")

        assert len(results) == 1
        assert results[0].status == "extraction_failed"
        assert "LLM" in results[0].error_message
        mock_pipeline["fill_web_form"].assert_not_called()

    def test_automation_fails(self, mock_pipeline: dict) -> None:
        mock_pipeline["scan_inbox"].return_value = [Path("inbox/claim_02.pdf")]
        mock_pipeline["extract_text"].return_value = "raw text"
        mock_pipeline["extract_claim_data"].return_value = SAMPLE_CLAIM
        mock_pipeline["fill_web_form"].return_value = AUTOMATION_FAILED_RESULT

        results = run_pipeline(Path("inbox"), "http://localhost/form")

        assert len(results) == 1
        assert results[0].status == "automation_failed"
        mock_pipeline["log_result"].assert_called_once_with(
            AUTOMATION_FAILED_RESULT, claim=SAMPLE_CLAIM
        )

    def test_multiple_pdfs_mixed_results(self, mock_pipeline: dict) -> None:
        """Pipeline continues processing after individual failures."""
        mock_pipeline["scan_inbox"].return_value = [
            Path("inbox/good.pdf"),
            Path("inbox/bad_text.pdf"),
            Path("inbox/bad_llm.pdf"),
        ]
        mock_pipeline["extract_text"].side_effect = [
            "good text",
            None,
            "messy text",
        ]
        mock_pipeline["extract_claim_data"].side_effect = [
            SAMPLE_CLAIM,
            None,
        ]
        mock_pipeline["fill_web_form"].return_value = SUCCESS_RESULT

        results = run_pipeline(Path("inbox"), "http://localhost/form")

        assert len(results) == 3
        assert results[0].status == "success"
        assert results[1].status == "extraction_failed"
        assert results[2].status == "extraction_failed"
        assert mock_pipeline["log_result"].call_count == 3

    def test_headless_passed_to_fill_web_form(self, mock_pipeline: dict) -> None:
        mock_pipeline["scan_inbox"].return_value = [Path("inbox/claim.pdf")]
        mock_pipeline["extract_text"].return_value = "text"
        mock_pipeline["extract_claim_data"].return_value = SAMPLE_CLAIM
        mock_pipeline["fill_web_form"].return_value = SUCCESS_RESULT

        run_pipeline(Path("inbox"), "http://localhost/form", headless=False)

        mock_pipeline["fill_web_form"].assert_called_once_with(
            SAMPLE_CLAIM, "http://localhost/form", headless=False
        )


class TestPrintSummary:
    """Tests for the summary output."""

    def test_all_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = [SUCCESS_RESULT, SUCCESS_RESULT]
        _print_summary(results)

        output = capsys.readouterr().out
        assert "2 processed" in output
        assert "2 succeeded" in output
        assert "0 failed" in output

    def test_mixed(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = [SUCCESS_RESULT, AUTOMATION_FAILED_RESULT]
        _print_summary(results)

        output = capsys.readouterr().out
        assert "2 processed" in output
        assert "1 succeeded" in output
        assert "1 failed" in output

    def test_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_summary([])

        output = capsys.readouterr().out
        assert "0 processed" in output
