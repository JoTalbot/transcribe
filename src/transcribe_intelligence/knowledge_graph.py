"""Small, serializable evidence graph used as the canonical intelligence layer."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .evidence import Evidence


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    kind: str
    label: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class GraphEdge:
    edge_id: str
    source_id: str
    predicate: str
    target_id: str
    confidence: float
    evidence_ids: tuple[str, ...] = ()


class EvidenceGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.evidence: dict[str, Evidence] = {}

    def add_node(self, node: GraphNode) -> None:
        existing = self.nodes.get(node.node_id)
        if existing is not None and existing != node:
            raise ValueError(f"conflicting node: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_evidence(self, evidence: Evidence) -> None:
        existing = self.evidence.get(evidence.evidence_id)
        if existing is not None and existing != evidence:
            raise ValueError(f"conflicting evidence: {evidence.evidence_id}")
        self.evidence[evidence.evidence_id] = evidence

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise KeyError("edge endpoints must exist")
        if any(eid not in self.evidence for eid in edge.evidence_ids):
            raise KeyError("edge references unknown evidence")
        existing = self.edges.get(edge.edge_id)
        if existing is not None and existing != edge:
            raise ValueError(f"conflicting edge: {edge.edge_id}")
        self.edges[edge.edge_id] = edge

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(self.nodes[key]) for key in sorted(self.nodes)],
            "edges": [asdict(self.edges[key]) for key in sorted(self.edges)],
            "evidence": [asdict(self.evidence[key]) for key in sorted(self.evidence)],
        }


def graph_from_edges(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge], evidence: Iterable[Evidence] = ()) -> EvidenceGraph:
    graph = EvidenceGraph()
    for item in nodes:
        graph.add_node(item)
    for item in evidence:
        graph.add_evidence(item)
    for item in edges:
        graph.add_edge(item)
    return graph
