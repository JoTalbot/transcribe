"""Portable artifact exchange contracts for pipeline workers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    artifact_id: str
    recording_id: str
    stage: str
    kind: str
    path: str
    sha256: str
    size_bytes: int
    producer: str
    model_version: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(path: Path, *, artifact_id: str, recording_id: str, stage: str, kind: str, producer: str, model_version: str | None = None) -> ArtifactManifest:
    """Build a manifest from an existing immutable artifact file."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return ArtifactManifest(
        artifact_id=artifact_id,
        recording_id=recording_id,
        stage=stage,
        kind=kind,
        path=str(resolved),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        producer=producer,
        model_version=model_version,
    )


def write_immutable_text(path: Path, text: str) -> None:
    """Create text once; identical repeats are idempotent and changes are rejected."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        return
    except FileExistsError:
        try:
            existing = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"existing artifact is unreadable: {path}") from exc
        if existing == text:
            return
        raise ValueError(f"artifact already exists with different content: {path}")


def _manifest_json(manifest: ArtifactManifest) -> str:
    return json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_manifest(manifest: ArtifactManifest, path: Path) -> None:
    """Create a manifest exclusively; identical repeats are idempotent and changes are rejected."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _manifest_json(manifest)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return
    except FileExistsError:
        try:
            existing = ArtifactManifest(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"existing artifact manifest is invalid: {path}") from exc
        if existing != manifest:
            raise ValueError(f"artifact manifest already exists with different content: {path}")
        return


def verify_manifest(manifest: ArtifactManifest) -> bool:
    """Verify artifact existence, byte count, and checksum."""
    path = Path(manifest.path)
    return path.is_file() and path.stat().st_size == manifest.size_bytes and sha256_file(path) == manifest.sha256
