from pathlib import Path
import json

from scripts.colab_speaker_embeddings import EmbeddingConfig, extract_embeddings


def test_extract_embeddings_normalizes_and_averages(tmp_path: Path):
    diarized = tmp_path / "diarized.json"
    diarized.write_text(json.dumps({"segments": [
        {"start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "one"},
        {"start": 2, "end": 3, "speaker": "SPEAKER_00", "text": "two"},
        {"start": 4, "end": 4.2, "speaker": "SPEAKER_01", "text": "short"},
    ]}), encoding="utf-8")

    def embedder(audio, start, end):
        assert audio.name == "call.wav"
        return (3.0, 4.0) if start == 0 else (0.0, 5.0)

    result = extract_embeddings(
        tmp_path / "call.wav", diarized, embedder, "rec1", "ecapa:test", EmbeddingConfig(min_segment_seconds=0.5)
    )
    assert [item.speaker_label for item in result] == ["SPEAKER_00"]
    vector = result[0].vector
    norm = sum(x * x for x in vector) ** 0.5
    assert abs(norm - 1.0) < 1e-9
    assert vector[0] > 0
    assert vector[1] > 0


def test_extract_embeddings_rejects_dimension_mismatch(tmp_path: Path):
    diarized = tmp_path / "diarized.json"
    diarized.write_text(json.dumps({"segments": [
        {"start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "one"},
        {"start": 2, "end": 3, "speaker": "SPEAKER_00", "text": "two"},
    ]}), encoding="utf-8")

    def embedder(audio, start, end):
        return (1.0, 0.0) if start == 0 else (1.0, 0.0, 0.0)

    import pytest
    with pytest.raises(ValueError, match="dimension mismatch"):
        extract_embeddings(tmp_path / "call.wav", diarized, embedder, "rec1", "ecapa:test")
