"""Tests for the Playwright automation module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.automation import _capture_screenshot, fill_web_form
from src.schemas import ClaimData

FORM_PATH = Path(__file__).resolve().parent.parent / "web_form" / "index.html"
FORM_URL = f"file://{FORM_PATH}"

SAMPLE_CLAIM = ClaimData(
    policyholder_name="Maria Santos",
    policy_number="POL-2024-001",
    claim_amount=15000.00,
    incident_date="2024-11-15",
    raw_source="claim_standard_01.pdf",
    confidence=0.85,
)


class TestFillWebFormIntegration:
    """Integration tests that use the real HTML form with Playwright."""

    def test_successful_submission(self) -> None:
        result = fill_web_form(SAMPLE_CLAIM, FORM_URL, headless=True)

        assert result.status == "success"
        assert result.source_file == "claim_standard_01.pdf"
        assert result.error_message is None
        assert result.screenshot_path is None

    def test_fields_filled_correctly(self) -> None:
        """Verify the form fields contain the expected values after filling."""
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(FORM_URL, wait_until="domcontentloaded")
            page.fill("#policyholder_name", SAMPLE_CLAIM.policyholder_name)
            page.fill("#policy_number", SAMPLE_CLAIM.policy_number)
            page.fill("#claim_amount", str(SAMPLE_CLAIM.claim_amount))
            page.fill("#incident_date", SAMPLE_CLAIM.incident_date)

            assert page.input_value("#policyholder_name") == "Maria Santos"
            assert page.input_value("#policy_number") == "POL-2024-001"
            assert page.input_value("#claim_amount") == "15000.0"
            assert page.input_value("#incident_date") == "2024-11-15"
        finally:
            browser.close()
            pw.stop()

    def test_missing_selector_fails(self, tmp_path: Path) -> None:
        """Form with a removed field should cause automation_failed."""
        broken_html = FORM_PATH.read_text().replace(
            'id="claim_amount"', 'id="amount_renamed"'
        )
        broken_form = tmp_path / "broken.html"
        broken_form.write_text(broken_html)
        broken_url = f"file://{broken_form}"

        result = fill_web_form(SAMPLE_CLAIM, broken_url, headless=True)

        assert result.status == "automation_failed"
        assert result.error_message is not None

    def test_invalid_url_fails(self) -> None:
        result = fill_web_form(SAMPLE_CLAIM, "file:///nonexistent/form.html", headless=True)

        assert result.status == "automation_failed"
        assert result.error_message is not None


class TestCaptureScreenshot:
    """Unit tests for the screenshot helper."""

    def test_returns_none_when_page_is_none(self) -> None:
        result = _capture_screenshot(None, "POL-001", "2024-01-01T00:00:00")
        assert result is None

    def test_saves_screenshot(self, tmp_path: Path) -> None:
        mock_page = MagicMock()

        with patch("src.automation.SCREENSHOTS_DIR", tmp_path):
            result = _capture_screenshot(mock_page, "POL-001", "2024-01-01T12:00:00p00:00")

        assert result is not None
        mock_page.screenshot.assert_called_once()

    def test_returns_none_on_screenshot_error(self) -> None:
        mock_page = MagicMock()
        mock_page.screenshot.side_effect = RuntimeError("browser crashed")

        result = _capture_screenshot(mock_page, "POL-001", "2024-01-01T00:00:00")
        assert result is None
