import pytest

from transcribe_intelligence.topic_embeddings import TopicEmbedding, cosine_similarity, nearest


def test_cosine_and_nearest_are_deterministic():
    items = [
        TopicEmbedding("b", "r", "t2", (0.0, 1.0), "m"),
        TopicEmbedding("a", "r", "t1", (1.0, 0.0), "m"),
    ]
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert [item.embedding_id for item, _ in nearest((1.0, 0.0), items)] == ["a", "b"]


def test_rejects_zero_vector():
    with pytest.raises(ValueError):
        cosine_similarity((0.0,), (1.0,))
