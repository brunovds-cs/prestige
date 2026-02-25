"""Tests for the ingestion module: inbox scanning and PDF text extraction."""

from pathlib import Path

from src.ingestion import extract_text, scan_inbox

INBOUND_DIR = Path(__file__).resolve().parent.parent / "inbound_claims"


class TestScanInbox:
    """Tests for scan_inbox."""

    def test_finds_all_pdfs(self) -> None:
        pdfs = scan_inbox(INBOUND_DIR)
        assert len(pdfs) >= 3
        assert all(p.suffix == ".pdf" for p in pdfs)

    def test_returns_sorted_list(self) -> None:
        pdfs = scan_inbox(INBOUND_DIR)
        names = [p.name for p in pdfs]
        assert names == sorted(names)

    def test_empty_folder(self, tmp_path: Path) -> None:
        pdfs = scan_inbox(tmp_path)
        assert pdfs == []

    def test_folder_with_no_pdfs(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("not a pdf")
        pdfs = scan_inbox(tmp_path)
        assert pdfs == []

    def test_nonexistent_folder(self, tmp_path: Path) -> None:
        pdfs = scan_inbox(tmp_path / "does_not_exist")
        assert pdfs == []


class TestExtractText:
    """Tests for extract_text."""

    def test_valid_pdf(self) -> None:
        text = extract_text(INBOUND_DIR / "claim_standard_01.pdf")
        assert text is not None
        assert "Maria Santos" in text

    def test_all_pdfs_return_text(self) -> None:
        for pdf in scan_inbox(INBOUND_DIR):
            text = extract_text(pdf)
            assert text is not None
            assert len(text) > 50

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = extract_text(tmp_path / "missing.pdf")
        assert result is None

    def test_non_pdf_file(self, tmp_path: Path) -> None:
        fake = tmp_path / "fake.pdf"
        fake.write_text("this is not a real pdf")
        result = extract_text(fake)
        assert result is None

    def test_empty_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        result = extract_text(empty)
        assert result is None
