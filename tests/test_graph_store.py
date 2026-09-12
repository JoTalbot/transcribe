from transcribe_intelligence.evidence import Evidence
from transcribe_intelligence.graph_store import GraphSnapshotStore
from transcribe_intelligence.knowledge_graph import EvidenceGraph, GraphEdge, GraphNode


def test_graph_snapshot_round_trip(tmp_path):
    graph = EvidenceGraph()
    graph.add_node(GraphNode("a", "person", "Alice"))
    graph.add_node(GraphNode("b", "event", "Meeting"))
    evidence = Evidence("ev1", "rec1", 1, 2, 0.9, "seg1", "meeting", "test", "v1")
    graph.add_evidence(evidence)
    graph.add_edge(GraphEdge("e1", "a", "attends", "b", 0.8, ("ev1",)))

    path = tmp_path / "graph.json"
    store = GraphSnapshotStore(path)
    store.save(graph)
    loaded = store.load()

    assert loaded.to_dict() == graph.to_dict()
