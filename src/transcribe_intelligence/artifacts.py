"""Portable artifact exchange contracts for pipeline workers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile


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


def write_manifest(manifest: ArtifactManifest, path: Path) -> None:
    """Atomically persist an immutable JSON artifact manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = ArtifactManifest(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"existing artifact manifest is invalid: {path}") from exc
        if existing != manifest:
            raise ValueError(f"artifact manifest already exists with different content: {path}")
        return

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_manifest(manifest: ArtifactManifest) -> bool:
    """Verify artifact existence, byte count, and checksum."""
    path = Path(manifest.path)
    return path.is_file() and path.stat().st_size == manifest.size_bytes and sha256_file(path) == manifest.sha256
