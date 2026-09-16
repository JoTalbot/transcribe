from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_replayed_completed_result_after_database_completion_is_quarantined(tmp_path: Path) -> None:
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-replay-complete", "/audio/replay.wav"))
    job_id = stable_job_id("rec-replay-complete", "ingest")
    repository.put_job(
        ExecutionJob(
            job_id,
            "rec-replay-complete",
            "ingest",
            "completed",
            attempt=1,
            artifact_id="rec-replay-complete:ingest:json",
        )
    )
    exchange = FileExchange(tmp_path / "exchange")
    result_path = exchange.put_result(
        ResultEnvelope(
            job_id,
            "completed",
            artifact_id="rec-replay-complete:ingest:json",
            worker="oracle-local",
            lease_id="already-consumed-lease",
        )
    )

    changed = ExchangeCoordinator(repository, exchange).apply_results()

    assert changed == 0
    assert not result_path.exists()
    quarantined = exchange.results / "quarantine" / result_path.name
    assert quarantined.exists()
    assert "stale or foreign result" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")
    current = repository.get_job(job_id)
    assert current is not None
    assert current.status == "completed"
    assert current.artifact_id == "rec-replay-complete:ingest:json"


def test_replayed_failed_result_after_database_failure_is_quarantined(tmp_path: Path) -> None:
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-replay-failed", "/audio/replay-failed.wav"))
    job_id = stable_job_id("rec-replay-failed", "ingest")
    repository.put_job(
        ExecutionJob(
            job_id,
            "rec-replay-failed",
            "ingest",
            "failed",
            attempt=1,
            error="worker failed",
        )
    )
    exchange = FileExchange(tmp_path / "exchange")
    result_path = exchange.put_result(
        ResultEnvelope(
            job_id,
            "failed",
            error="worker failed",
            worker="oracle-local",
            lease_id="already-consumed-lease",
        )
    )

    changed = ExchangeCoordinator(repository, exchange).apply_results()

    assert changed == 0
    assert not result_path.exists()
    quarantined = exchange.results / "quarantine" / result_path.name
    assert quarantined.exists()
    assert "stale or foreign result" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")
    current = repository.get_job(job_id)
    assert current is not None
    assert current.status == "failed"
    assert current.error == "worker failed"
