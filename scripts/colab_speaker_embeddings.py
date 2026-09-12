"""Extract normalized ECAPA speaker embeddings from diarized audio in Colab."""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.embedding_store import EmbeddingStore
from transcribe_intelligence.speaker_embeddings import SpeakerEmbedding


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    model_name: str = "speechbrain/spkrec-ecapa-voxceleb"
    sample_rate: int = 16000
    min_segment_seconds: float = 0.8


def _normalize(vector: Any) -> tuple[float, ...]:
    values = [float(x) for x in vector]
    norm = sum(x * x for x in values) ** 0.5
    if not values or norm <= 0:
        raise ValueError("speaker embedder returned an empty or zero vector")
    return tuple(x / norm for x in values)


def extract_embeddings(
    audio: Path,
    diarized_json: Path,
    embedder: Callable[[Path, float, float], Any],
    recording_id: str,
    model_version: str,
    config: EmbeddingConfig = EmbeddingConfig(),
) -> list[SpeakerEmbedding]:
    """Average normalized segment embeddings into one vector per local speaker."""
    payload = json.loads(diarized_json.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, object]]] = {}
    for segment in payload.get("segments", []):
        if not segment.get("speaker"):
            continue
        start, end = float(segment["start"]), float(segment["end"])
        if end - start >= config.min_segment_seconds:
            grouped.setdefault(str(segment["speaker"]), []).append(segment)

    results: list[SpeakerEmbedding] = []
    for speaker, segments in sorted(grouped.items()):
        vectors = [_normalize(embedder(audio, float(s["start"]), float(s["end"]))) for s in segments]
        dims = len(vectors[0])
        if any(len(v) != dims for v in vectors):
            raise ValueError(f"embedding dimension mismatch for {recording_id}:{speaker}")
        centroid = _normalize(tuple(sum(v[i] for v in vectors) / len(vectors) for i in range(dims)))
        results.append(SpeakerEmbedding(
            f"{recording_id}:{speaker}", recording_id, speaker, centroid, model_version,
            float(segments[0]["start"]), float(segments[-1]["end"]),
        ))
    return results


def build_speechbrain_embedder(model: Any, target_sample_rate: int = 16000):
    """Create a segment embedder backed by SpeechBrain ECAPA on CUDA."""
    import torch
    import torchaudio

    def embed(audio: Path, start: float, end: float) -> tuple[float, ...]:
        waveform, sample_rate = torchaudio.load(str(audio))
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sample_rate != target_sample_rate:
            waveform = torchaudio.functional.resample(waveform, sample_rate, target_sample_rate)
        left = max(0, int(round(start * target_sample_rate)))
        right = min(waveform.shape[-1], int(round(end * target_sample_rate)))
        if right <= left:
            raise ValueError(f"empty audio segment {start}-{end}")
        chunk = waveform[:, left:right]
        with torch.inference_mode():
            embedding = model.encode_batch(chunk)
        return embedding.squeeze().detach().float().cpu().tolist()

    return embed


def extract_and_persist(
    audio: Path,
    diarized_json: Path,
    output_dir: Path,
    recording_id: str,
    model: Any,
    config: EmbeddingConfig = EmbeddingConfig(),
) -> list[SpeakerEmbedding]:
    embedder = build_speechbrain_embedder(model, config.sample_rate)
    model_version = config.model_name
    embeddings = extract_embeddings(audio, diarized_json, embedder, recording_id, model_version, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    store = EmbeddingStore(output_dir / "speaker_embeddings.json")
    for embedding in embeddings:
        store.upsert(embedding)
    manifest = build_manifest(
        output_dir / "speaker_embeddings.json",
        artifact_id=f"{recording_id}:embeddings:json",
        recording_id=recording_id,
        stage="embeddings",
        kind="speaker_embeddings",
        producer="colab-speechbrain-ecapa",
        model_version=model_version,
    )
    write_manifest(manifest, output_dir / "speaker_embeddings.manifest.json")
    return embeddings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--diarized-json", type=Path, required=True)
    parser.add_argument("--recording-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=EmbeddingConfig.model_name)
    parser.parse_args()
    raise SystemExit("CLI model loading is intentionally owned by colab_exchange_worker.py")


if __name__ == "__main__":
    main()
