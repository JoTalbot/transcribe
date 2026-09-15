"""Deterministic resolution of exchange artifact IDs to verified files."""
from __future__ import annotations

import json
from pathlib import Path

from .artifacts import ArtifactManifest, verify_manifest


class ArtifactResolutionError(RuntimeError):
    """Raised when an artifact ID cannot be safely resolved."""


class ArtifactResolver:
    """Resolve artifact IDs from manifests rooted at a local exchange directory."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def _manifest_files(self) -> list[Path]:
        return sorted(self.root.rglob("*.manifest.json"))

    def _find_manifest(self, artifact_id: str) -> tuple[Path, ArtifactManifest]:
        if not artifact_id.strip():
            raise ValueError("artifact_id must not be empty")
        matches: list[tuple[Path, ArtifactManifest]] = []
        for manifest_path in self._manifest_files():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = ArtifactManifest(**payload)
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                raise ArtifactResolutionError(f"invalid artifact manifest: {manifest_path}") from exc
            if manifest.artifact_id == artifact_id:
                matches.append((manifest_path, manifest))
        if not matches:
            raise FileNotFoundError(f"artifact manifest not found: {artifact_id}")
        if len(matches) > 1:
            raise ArtifactResolutionError(f"duplicate artifact_id: {artifact_id}")
        return matches[0]

    def resolve(self, artifact_id: str) -> ArtifactManifest:
        """Resolve an artifact ID to its manifest."""
        return self._find_manifest(artifact_id)[1]

    def resolve_path(self, artifact_id: str) -> Path:
        """Resolve and checksum-verify an artifact, supporting portable manifests."""
        manifest_path, manifest = self._find_manifest(artifact_id)
        declared = Path(manifest.path)
        candidates: list[Path] = []
        if not declared.is_absolute():
            candidates.append((self.root / declared).resolve())
        else:
            candidates.append(declared.expanduser().resolve())
            candidates.append((manifest_path.parent / declared.name).resolve())

        for candidate in dict.fromkeys(candidates):
            if candidate.is_file() and self.root in candidate.parents:
                portable = ArtifactManifest(
                    artifact_id=manifest.artifact_id,
                    recording_id=manifest.recording_id,
                    stage=manifest.stage,
                    kind=manifest.kind,
                    path=str(candidate),
                    sha256=manifest.sha256,
                    size_bytes=manifest.size_bytes,
                    producer=manifest.producer,
                    model_version=manifest.model_version,
                )
                if not verify_manifest(portable):
                    raise ArtifactResolutionError(f"artifact checksum verification failed: {artifact_id}")
                return candidate
        raise ArtifactResolutionError(f"artifact is unavailable inside resolver root: {artifact_id}")
