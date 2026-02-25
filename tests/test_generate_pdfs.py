"""Tests for dummy claim PDF generation and readability."""

from pathlib import Path

from pypdf import PdfReader

INBOUND_DIR = Path(__file__).resolve().parent.parent / "inbound_claims"

EXPECTED_PDFS = [
    "claim_standard_01.pdf",
    "claim_standard_02.pdf",
    "claim_messy_03.pdf",
]


class TestDummyPDFs:
    """Verify all dummy claim PDFs exist and are readable with pypdf."""

    def test_all_pdfs_exist(self) -> None:
        for name in EXPECTED_PDFS:
            path = INBOUND_DIR / name
            assert path.exists(), f"Missing PDF: {path}"

    def test_pdfs_are_readable(self) -> None:
        for name in EXPECTED_PDFS:
            reader = PdfReader(INBOUND_DIR / name)
            assert len(reader.pages) >= 1

    def test_pdfs_contain_text(self) -> None:
        for name in EXPECTED_PDFS:
            reader = PdfReader(INBOUND_DIR / name)
            text = reader.pages[0].extract_text()
            assert len(text) > 50, f"{name} has too little text: {len(text)} chars"

    def test_standard_01_has_expected_fields(self) -> None:
        text = PdfReader(INBOUND_DIR / "claim_standard_01.pdf").pages[0].extract_text()
        assert "Maria Santos" in text
        assert "POL-2024-78432" in text
        assert "12,500" in text
        assert "2025-11-03" in text

    def test_standard_02_has_expected_fields(self) -> None:
        text = PdfReader(INBOUND_DIR / "claim_standard_02.pdf").pages[0].extract_text()
        assert "John Rivera" in text
        assert "POL-2025-00193" in text
        assert "8,750" in text
        assert "2026-01-15" in text

    def test_messy_03_has_expected_fields(self) -> None:
        text = PdfReader(INBOUND_DIR / "claim_messy_03.pdf").pages[0].extract_text()
        assert "Patricia Almeida" in text
        assert "POL-2023-55671" in text
        assert "23,100" in text
        assert "2025-08-22" in text
