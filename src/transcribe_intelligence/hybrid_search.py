"""Confidence-aware hybrid lexical and semantic retrieval."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .vector_fusion import cosine_similarity

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(text)}


def lexical_similarity(query: str, text: str) -> float:
    """Return symmetric token-overlap similarity in the range [0, 1]."""
    left, right = _tokens(query), _tokens(text)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True, slots=True)
class HybridSearchDocument:
    document_id: str
    recording_id: str
    text: str
    vector: tuple[float, ...]
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class HybridSearchHit:
    document_id: str
    recording_id: str
    score: float
    semantic_score: float
    lexical_score: float
    text: str


class HybridSearchIndex:
    """In-memory reference implementation for semantic + lexical retrieval."""

    def __init__(self, *, semantic_weight: float = 0.7, lexical_weight: float = 0.3):
        if semantic_weight < 0 or lexical_weight < 0 or semantic_weight + lexical_weight <= 0:
            raise ValueError("search weights must be non-negative and not both zero")
        total = semantic_weight + lexical_weight
        self.semantic_weight = semantic_weight / total
        self.lexical_weight = lexical_weight / total
        self._documents: dict[str, HybridSearchDocument] = {}

    def upsert(self, document: HybridSearchDocument) -> None:
        if not 0.0 <= document.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        self._documents[document.document_id] = document

    def search(
        self,
        query_text: str,
        query_vector: list[float] | tuple[float, ...],
        limit: int = 10,
    ) -> list[HybridSearchHit]:
        if limit < 1:
            raise ValueError("limit must be positive")
        scored: list[tuple[float, HybridSearchHit]] = []
        for doc in self._documents.values():
            semantic = cosine_similarity(list(query_vector), list(doc.vector))
            lexical = lexical_similarity(query_text, doc.text)
            score = (self.semantic_weight * semantic + self.lexical_weight * lexical) * doc.confidence
            hit = HybridSearchHit(doc.document_id, doc.recording_id, score, semantic, lexical, doc.text)
            scored.append((score, hit))
        scored.sort(key=lambda item: (-item[0], item[1].document_id))
        return [hit for _, hit in scored[:limit]]
