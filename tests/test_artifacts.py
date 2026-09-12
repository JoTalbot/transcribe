from pathlib import Path

import pytest

from transcribe_intelligence.artifacts import build_manifest, verify_manifest, write_manifest


def test_artifact_manifest_round_trip_and_verification(tmp_path: Path):
    artifact = tmp_path / "result.json"
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    manifest = build_manifest(artifact, artifact_id="a1", recording_id="r1", stage="asr", kind="transcript", producer="test")

    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest, manifest_path)

    assert manifest_path.is_file()
    assert verify_manifest(manifest)
    assert manifest.sha256
    assert manifest.size_bytes == artifact.stat().st_size


def test_tampering_is_detected(tmp_path: Path):
    artifact = tmp_path / "result.txt"
    artifact.write_text("original", encoding="utf-8")
    manifest = build_manifest(artifact, artifact_id="a1", recording_id="r1", stage="asr", kind="transcript", producer="test")
    artifact.write_text("changed", encoding="utf-8")
    assert not verify_manifest(manifest)


def test_missing_artifact_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        build_manifest(tmp_path / "missing", artifact_id="a1", recording_id="r1", stage="asr", kind="transcript", producer="test")
