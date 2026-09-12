"""Atomic JSON persistence for evidence graph snapshots."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import Evidence
from .knowledge_graph import EvidenceGraph, GraphEdge, GraphNode

SCHEMA_VERSION = "1.0"


class GraphSnapshotStore:
    """Persist complete graph snapshots with deterministic, atomic writes."""

    def __init__(self, path: Path):
        self.path = path

    def save(self, graph: EvidenceGraph) -> None:
        payload = {"schema_version": SCHEMA_VERSION, **graph.to_dict()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def load(self) -> EvidenceGraph:
        payload: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported graph snapshot schema")
        graph = EvidenceGraph()
        for raw in payload.get("nodes", []):
            graph.add_node(GraphNode(**raw))
        for raw in payload.get("evidence", []):
            graph.add_evidence(Evidence(**raw))
        for raw in payload.get("edges", []):
            raw["evidence_ids"] = tuple(raw.get("evidence_ids", ()))
            graph.add_edge(GraphEdge(**raw))
        return graph
