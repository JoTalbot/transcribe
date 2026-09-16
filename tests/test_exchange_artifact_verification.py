from pathlib import Path

from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def _write_artifact(exchange: FileExchange, recording_id: str, artifact_id: str, content: str = "payload\n") -> Path:
    artifact_dir = exchange.root / "artifacts" / recording_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact = artifact_dir / "artifact.json"
    artifact.write_text(content, encoding="utf-8")
    manifest = build_manifest(
        artifact,
        artifact_id=artifact_id,
        recording_id=recording_id,
        stage="ingest",
        kind="json",
        producer="test",
    )
    write_manifest(manifest, artifact_dir / "artifact.manifest.json")
    return artifact


def _running_job(repository: InMemoryRepository, recording_id: str) -> str:
    repository.put_recording(Recording(recording_id, f"/audio/{recording_id}.wav"))
    job_id = stable_job_id(recording_id, "ingest")
    repository.put_job(
        ExecutionJob(
            job_id,
            recording_id,
            "ingest",
            "running",
            attempt=1,
            worker="oracle",
            lease_id="lease-1",
        )
    )
    return job_id


def test_verified_completed_result_requires_existing_artifact(tmp_path: Path):
    repository = InMemoryRepository()
    job_id = _running_job(repository, "rec-missing")
    exchange = FileExchange(tmp_path / "exchange")
    result_path = exchange.put_result(
        ResultEnvelope(
            job_id,
            "completed",
            artifact_id="rec-missing:ingest:json",
            worker="oracle",
            lease_id="lease-1",
        )
    )

    changed = ExchangeCoordinator(repository, exchange, verify_artifacts=True).apply_results()

    assert changed == 0
    assert repository.get_job(job_id).status == "running"
    assert not result_path.exists()
    quarantined = exchange.results / "quarantine" / result_path.name
    assert quarantined.exists()
    assert "invalid completed artifact" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")


def test_verified_completed_result_rejects_tampered_artifact(tmp_path: Path):
    repository = InMemoryRepository()
    job_id = _running_job(repository, "rec-tampered")
    exchange = FileExchange(tmp_path / "exchange")
    artifact_id = "rec-tampered:ingest:json"
    artifact = _write_artifact(exchange, "rec-tampered", artifact_id)
    artifact.write_text("tampered\n", encoding="utf-8")
    result_path = exchange.put_result(
        ResultEnvelope(job_id, "completed", artifact_id=artifact_id, worker="oracle", lease_id="lease-1")
    )

    changed = ExchangeCoordinator(repository, exchange, verify_artifacts=True).apply_results()

    assert changed == 0
    assert repository.get_job(job_id).status == "running"
    assert not result_path.exists()
    quarantined = exchange.results / "quarantine" / result_path.name
    assert quarantined.exists()
    assert "invalid completed artifact" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")


def test_verified_completed_result_accepts_valid_manifest_and_artifact(tmp_path: Path):
    repository = InMemoryRepository()
    job_id = _running_job(repository, "rec-valid")
    exchange = FileExchange(tmp_path / "exchange")
    artifact_id = "rec-valid:ingest:json"
    _write_artifact(exchange, "rec-valid", artifact_id)
    result_path = exchange.put_result(
        ResultEnvelope(job_id, "completed", artifact_id=artifact_id, worker="oracle", lease_id="lease-1")
    )

    changed = ExchangeCoordinator(repository, exchange, verify_artifacts=True).apply_results()

    assert changed == 1
    completed = repository.get_job(job_id)
    assert completed.status == "completed"
    assert completed.artifact_id == artifact_id
    assert not result_path.exists()
    assert not (exchange.results / "quarantine" / result_path.name).exists()


def test_verified_completed_result_rejects_missing_artifact_id(tmp_path: Path):
    repository = InMemoryRepository()
    job_id = _running_job(repository, "rec-no-id")
    exchange = FileExchange(tmp_path / "exchange")
    result_path = exchange.put_result(
        ResultEnvelope(job_id, "completed", worker="oracle", lease_id="lease-1")
    )

    changed = ExchangeCoordinator(repository, exchange, verify_artifacts=True).apply_results()

    assert changed == 0
    assert repository.get_job(job_id).status == "running"
    assert not result_path.exists()
    quarantined = exchange.results / "quarantine" / result_path.name
    assert quarantined.exists()
    assert "completed result requires artifact_id" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")
