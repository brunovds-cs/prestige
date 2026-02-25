"""Tests for Pydantic schemas: ClaimData and ProcessingResult."""

import pytest
from pydantic import ValidationError

from src.schemas import ClaimData, ProcessingResult


# --- ClaimData ---


def _valid_claim(**overrides: object) -> dict:
    defaults = {
        "policyholder_name": "Jane Doe",
        "policy_number": "POL-2024-001",
        "claim_amount": 15000.50,
        "incident_date": "2024-11-03",
        "raw_source": "claim_standard_01.pdf",
        "confidence": 0.95,
    }
    defaults.update(overrides)
    return defaults


class TestClaimData:
    def test_valid_claim(self) -> None:
        claim = ClaimData(**_valid_claim())
        assert claim.policyholder_name == "Jane Doe"
        assert claim.claim_amount == 15000.50

    def test_missing_required_field(self) -> None:
        data = _valid_claim()
        del data["policy_number"]
        with pytest.raises(ValidationError):
            ClaimData(**data)

    def test_negative_claim_amount(self) -> None:
        with pytest.raises(ValidationError):
            ClaimData(**_valid_claim(claim_amount=-100))

    def test_zero_claim_amount(self) -> None:
        with pytest.raises(ValidationError):
            ClaimData(**_valid_claim(claim_amount=0))

    def test_invalid_date_format(self) -> None:
        with pytest.raises(ValidationError):
            ClaimData(**_valid_claim(incident_date="11/03/2024"))

    def test_confidence_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            ClaimData(**_valid_claim(confidence=-0.1))

    def test_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            ClaimData(**_valid_claim(confidence=1.5))

    def test_confidence_boundary_values(self) -> None:
        ClaimData(**_valid_claim(confidence=0))
        ClaimData(**_valid_claim(confidence=1))


# --- ProcessingResult ---


def _valid_result(**overrides: object) -> dict:
    defaults = {
        "status": "success",
        "timestamp": "2024-11-03T10:30:00",
        "source_file": "claim_standard_01.pdf",
    }
    defaults.update(overrides)
    return defaults


class TestProcessingResult:
    def test_success_result(self) -> None:
        result = ProcessingResult(**_valid_result())
        assert result.status == "success"
        assert result.screenshot_path is None
        assert result.error_message is None

    def test_extraction_failed(self) -> None:
        result = ProcessingResult(
            **_valid_result(
                status="extraction_failed",
                error_message="LLM returned invalid JSON",
            )
        )
        assert result.status == "extraction_failed"
        assert result.error_message == "LLM returned invalid JSON"

    def test_automation_failed_with_screenshot(self) -> None:
        result = ProcessingResult(
            **_valid_result(
                status="automation_failed",
                screenshot_path="screenshots/20241103_POL001.png",
                error_message="Element not found",
            )
        )
        assert result.screenshot_path is not None

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            ProcessingResult(**_valid_result(status="unknown"))

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ProcessingResult(status="success")
