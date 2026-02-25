"""PDF ingestion: scan inbox folder and extract raw text from claim PDFs."""

import logging
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


def scan_inbox(path: Path) -> list[Path]:
    """Return a sorted list of PDF files found in the given directory."""
    if not path.is_dir():
        logger.error("Inbox path does not exist or is not a directory: %s", path)
        return []

    pdfs = sorted(path.glob("*.pdf"))
    logger.info("Found %d PDF(s) in %s", len(pdfs), path)
    return pdfs


def extract_text(pdf_path: Path) -> str | None:
    """Extract raw text from a PDF file. Returns None on failure."""
    try:
        doc = pymupdf.open(pdf_path)
        pages_text = [page.get_text() or "" for page in doc]
        doc.close()
        text = "\n".join(pages_text).strip()

        if not text:
            logger.warning("PDF has no extractable text: %s", pdf_path)
            return None

        logger.info("Extracted %d chars from %s", len(text), pdf_path.name)
        return text

    except Exception as exc:
        logger.error("Failed to read PDF %s: %s", pdf_path, exc)
        return None
