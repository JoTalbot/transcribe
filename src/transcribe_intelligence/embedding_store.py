"""Atomic JSON store for speaker embeddings and cluster assignments."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .speaker_embeddings import SpeakerEmbedding, VoiceCluster


class EmbeddingStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, SpeakerEmbedding]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: SpeakerEmbedding(**{**value, "vector": tuple(value["vector"])}) for key, value in raw.get("embeddings", {}).items()}

    def upsert(self, embedding: SpeakerEmbedding) -> SpeakerEmbedding:
        items = self.load()
        items[embedding.embedding_id] = embedding
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"schema_version": "1.0", "embeddings": {k: asdict(v) for k, v in sorted(items.items())}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        return embedding


def cluster_payload(clusters: list[VoiceCluster]) -> dict[str, object]:
    return {"schema_version": "1.0", "clusters": [{"cluster_id": c.cluster_id, "member_ids": c.member_ids, "centroid": list(c.centroid)} for c in clusters]}
