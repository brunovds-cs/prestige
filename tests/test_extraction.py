"""Tests for the LLM extraction module."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.extraction import LLMClient, _parse_response, extract_claim_data

VALID_JSON = json.dumps(
    {
        "policyholder_name": "Maria Santos",
        "policy_number": "POL-2024-001",
        "claim_amount": 15000.00,
        "incident_date": "2024-11-15",
    }
)

MISSING_FIELDS_JSON = json.dumps(
    {
        "policyholder_name": "Maria Santos",
        "policy_number": "POL-2024-001",
    }
)

INVALID_AMOUNT_JSON = json.dumps(
    {
        "policyholder_name": "Maria Santos",
        "policy_number": "POL-2024-001",
        "claim_amount": -500,
        "incident_date": "2024-11-15",
    }
)

BAD_DATE_JSON = json.dumps(
    {
        "policyholder_name": "Maria Santos",
        "policy_number": "POL-2024-001",
        "claim_amount": 1500,
        "incident_date": "November 15, 2024",
    }
)


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Create a mock LLMClient that returns the given responses in order."""
    client = MagicMock(spec=LLMClient)
    client.chat.side_effect = responses
    return client


class TestParseResponse:
    """Tests for the _parse_response helper."""

    def test_valid_json(self) -> None:
        result = _parse_response(VALID_JSON, "claim_01.pdf")
        assert result is not None
        assert result.policyholder_name == "Maria Santos"
        assert result.policy_number == "POL-2024-001"
        assert result.claim_amount == 15000.00
        assert result.incident_date == "2024-11-15"
        assert result.raw_source == "claim_01.pdf"
        assert result.confidence == 0.85

    def test_malformed_json(self) -> None:
        result = _parse_response("not json at all {{{", "claim.pdf")
        assert result is None

    def test_missing_fields(self) -> None:
        result = _parse_response(MISSING_FIELDS_JSON, "claim.pdf")
        assert result is None

    def test_invalid_claim_amount(self) -> None:
        result = _parse_response(INVALID_AMOUNT_JSON, "claim.pdf")
        assert result is None

    def test_bad_date_format(self) -> None:
        result = _parse_response(BAD_DATE_JSON, "claim.pdf")
        assert result is None


class TestExtractClaimData:
    """Tests for the main extract_claim_data function."""

    def test_success_first_attempt(self) -> None:
        client = _make_mock_client([VALID_JSON])
        result = extract_claim_data("some raw text", "claim.pdf", client=client)

        assert result is not None
        assert result.policyholder_name == "Maria Santos"
        assert client.chat.call_count == 1

    def test_success_on_retry(self) -> None:
        client = _make_mock_client(["garbage response", VALID_JSON])
        result = extract_claim_data("some raw text", "claim.pdf", client=client)

        assert result is not None
        assert result.policyholder_name == "Maria Santos"
        assert client.chat.call_count == 2

    def test_failure_after_retry(self) -> None:
        client = _make_mock_client(["garbage", "still garbage"])
        result = extract_claim_data("some raw text", "claim.pdf", client=client)

        assert result is None
        assert client.chat.call_count == 2

    def test_api_error_first_attempt(self) -> None:
        client = MagicMock(spec=LLMClient)
        client.chat.side_effect = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        result = extract_claim_data("some raw text", "claim.pdf", client=client)

        assert result is None
        assert client.chat.call_count == 1

    def test_api_error_on_retry(self) -> None:
        """First attempt returns bad JSON, retry hits API error."""
        client = MagicMock(spec=LLMClient)
        client.chat.side_effect = [
            "not json",
            httpx.HTTPStatusError(
                "Timeout",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            ),
        ]
        result = extract_claim_data("some raw text", "claim.pdf", client=client)

        assert result is None
        assert client.chat.call_count == 2

    def test_malformed_json_then_missing_fields(self) -> None:
        """Both attempts return parseable but invalid data."""
        client = _make_mock_client(["not json", MISSING_FIELDS_JSON])
        result = extract_claim_data("some raw text", "claim.pdf", client=client)

        assert result is None
        assert client.chat.call_count == 2

    def test_default_client_created(self) -> None:
        """When no client is passed, one is constructed automatically."""
        mock_client = _make_mock_client([VALID_JSON])

        with patch("src.extraction.LLMClient", return_value=mock_client) as mock_cls:
            result = extract_claim_data("raw text", "claim.pdf")

            mock_cls.assert_called_once()
            assert result is not None
