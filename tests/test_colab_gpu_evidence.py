from pathlib import Path

import pytest

from scripts.colab_gpu_evidence import collect, collect_artifacts
from transcribe_intelligence.artifacts import build_manifest, sha256_file, write_manifest


def test_collect_artifacts_verifies_manifest_and_reports_metadata(tmp_path: Path):
    root = tmp_path / "artifacts"
    artifact = root / "r1" / "asr" / "result.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"text":"hello"}\n', encoding="utf-8")
    manifest = build_manifest(
        artifact,
        artifact_id="r1:asr:json",
        recording_id="r1",
        stage="asr",
        kind="json",
        producer="test",
        model_version="large-v3",
    )
    write_manifest(manifest, artifact.with_suffix(artifact.suffix + ".manifest.json"))

    evidence = collect_artifacts(root)

    assert len(evidence) == 1
    assert evidence[0]["artifact_id"] == "r1:asr:json"
    assert evidence[0]["stage"] == "asr"
    assert evidence[0]["model_version"] == "large-v3"
    assert evidence[0]["verified"] is True
    assert evidence[0]["size_bytes"] == artifact.stat().st_size


def test_collect_artifacts_marks_tampered_artifact_unverified(tmp_path: Path):
    root = tmp_path / "artifacts"
    artifact = root / "r1" / "normalize" / "audio.wav"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"original")
    manifest = build_manifest(
        artifact,
        artifact_id="r1:normalize:audio",
        recording_id="r1",
        stage="normalize",
        kind="audio",
        producer="test",
    )
    write_manifest(manifest, artifact.with_suffix(artifact.suffix + ".manifest.json"))
    artifact.write_bytes(b"tampered")

    evidence = collect_artifacts(root)

    assert evidence[0]["verified"] is False
    assert "checksum" in evidence[0]["error"]


def test_collect_includes_worker_runtime_metrics(tmp_path: Path):
    metrics = tmp_path / "worker-metrics-1.json"
    metrics.write_text(
        '{"schema_version":1,"started_at_unix":1.0,"finished_at_unix":13.5,"wall_clock_seconds":12.5,"max_rss_bytes":100,"model_load_seconds":{"total_model_load_seconds":8.0},"jobs":[]}',
        encoding="utf-8",
    )

    evidence = collect(tmp_path)

    assert evidence["schema_version"] == 2
    runtime = evidence["runtime"]["worker_metrics"]
    assert len(runtime) == 1
    assert runtime[0]["verified"] is True
    assert runtime[0]["metrics"]["wall_clock_seconds"] == 12.5
    assert runtime[0]["size_bytes"] == metrics.stat().st_size
    assert runtime[0]["sha256"] == sha256_file(metrics)


def test_collect_marks_malformed_worker_metrics_unverified(tmp_path: Path):
    metrics = tmp_path / "worker-metrics-bad.json"
    metrics.write_text("not-json", encoding="utf-8")

    evidence = collect(tmp_path)

    runtime = evidence["runtime"]["worker_metrics"]
    assert runtime[0]["verified"] is False
    assert runtime[0]["error"]
    assert "json" in runtime[0]["error"].lower()


def test_collect_marks_schema_invalid_worker_metrics_unverified(tmp_path: Path):
    metrics = tmp_path / "worker-metrics-invalid-schema.json"
    metrics.write_text(
        '{"schema_version":1,"jobs":[]}',
        encoding="utf-8",
    )

    evidence = collect(tmp_path)

    runtime = evidence["runtime"]["worker_metrics"]
    assert runtime[0]["verified"] is False
    assert "missing required fields" in runtime[0]["error"]


def test_collect_has_stable_schema_without_gpu_requirement(tmp_path: Path):
    evidence = collect(tmp_path)

    assert evidence["schema_version"] == 2
    assert "gpu" in evidence
    assert "runtime" in evidence
    assert "packages" in evidence
    assert evidence["gpu"]["cuda_available"] is False or isinstance(evidence["gpu"]["cuda_available"], bool)


def test_evidence_output_is_immutable(tmp_path: Path):
    output = tmp_path / "evidence.json"
    output.write_text('{"existing":true}\n', encoding="utf-8")

    from scripts.colab_gpu_evidence import main
    import sys

    original_argv = sys.argv
    sys.argv = ["colab_gpu_evidence", "--root", str(tmp_path), "--output", str(output)]
    try:
        with pytest.raises(ValueError, match="artifact already exists with different content"):
            main()
    finally:
        sys.argv = original_argv

    assert output.read_text(encoding="utf-8") == '{"existing":true}\n'
