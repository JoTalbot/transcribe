"""Deterministic orchestration contracts for post-transcription intelligence stages."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

from .pipeline_contract import Stage


@dataclass(frozen=True, slots=True)
class SegmentInput:
    segment_id: str
    recording_id: str
    start: float
    end: float
    text: str
    speaker: str | None = None


T = TypeVar("T")


def run_stage(items: Iterable[SegmentInput], stage: Stage, extractor: Callable[[SegmentInput], Iterable[T]]) -> list[T]:
    """Run a pure extractor over segments in stable order.

    The extractor owns model-specific inference; this layer guarantees deterministic
    ordering and makes the post-ASR stages independently testable and resumable.
    """
    if stage not in {
        Stage.TEXT_ANALYSIS,
        Stage.TOPICS,
        Stage.LINKING,
        Stage.GRAPH,
    }:
        raise ValueError(f"stage {stage.value!r} is not a post-transcription intelligence stage")
    output: list[T] = []
    for item in sorted(items, key=lambda value: (value.recording_id, value.start, value.end, value.segment_id)):
        output.extend(extractor(item))
    return output


def group_by_recording(items: Iterable[SegmentInput]) -> dict[str, list[SegmentInput]]:
    grouped: dict[str, list[SegmentInput]] = {}
    for item in items:
        grouped.setdefault(item.recording_id, []).append(item)
    for values in grouped.values():
        values.sort(key=lambda value: (value.start, value.end, value.segment_id))
    return grouped
