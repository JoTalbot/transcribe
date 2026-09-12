"""Stage-aware artifact contracts for ASR and diarization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid transcript segment timing")
        if not self.text.strip():
            raise ValueError("transcript text must not be empty")


@dataclass(frozen=True, slots=True)
class DiarizedSegment:
    start: float
    end: float
    speaker: str
    text: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid diarized segment timing")
        if not self.speaker.strip() or not self.text.strip():
            raise ValueError("speaker and text must not be empty")


def transcript_payload(recording_id: str, source: str, model: str, segments: list[TranscriptSegment]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "recording_id": recording_id,
        "source": source,
        "model": model,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
    }


def diarized_payload(recording_id: str, source: str, model: str, segments: list[DiarizedSegment]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "recording_id": recording_id,
        "source": source,
        "model": model,
        "segments": [{"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text} for s in segments],
    }
