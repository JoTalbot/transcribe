"""Dependency-free vector utilities for later retrieval and clustering stages."""
from __future__ import annotations

import math


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for two equal-length vectors."""
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have equal non-zero dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def mean_vector(vectors: list[list[float]]) -> list[float]:
    """Compute a centroid without mutating input vectors."""
    if not vectors or not vectors[0]:
        raise ValueError("at least one non-empty vector is required")
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("all vectors must have equal dimensions")
    count = float(len(vectors))
    return [sum(vector[index] for vector in vectors) / count for index in range(dimensions)]
