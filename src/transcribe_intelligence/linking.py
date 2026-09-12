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
    """Create one best candidate per unordered recording pair."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    items = sorted(embeddings, key=lambda item: item.embedding_id)
    best: dict[tuple[str, str], ConversationLink] = {}
    for left, right in combinations(items, 2):
        if left.recording_id == right.recording_id:
            continue
        score = cosine(left.vector, right.vector)
        if score < threshold:
            continue
        recording_pair = tuple(sorted((left.recording_id, right.recording_id)))
        confidence = min(1.0, max(0.0, (score - threshold) / max(1e-9, 1.0 - threshold)))
        candidate = ConversationLink(
            f"{left.embedding_id}~{right.embedding_id}",
            recording_pair[0], recording_pair[1], score,
            "voice_embedding_candidate", confidence,
        )
        existing = best.get(recording_pair)
        if existing is None or (candidate.similarity, candidate.link_id) > (existing.similarity, existing.link_id):
            best[recording_pair] = candidate
    return [best[key] for key in sorted(best)]
