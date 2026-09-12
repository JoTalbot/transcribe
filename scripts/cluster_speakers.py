"""Cluster recording-local speaker embeddings into conservative VOICE_CLUSTER groups."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.embedding_store import EmbeddingStore, cluster_payload
from transcribe_intelligence.speaker_embeddings import cluster_embeddings


def load_embeddings(paths: list[Path]):
    embeddings = {}
    for path in paths:
        for key, value in EmbeddingStore(path).load().items():
            if key in embeddings and embeddings[key] != value:
                raise ValueError(f"conflicting embedding: {key}")
            embeddings[key] = value
    return [embeddings[key] for key in sorted(embeddings)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.78)
    args = parser.parse_args()
    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")
    embeddings = load_embeddings([p.expanduser().resolve() for p in args.embeddings])
    clusters = cluster_embeddings(embeddings, threshold=args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cluster_payload(clusters), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = build_manifest(
        args.output,
        artifact_id="voice-clusters:json",
        recording_id="global",
        stage="embeddings",
        kind="voice_clusters",
        producer="cluster-speakers",
        model_version=embeddings[0].model_version if embeddings else None,
    )
    write_manifest(manifest, args.output.with_suffix(args.output.suffix + ".manifest.json"))
    print(f"Embeddings: {len(embeddings)}; VOICE_CLUSTER groups: {len(clusters)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
