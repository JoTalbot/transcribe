from transcribe_intelligence.search import InMemorySemanticIndex, SearchDocument


def test_semantic_search_is_deterministic():
    index = InMemorySemanticIndex()
    index.upsert(SearchDocument("b", "r2", "second", (0, 1)))
    index.upsert(SearchDocument("a", "r1", "first", (1, 0)))
    hits = index.search((1, 0), 2)
    assert [hit.document_id for hit in hits] == ["a", "b"]


def test_search_applies_document_confidence():
    index = InMemorySemanticIndex()
    index.upsert(SearchDocument("high", "r1", "high", (1, 0), 1.0))
    index.upsert(SearchDocument("low", "r2", "low", (1, 0), .2))
    assert index.search((1, 0), 2)[0].document_id == "high"
