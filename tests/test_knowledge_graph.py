from transcribe_intelligence.evidence import Evidence
from transcribe_intelligence.knowledge_graph import EvidenceGraph, GraphEdge, GraphNode


def test_graph_requires_evidence_and_endpoints():
    graph = EvidenceGraph()
    graph.add_node(GraphNode("r1", "recording"))
    graph.add_node(GraphNode("e1", "entity", "Alice", .8))
    ev = Evidence("ev1", "r1", 1, 2, .9, "s1", "Alice", "test", "v1")
    graph.add_evidence(ev)
    graph.add_edge(GraphEdge("x1", "r1", "mentions", "e1", .8, ("ev1",)))
    assert graph.to_dict()["edges"][0]["edge_id"] == "x1"


def test_graph_rejects_unknown_evidence():
    graph = EvidenceGraph()
    graph.add_node(GraphNode("a", "recording"))
    graph.add_node(GraphNode("b", "entity"))
    try:
        graph.add_edge(GraphEdge("x", "a", "mentions", "b", .5, ("missing",)))
    except KeyError:
        pass
    else:
        raise AssertionError("unknown evidence must be rejected")
