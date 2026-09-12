from transcribe_intelligence.evidence import Evidence
from transcribe_intelligence.graph_index import documents_from_graph
from transcribe_intelligence.knowledge_graph import EvidenceGraph, GraphEdge, GraphNode


def test_documents_from_graph_are_deterministic_and_keep_evidence():
    graph = EvidenceGraph()
    graph.add_node(GraphNode("person", "person", "Alice"))
    graph.add_node(GraphNode("event", "event", "Meeting"))
    graph.add_evidence(Evidence("ev", "rec", 3, 4, 0.9, "seg", "Discuss meeting", "test", "v1"))
    graph.add_edge(GraphEdge("edge", "person", "attends", "event", 0.8, ("ev",)))

    docs = documents_from_graph(graph)
    assert docs[0].document_id == "edge"
    assert docs[0].recording_id == "rec"
    assert "Alice" in docs[0].text
    assert "Discuss meeting" in docs[0].text
    assert docs[0].evidence_ids == ("ev",)
