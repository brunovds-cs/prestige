"""Playwright-based browser automation to fill insurance claim web forms."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from src.schemas import ClaimData, ProcessingResult

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("screenshots")


def fill_web_form(
    claim: ClaimData,
    form_url: str,
    headless: bool = True,
) -> ProcessingResult:
    """Fill and submit an insurance claim web form using Playwright.

    Opens a Chromium browser, navigates to the form, fills each field,
    clicks submit, and waits for the confirmation element.
    Captures a screenshot on any failure.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    pw = sync_playwright().start()
    browser = None
    page = None
    try:
        browser = pw.chromium.launch(
            headless=headless,
            slow_mo=400 if not headless else 0,
        )
        page = browser.new_page()

        page.goto(form_url, wait_until="domcontentloaded")

        page.fill("#policyholder_name", claim.policyholder_name)
        page.fill("#policy_number", claim.policy_number)
        page.fill("#claim_amount", str(claim.claim_amount))
        page.fill("#incident_date", claim.incident_date)

        page.click("#submit-btn")

        page.wait_for_selector("#confirmation", state="visible", timeout=5000)

        logger.info(
            "Successfully submitted form for %s (%s)",
            claim.policyholder_name,
            claim.policy_number,
        )
        return ProcessingResult(
            status="success",
            timestamp=timestamp,
            source_file=claim.raw_source,
        )

    except (PlaywrightTimeout, Exception) as exc:
        logger.error(
            "Automation failed for %s: %s",
            claim.raw_source,
            exc,
        )
        screenshot_path = _capture_screenshot(
            page,
            claim.policy_number,
            timestamp,
        )
        return ProcessingResult(
            status="automation_failed",
            timestamp=timestamp,
            source_file=claim.raw_source,
            error_message=str(exc),
            screenshot_path=str(screenshot_path) if screenshot_path else None,
        )

    finally:
        if browser:
            browser.close()
        pw.stop()


def _capture_screenshot(
    page: object | None,
    policy_number: str,
    timestamp: str,
) -> Path | None:
    """Save a screenshot of the current page state. Returns the path or None."""
    if page is None:
        return None

    try:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_ts = timestamp.replace(":", "-").replace("+", "p")
        filename = f"{safe_ts}_{policy_number}.png"
        path = SCREENSHOTS_DIR / filename
        page.screenshot(path=str(path))  # type: ignore[union-attr]
        logger.info("Screenshot saved: %s", path)
        return path
    except Exception as exc:
        logger.error("Failed to capture screenshot: %s", exc)
        return None
