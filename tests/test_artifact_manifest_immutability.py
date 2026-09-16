from pathlib import Path

import pytest

from transcribe_intelligence.artifacts import build_manifest, write_manifest


def test_write_manifest_is_idempotent_for_same_manifest(tmp_path: Path) -> None:
    artifact = tmp_path / "result.json"
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    manifest = build_manifest(
        artifact,
        artifact_id="a1",
        recording_id="r1",
        stage="asr",
        kind="transcript",
        producer="test",
    )
    manifest_path = tmp_path / "manifest.json"

    write_manifest(manifest, manifest_path)
    original = manifest_path.read_text(encoding="utf-8")
    write_manifest(manifest, manifest_path)

    assert manifest_path.read_text(encoding="utf-8") == original


def test_write_manifest_rejects_replacement_of_existing_artifact_identity(tmp_path: Path) -> None:
    artifact = tmp_path / "result.json"
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    first = build_manifest(
        artifact,
        artifact_id="a1",
        recording_id="r1",
        stage="asr",
        kind="transcript",
        producer="test",
    )
    second = build_manifest(
        artifact,
        artifact_id="a2",
        recording_id="r1",
        stage="asr",
        kind="transcript",
        producer="test",
    )

    write_manifest(first, manifest_path)

    with pytest.raises(ValueError, match="already exists with different content"):
        write_manifest(second, manifest_path)

    assert '"artifact_id": "a1"' in manifest_path.read_text(encoding="utf-8")
