"""Pipeline orchestrator: chains ingestion, extraction, automation, and logging."""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.automation import fill_web_form
from src.extraction import extract_claim_data
from src.ingestion import extract_text, scan_inbox
from src.logging_db import log_result
from src.schemas import ProcessingResult

logger = logging.getLogger(__name__)

# ANSI colors (disabled when not a TTY)
_USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
GREEN = "\033[32m" if _USE_COLOR else ""
RED = "\033[31m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
RESET = "\033[0m" if _USE_COLOR else ""


def run_pipeline(
    inbox_path: Path,
    form_url: str,
    headless: bool = True,
) -> list[ProcessingResult]:
    """Process all claim PDFs in the inbox folder.

    For each PDF: extract text -> LLM extraction -> fill web form -> log result.
    Failures in one PDF do not affect processing of others.
    """
    pdfs = scan_inbox(inbox_path)
    if not pdfs:
        logger.info("No PDFs to process")
        return []

    results: list[ProcessingResult] = []

    for pdf_path in pdfs:
        source_file = pdf_path.name
        logger.info("Processing %s", source_file)

        # Step 1: Extract raw text
        raw_text = extract_text(pdf_path)
        if raw_text is None:
            result = ProcessingResult(
                status="extraction_failed",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_file=source_file,
                error_message="Failed to extract text from PDF",
            )
            log_result(result, claim=None)
            results.append(result)
            _print_status(result)
            continue

        # Step 2: LLM extraction
        claim = extract_claim_data(raw_text, source_file)
        if claim is None:
            result = ProcessingResult(
                status="extraction_failed",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_file=source_file,
                error_message="LLM failed to extract structured data",
            )
            log_result(result, claim=None)
            results.append(result)
            _print_status(result)
            continue

        # Step 3: Fill web form
        result = fill_web_form(claim, form_url, headless=headless)

        # Step 4: Log result
        log_result(result, claim=claim)
        results.append(result)
        _print_status(result)

    _print_summary(results)
    return results


def _print_status(result: ProcessingResult) -> None:
    """Print a colored status line for a single PDF."""
    if result.status == "success":
        print(f"  {GREEN}OK{RESET}  {result.source_file}")
    else:
        msg = result.error_message or result.status
        print(f"  {RED}FAIL{RESET}  {result.source_file} — {msg}")


def _print_summary(results: list[ProcessingResult]) -> None:
    """Print a colored summary of the pipeline run."""
    total = len(results)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = total - succeeded
    print(
        f"\n{BOLD}Pipeline complete:{RESET} {total} processed, "
        f"{GREEN}{succeeded} succeeded{RESET}, "
        f"{RED}{failed} failed{RESET}"
    )


def main() -> None:
    """CLI entry point with argparse."""
    parser = argparse.ArgumentParser(
        description="Process insurance claim PDFs and submit to web form",
    )
    parser.add_argument(
        "--inbox",
        type=Path,
        default=Path("inbound_claims"),
        help="Path to folder containing claim PDFs (default: inbound_claims)",
    )
    parser.add_argument(
        "--form-url",
        type=str,
        default="http://localhost:8000/web_form/index.html",
        help="URL of the claim submission form",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in headful mode (visible window)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_pipeline(
        inbox_path=args.inbox,
        form_url=args.form_url,
        headless=not args.headful,
    )


if __name__ == "__main__":
    main()
