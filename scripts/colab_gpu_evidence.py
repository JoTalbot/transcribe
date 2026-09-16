"""Collect auditable Colab GPU and artifact evidence without exposing secrets."""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (SRC_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from transcribe_intelligence.artifact_resolver import ArtifactResolver


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


def collect_gpu() -> dict[str, object]:
    result: dict[str, object] = {
        "torch_version": _package_version("torch"),
        "cuda_available": False,
        "cuda_version": None,
        "gpu": None,
        "vram_total_bytes": None,
        "vram_allocated_bytes": None,
        "vram_reserved_bytes": None,
    }
    try:
        import torch
    except ImportError:
        return result
    available = bool(torch.cuda.is_available())
    result["torch_version"] = getattr(torch, "__version__", result["torch_version"])
    result["cuda_available"] = available
    result["cuda_version"] = getattr(torch.version, "cuda", None)
    if not available:
        return result
    device = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(device)
    result["gpu"] = props.name
    result["vram_total_bytes"] = int(props.total_memory)
    result["vram_allocated_bytes"] = int(torch.cuda.memory_allocated(device))
    result["vram_reserved_bytes"] = int(torch.cuda.memory_reserved(device))
    return result


def collect_artifacts(root: Path) -> list[dict[str, object]]:
    resolver = ArtifactResolver(root)
    artifacts: list[dict[str, object]] = []
    for manifest_path in sorted(root.rglob("*.manifest.json")):
        manifest = resolver._read_manifest(manifest_path)
        verified = False
        try:
            resolver.resolve(manifest.artifact_id)
            verified = True
        except Exception:
            verified = False
        artifacts.append(
            {
                "artifact_id": manifest.artifact_id,
                "recording_id": manifest.recording_id,
                "stage": manifest.stage,
                "kind": manifest.kind,
                "size_bytes": manifest.size_bytes,
                "sha256": manifest.sha256,
                "producer": manifest.producer,
                "model_version": manifest.model_version,
                "verified": verified,
                "manifest": str(manifest_path),
            }
        )
    return artifacts


def collect(root: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "collected_at_unix": time.time(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            "faster_whisper": _package_version("faster-whisper"),
            "pyannote_audio": _package_version("pyannote.audio"),
            "speechbrain": _package_version("speechbrain"),
            "torchaudio": _package_version("torchaudio"),
            "transformers": _package_version("transformers"),
        },
        "gpu": collect_gpu(),
        "artifacts": collect_artifacts(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Artifact root containing *.manifest.json files")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence output path")
    args = parser.parse_args()
    evidence = collect(args.root)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
