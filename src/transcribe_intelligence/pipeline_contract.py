"""Stage contracts for the resumable conversation-intelligence pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Stage(StrEnum):
    INGEST = "ingest"
    NORMALIZE = "normalize"
    ASR = "asr"
    DIARIZATION = "diarization"
    EMBEDDINGS = "embeddings"
    TEXT_ANALYSIS = "text_analysis"
    TOPICS = "topics"
    LINKING = "linking"
    GRAPH = "graph"


@dataclass(frozen=True)
class StageResult:
    stage: Stage
    status: str
    artifact_id: str | None = None
    model_version: str | None = None

    @property
    def completed(self) -> bool:
        return self.status == "completed" and bool(self.artifact_id)
