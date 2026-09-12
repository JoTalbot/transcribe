"""Optional Colab GPU extraction of speaker embeddings from diarized audio."""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from transcribe_intelligence.speaker_embeddings import SpeakerEmbedding


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    model_name: str = "speechbrain/spkrec-ecapa-voxceleb"


def extract_embeddings(audio: Path, diarized_json: Path, embedder, recording_id: str, model_version: str) -> list[SpeakerEmbedding]:
    payload = json.loads(diarized_json.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, object]]] = {}
    for segment in payload.get("segments", []):
        if segment.get("speaker") and float(segment["end"]) > float(segment["start"]):
            grouped.setdefault(str(segment["speaker"]), []).append(segment)
    results: list[SpeakerEmbedding] = []
    for speaker, segments in sorted(grouped.items()):
        vectors = []
        for segment in segments:
            vector = embedder(audio, float(segment["start"]), float(segment["end"]))
            vectors.append(tuple(float(x) for x in vector))
        if not vectors:
            continue
        dims = len(vectors[0])
        centroid = tuple(sum(v[i] for v in vectors) / len(vectors) for i in range(dims))
        results.append(SpeakerEmbedding(f"{recording_id}:{speaker}", recording_id, speaker, centroid, model_version, float(segments[0]["start"]), float(segments[-1]["end"])))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--diarized-json", type=Path, required=True)
    parser.add_argument("--recording-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=EmbeddingConfig.model_name)
    args = parser.parse_args()
    raise SystemExit("GPU embedder injection is required; use extract_embeddings() from the Colab worker")


if __name__ == "__main__":
    main()
