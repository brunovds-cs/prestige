"""LLM-based extraction of structured claim data from raw PDF text."""

import json
import logging
import os

import httpx

from src.schemas import ClaimData

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "minimax/minimax-m2.5"

SYSTEM_PROMPT = """\
You are a data extraction assistant for insurance claims.
Given raw text from an insurance claim PDF, extract the following fields
and return ONLY a valid JSON object — no markdown, no explanation, no extra text.

Required JSON schema:
{
  "policyholder_name": "<string>",
  "policy_number": "<string>",
  "claim_amount": <number, positive>,
  "incident_date": "<YYYY-MM-DD>"
}

Rules:
- claim_amount must be a positive number (no currency symbols).
- incident_date must be in ISO 8601 format (YYYY-MM-DD).
- If a field is ambiguous, use your best judgment and include it.
- Return ONLY the JSON object. Nothing else."""

RETRY_SYSTEM_PROMPT = """\
Your previous response was not valid JSON or was missing required fields.
Return ONLY a raw JSON object with these exact keys:
policyholder_name (string), policy_number (string),
claim_amount (positive number), incident_date (YYYY-MM-DD string).
No markdown fences, no commentary. Just the JSON object."""


class LLMClient:
    """Thin wrapper around the OpenRouter chat completions API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._http = httpx.Client(timeout=30)

    def chat(self, system: str, user_message: str) -> str:
        """Send a chat completion request and return the assistant message text."""
        response = self._http.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 512,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def close(self) -> None:
        self._http.close()


def _parse_response(response_text: str, source_file: str) -> ClaimData | None:
    """Parse LLM response text into a ClaimData model. Returns None on failure."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON: %s", exc)
        return None

    try:
        return ClaimData(
            policyholder_name=data["policyholder_name"],
            policy_number=data["policy_number"],
            claim_amount=data["claim_amount"],
            incident_date=data["incident_date"],
            raw_source=source_file,
            confidence=0.85,
        )
    except (KeyError, ValueError) as exc:
        logger.warning("LLM response missing or invalid fields: %s", exc)
        return None


def extract_claim_data(
    raw_text: str,
    source_file: str,
    client: LLMClient | None = None,
) -> ClaimData | None:
    """Extract structured claim data from raw PDF text using an LLM.

    Makes one attempt with the standard prompt. If parsing fails, retries once
    with a stricter prompt. Returns None on final failure.
    """
    own_client = client is None
    if own_client:
        client = LLMClient()

    try:
        return _extract_with_retry(client, raw_text, source_file)
    finally:
        if own_client:
            client.close()


def _extract_with_retry(
    client: LLMClient,
    raw_text: str,
    source_file: str,
) -> ClaimData | None:
    """Attempt extraction, retry once with stricter prompt on failure."""
    # First attempt
    try:
        response = client.chat(SYSTEM_PROMPT, raw_text)
        logger.debug("LLM response (attempt 1): %s", response)
    except httpx.HTTPError as exc:
        logger.error("LLM API error for %s: %s", source_file, exc)
        return None

    claim = _parse_response(response, source_file)
    if claim is not None:
        logger.info("Extracted claim data from %s on first attempt", source_file)
        return claim

    # Retry with stricter prompt
    logger.info("Retrying extraction for %s with stricter prompt", source_file)
    try:
        response = client.chat(RETRY_SYSTEM_PROMPT, raw_text)
        logger.debug("LLM response (attempt 2): %s", response)
    except httpx.HTTPError as exc:
        logger.error("LLM API error on retry for %s: %s", source_file, exc)
        return None

    claim = _parse_response(response, source_file)
    if claim is not None:
        logger.info("Extracted claim data from %s on retry", source_file)
        return claim

    logger.error("Failed to extract claim data from %s after retry", source_file)
    return None
