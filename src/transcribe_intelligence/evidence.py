"""Generic provenance records for auditable pipeline outputs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Evidence:
    """Point an extracted result back to a source span and method."""

    evidence_id: str
    recording_id: str
    start: float
    end: float
    confidence: float
    segment_id: str | None = None
    text: str | None = None
    method: str = "unknown"
    model_version: str | None = None

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid evidence time range")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
