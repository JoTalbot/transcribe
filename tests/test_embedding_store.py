from pathlib import Path

from transcribe_intelligence.embedding_store import EmbeddingStore, cluster_payload
from transcribe_intelligence.speaker_embeddings import SpeakerEmbedding, VoiceCluster


def test_embedding_store_round_trip(tmp_path: Path):
    store = EmbeddingStore(tmp_path / "embeddings.json")
    item = SpeakerEmbedding("r1:SPEAKER_00", "r1", "SPEAKER_00", (0.1, 0.2), "ecapa-v1")
    store.upsert(item)
    assert store.load()[item.embedding_id].vector == (0.1, 0.2)


def test_cluster_payload():
    payload = cluster_payload([VoiceCluster("VOICE_CLUSTER_00000", ["a"], (1.0, 0.0))])
    assert payload["clusters"][0]["cluster_id"] == "VOICE_CLUSTER_00000"
