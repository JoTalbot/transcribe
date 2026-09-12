from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class SpeakerEmbedding:
    embedding_id: str
    recording_id: str
    speaker_label: str
    vector: tuple[float, ...]
    model_version: str
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True, slots=True)
class VoiceCluster:
    cluster_id: str
    member_ids: list[str]
    centroid: tuple[float, ...]


def cosine(left: tuple[float, ...] | list[float], right: tuple[float, ...] | list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have equal non-zero length")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("zero vectors are not supported")
    return dot / (left_norm * right_norm)


def _centroid(vectors: list[tuple[float, ...]]) -> tuple[float, ...]:
    dimensions = len(vectors[0])
    values = tuple(sum(vector[i] for vector in vectors) / len(vectors) for i in range(dimensions))
    norm = math.sqrt(sum(value * value for value in values))
    return values if norm == 0 else tuple(value / norm for value in values)


def cluster_embeddings(embeddings: list[SpeakerEmbedding], threshold: float = 0.78) -> list[VoiceCluster]:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    ordered = sorted(embeddings, key=lambda item: item.embedding_id)
    clusters: list[list[SpeakerEmbedding]] = []
    for embedding in ordered:
        candidates = [
            cluster for cluster in clusters
            if all(cosine(embedding.vector, member.vector) >= threshold for member in cluster)
        ]
        if not candidates:
            clusters.append([embedding])
            continue
        target = min(candidates, key=lambda cluster: min(member.embedding_id for member in cluster))
        target.append(embedding)
    return [
        VoiceCluster(
            f"VOICE_CLUSTER_{index:05d}",
            [member.embedding_id for member in sorted(cluster, key=lambda item: item.embedding_id)],
            _centroid([member.vector for member in cluster]),
        )
        for index, cluster in enumerate(clusters)
    ]
