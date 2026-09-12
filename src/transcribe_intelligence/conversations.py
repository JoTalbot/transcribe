"""Evidence-preserving conversation and thread linking primitives."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from .entities import TopicMention
from .vector_fusion import cosine_similarity


@dataclass(frozen=True, slots=True)
class ConversationThread:
    thread_id: str
    recording_ids: tuple[str, ...]
    topic_ids: tuple[str, ...]
    confidence: float
    method: str


def link_topic_mentions(mentions: list[TopicMention], embeddings: dict[str, tuple[float, ...]], threshold: float = 0.82) -> list[ConversationThread]:
    """Link topic mentions across recordings by embedding similarity."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    result: list[ConversationThread] = []
    ordered = sorted(mentions, key=lambda x: (x.recording_id, x.topic_id))
    for left, right in combinations(ordered, 2):
        if left.recording_id == right.recording_id:
            continue
        lv = embeddings.get(left.topic_id)
        rv = embeddings.get(right.topic_id)
        if lv is None or rv is None:
            continue
        score = cosine_similarity(list(lv), list(rv))
        if score >= threshold:
            result.append(ConversationThread(
                f"{left.topic_id}~{right.topic_id}",
                tuple(sorted({left.recording_id, right.recording_id})),
                tuple(sorted({left.topic_id, right.topic_id})),
                score,
                "topic_embedding_similarity",
            ))
    return result
