"""Backend-neutral semantic search contract."""
from __future__ import annotations

from dataclasses import dataclass
from .vector_fusion import cosine_similarity


@dataclass(frozen=True, slots=True)
class SearchDocument:
    document_id: str
    recording_id: str
    text: str
    vector: tuple[float, ...]
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class SearchHit:
    document_id: str
    recording_id: str
    score: float
    text: str


class InMemorySemanticIndex:
    """Deterministic reference index; production storage can use pgvector."""
    def __init__(self) -> None:
        self._documents: dict[str, SearchDocument] = {}

    def upsert(self, document: SearchDocument) -> None:
        self._documents[document.document_id] = document

    def search(self, query: list[float] | tuple[float, ...], limit: int = 10) -> list[SearchHit]:
        if limit < 1:
            raise ValueError("limit must be positive")
        scored = [(cosine_similarity(list(query), list(doc.vector)) * doc.confidence, doc) for doc in self._documents.values()]
        scored.sort(key=lambda item: (-item[0], item[1].document_id))
        return [SearchHit(doc.document_id, doc.recording_id, score, doc.text) for score, doc in scored[:limit]]
