import pytest

from transcribe_intelligence.hybrid_search import (
    HybridSearchDocument,
    HybridSearchIndex,
    lexical_similarity,
)


def test_lexical_similarity_is_case_insensitive():
    assert lexical_similarity("Hello world", "hello WORLD") == 1.0


def test_hybrid_search_combines_scores_and_confidence():
    index = HybridSearchIndex(semantic_weight=0.5, lexical_weight=0.5)
    index.upsert(HybridSearchDocument("a", "r1", "contract payment", (1, 0), 1.0))
    index.upsert(HybridSearchDocument("b", "r2", "contract", (1, 0), 0.5))
    hits = index.search("payment", (1, 0))
    assert hits[0].document_id == "a"
    assert hits[0].lexical_score > hits[1].lexical_score


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        HybridSearchIndex(semantic_weight=0, lexical_weight=0)
