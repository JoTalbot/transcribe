"""Validate a collected Colab GPU evidence snapshot for physical E2E use."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_STAGES = {
    "ingest",
    "normalize",
    "asr",
    "diarization",
    "embeddings",
    "text_analysis",
    "topics",
    "linking",
    "graph",
}
REQUIRED_GPU_PACKAGES = ("faster_whisper", "pyannote_audio", "speechbrain", "torchaudio")


def validate(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["evidence payload must be a JSON object"]
    if payload.get("schema_version") != 2:
        errors.append("unsupported evidence schema_version")

    gpu = payload.get("gpu")
    if not isinstance(gpu, dict):
        errors.append("gpu section is missing or invalid")
    else:
        if gpu.get("cuda_available") is not True:
            errors.append("CUDA is not available; snapshot is not physical GPU evidence")
        for field in ("gpu", "cuda_version", "torch_version", "vram_total_bytes", "peak_vram_allocated_bytes"):
            if gpu.get(field) in (None, ""):
                errors.append(f"gpu.{field} is missing")

    packages = payload.get("packages")
    if not isinstance(packages, dict):
        errors.append("packages section is missing or invalid")
    else:
        for name in REQUIRED_GPU_PACKAGES:
            if not packages.get(name):
                errors.append(f"packages.{name} is missing")

    runtime = payload.get("runtime")
    metrics = runtime.get("worker_metrics") if isinstance(runtime, dict) else None
    if not isinstance(metrics, list) or not metrics:
        errors.append("no worker runtime metrics snapshot found")
    elif not any(isinstance(item, dict) and item.get("verified") is True for item in metrics):
        errors.append("no verified worker runtime metrics snapshot found")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("no artifacts found in evidence")
    else:
        stages = {item.get("stage") for item in artifacts if isinstance(item, dict) and item.get("verified") is True}
        missing_stages = sorted(EXPECTED_STAGES - stages)
        if missing_stages:
            errors.append("missing verified pipeline stages: " + ", ".join(missing_stages))
        if any(not isinstance(item, dict) or item.get("verified") is not True for item in artifacts):
            errors.append("one or more artifact entries are unverified")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Collected colab_gpu_evidence.json")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read evidence JSON: {exc}")
    errors = validate(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Colab GPU evidence is structurally valid for physical E2E review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
