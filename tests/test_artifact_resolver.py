import json
from pathlib import Path

import pytest

from transcribe_intelligence.artifact_resolver import ArtifactResolutionError, ArtifactResolver
from transcribe_intelligence.artifacts import build_manifest, write_manifest


def _write_artifact(root: Path, artifact_id: str = "r1:diarization:json") -> Path:
    recording = root / "r1"
    recording.mkdir(parents=True)
    artifact = recording / "r1.json"
    artifact.write_text('{"segments": []}\n', encoding="utf-8")
    manifest = build_manifest(
        artifact,
        artifact_id=artifact_id,
        recording_id="r1",
        stage="diarization",
        kind="json",
        producer="test",
    )
    write_manifest(manifest, recording / "r1_diarization_json.manifest.json")
    return artifact


def test_resolver_maps_artifact_id_to_verified_path(tmp_path: Path):
    artifact = _write_artifact(tmp_path)
    resolver = ArtifactResolver(tmp_path)

    assert resolver.resolve_path("r1:diarization:json") == artifact.resolve()


def test_resolver_detects_tampering(tmp_path: Path):
    artifact = _write_artifact(tmp_path)
    artifact.write_text('{"segments": ["tampered"]}\n', encoding="utf-8")

    with pytest.raises(ArtifactResolutionError, match="checksum verification failed"):
        ArtifactResolver(tmp_path).resolve_path("r1:diarization:json")


def test_resolver_rejects_duplicate_artifact_ids(tmp_path: Path):
    _write_artifact(tmp_path)
    second = tmp_path / "copy"
    second.mkdir()
    artifact = second / "r1.json"
    artifact.write_text("copy\n", encoding="utf-8")
    manifest = build_manifest(
        artifact,
        artifact_id="r1:diarization:json",
        recording_id="r1",
        stage="diarization",
        kind="json",
        producer="test",
    )
    write_manifest(manifest, second / "copy.manifest.json")

    with pytest.raises(ArtifactResolutionError, match="duplicate artifact_id"):
        ArtifactResolver(tmp_path).resolve("r1:diarization:json")


def test_resolver_supports_manifest_with_relative_path(tmp_path: Path):
    artifact = _write_artifact(tmp_path)
    manifest_path = tmp_path / "r1" / "r1_diarization_json.manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["path"] = "r1/r1.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert ArtifactResolver(tmp_path).resolve_path("r1:diarization:json") == artifact.resolve()
