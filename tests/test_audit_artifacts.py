import json
from pathlib import Path

from transcribe_intelligence.artifacts import build_manifest, write_manifest
from scripts.audit_artifacts import audit_artifacts


def _publish(root: Path, *, artifact_id: str = "art-1", relative_path: str = "rec/a.txt") -> Path:
    payload = root / relative_path
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text("payload\n", encoding="utf-8")
    manifest = build_manifest(
        artifact_id=artifact_id,
        recording_id="rec-1",
        stage="ingest",
        kind="text",
        path=payload,
        producer="test",
        model_version="test-1",
    )
    manifest_path = payload.with_name(f"{payload.name}.manifest.json")
    write_manifest(manifest, manifest_path)
    return payload


def test_audit_accepts_verified_artifact_store(tmp_path: Path) -> None:
    _publish(tmp_path)

    report = audit_artifacts(tmp_path)

    assert report["healthy"] is True
    assert report["issue_count"] == 0
    assert report["manifest_count"] == 1


def test_audit_reports_tampered_payload(tmp_path: Path) -> None:
    payload = _publish(tmp_path)
    payload.write_text("tampered\n", encoding="utf-8")

    report = audit_artifacts(tmp_path)

    assert report["healthy"] is False
    assert any(issue["type"] == "checksum_mismatch" for issue in report["issues"])


def test_audit_reports_missing_payload(tmp_path: Path) -> None:
    payload = _publish(tmp_path)
    payload.unlink()

    report = audit_artifacts(tmp_path)

    assert any(issue["type"] == "missing_payload" for issue in report["issues"])


def test_audit_reports_orphan_payload(tmp_path: Path) -> None:
    _publish(tmp_path)
    orphan = tmp_path / "rec" / "orphan.txt"
    orphan.write_text("orphan\n", encoding="utf-8")

    report = audit_artifacts(tmp_path)

    assert any(issue["type"] == "orphan_payload" and issue["path"] == "rec/orphan.txt" for issue in report["issues"])


def test_audit_reports_duplicate_artifact_id(tmp_path: Path) -> None:
    _publish(tmp_path, artifact_id="duplicate", relative_path="a.txt")
    _publish(tmp_path, artifact_id="duplicate", relative_path="b.txt")

    report = audit_artifacts(tmp_path)

    duplicates = [issue for issue in report["issues"] if issue["type"] == "duplicate_artifact_id"]
    assert len(duplicates) == 2


def test_audit_reports_malformed_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "broken.manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")

    report = audit_artifacts(tmp_path)

    assert any(issue["type"] == "invalid_manifest" for issue in report["issues"])


def test_audit_reports_manifest_path_outside_root(tmp_path: Path) -> None:
    payload = tmp_path / "payload.txt"
    payload.write_text("payload\n", encoding="utf-8")
    manifest = build_manifest(
        artifact_id="outside",
        recording_id="rec-1",
        stage="ingest",
        kind="text",
        path=payload,
        producer="test",
        model_version="test-1",
    )
    manifest_path = tmp_path / "outside.manifest.json"
    payload_data = json.loads(json.dumps(manifest.__dict__)) if hasattr(manifest, "__dict__") else {
        "artifact_id": manifest.artifact_id,
        "recording_id": manifest.recording_id,
        "stage": manifest.stage,
        "kind": manifest.kind,
        "path": "/outside/root/payload.txt",
        "sha256": manifest.sha256,
        "size_bytes": manifest.size_bytes,
        "producer": manifest.producer,
        "model_version": manifest.model_version,
    }
    payload_data["path"] = "/outside/root/payload.txt"
    manifest_path.write_text(json.dumps(payload_data), encoding="utf-8")

    report = audit_artifacts(tmp_path)

    assert any(issue["type"] == "path_outside_root" for issue in report["issues"])
