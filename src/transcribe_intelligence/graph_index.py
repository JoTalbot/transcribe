"""Build searchable documents from evidence-backed graph content."""
from __future__ import annotations

from dataclasses import dataclass

from .knowledge_graph import EvidenceGraph


@dataclass(frozen=True, slots=True)
class GraphSearchDocument:
    document_id: str
    recording_id: str
    text: str
    evidence_ids: tuple[str, ...]


def documents_from_graph(graph: EvidenceGraph) -> list[GraphSearchDocument]:
    """Create deterministic lexical documents from graph nodes and their evidence."""
    documents: list[GraphSearchDocument] = []
    for edge_id in sorted(graph.edges):
        edge = graph.edges[edge_id]
        evidence_ids = tuple(sorted(edge.evidence_ids))
        evidence_text = " ".join(
            graph.evidence[eid].text for eid in evidence_ids if graph.evidence[eid].text
        )
        source = graph.nodes[edge.source_id]
        target = graph.nodes[edge.target_id]
        text = " ".join(
            part for part in (source.label, edge.predicate, target.label, evidence_text) if part
        )
        recording_ids = sorted({graph.evidence[eid].recording_id for eid in evidence_ids})
        recording_id = recording_ids[0] if recording_ids else ""
        documents.append(GraphSearchDocument(edge_id, recording_id, text, evidence_ids))
    return documents
