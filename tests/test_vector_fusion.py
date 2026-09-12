import pytest

from transcribe_intelligence.vector_fusion import centroid, cosine_similarity


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_centroid():
    assert centroid([[1.0, 3.0], [3.0, 5.0]]) == [2.0, 4.0]
