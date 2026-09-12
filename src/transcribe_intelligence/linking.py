"""Cross-recording conversation links with explicit confidence and evidence."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from .speaker_embeddings import SpeakerEmbedding, cosine


@dataclass(frozen=True, slots=True)
class ConversationLink:
    link_id: str
    left_recording_id: str
    right_recording_id: str
    similarity: float
    method: str
    confidence: float


def link_speakers(embeddings: Iterable[SpeakerEmbedding], threshold: float = 0.78) -> list[ConversationLink]:
    """Create candidate cross-recording links; never link speakers within one recording."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    items = sorted(embeddings, key=lambda item: item.embedding_id)
    links: list[ConversationLink] = []
    for left, right in combinations(items, 2):
        if left.recording_id == right.recording_id:
            continue
        score = cosine(left.vector, right.vector)
        if score >= threshold:
            confidence = min(1.0, max(0.0, (score - threshold) / max(1e-9, 1.0 - threshold)))
            links.append(ConversationLink(
                f"{left.embedding_id}~{right.embedding_id}",
                left.recording_id, right.recording_id, score,
                "voice_embedding_candidate", confidence,
            ))
    return links
