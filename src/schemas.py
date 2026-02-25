"""Pydantic models for the insurance claim processing pipeline."""

from typing import Literal

from pydantic import BaseModel, Field


class ClaimData(BaseModel):
    """Structured data extracted from an insurance claim PDF."""

    policyholder_name: str
    policy_number: str
    claim_amount: float = Field(gt=0)
    incident_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    raw_source: str
    confidence: float = Field(ge=0, le=1)


class ProcessingResult(BaseModel):
    """Outcome of processing a single claim through the pipeline."""

    status: Literal["success", "extraction_failed", "automation_failed"]
    timestamp: str
    source_file: str
    screenshot_path: str | None = None
    error_message: str | None = None
