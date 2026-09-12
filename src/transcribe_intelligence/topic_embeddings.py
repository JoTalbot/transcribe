"""Provider-neutral topic embedding contracts and cosine search."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class TopicEmbedding:
    embedding_id: str
    recording_id: str
    topic_id: str
    vector: tuple[float, ...]
    model_version: str

    def __post_init__(self) -> None:
        if not self.embedding_id or not self.recording_id or not self.topic_id or not self.vector:
            raise ValueError("embedding identifiers and vector are required")
        if any(not math.isfinite(value) for value in self.vector):
            raise ValueError("embedding values must be finite")


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must be non-empty and have equal dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    nl = math.sqrt(sum(a * a for a in left))
    nr = math.sqrt(sum(b * b for b in right))
    if nl == 0 or nr == 0:
        raise ValueError("zero vector is not searchable")
    return dot / (nl * nr)


def nearest(query: tuple[float, ...], items: list[TopicEmbedding], limit: int = 10) -> list[tuple[TopicEmbedding, float]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    scored = [(item, cosine_similarity(query, item.vector)) for item in items]
    return sorted(scored, key=lambda pair: (-pair[1], pair[0].embedding_id))[:limit]
