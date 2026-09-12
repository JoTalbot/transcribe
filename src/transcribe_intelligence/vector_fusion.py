"""Generic vector operations used by semantic retrieval components."""
from __future__ import annotations

import math


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for equal-length non-zero vectors."""
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have equal non-zero length")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("zero vectors are not supported")
    return dot / (left_norm * right_norm)


def centroid(vectors: list[list[float]]) -> list[float]:
    """Return the arithmetic mean vector."""
    if not vectors or not vectors[0]:
        raise ValueError("vectors must be non-empty")
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("vectors must have equal dimensions")
    count = len(vectors)
    return [sum(vector[i] for vector in vectors) / count for i in range(dimensions)]
