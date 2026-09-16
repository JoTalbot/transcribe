from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, JobEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_stale_request_after_lease_reclaim_is_quarantined_and_redispatched(tmp_path: Path) -> None:
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-stale-request", "/audio/stale.wav"))
    job_id = stable_job_id("rec-stale-request", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-stale-request", "ingest"))
    exchange = FileExchange(tmp_path / "exchange")
    coordinator = ExchangeCoordinator(repository, exchange)

    first = coordinator.dispatch_ready("rec-stale-request", worker="worker-a")
    assert len(first) == 1
    stale = exchange.get_request(job_id)
    assert stale.worker == "worker-a"
    assert stale.lease_id

    # Simulate PostgreSQL lease recovery while the Drive request was never consumed.
    repository.update_job(
        ExecutionJob(
            job_id,
            "rec-stale-request",
            "ingest",
            "retry",
            attempt=stale_attempt := repository.get_job(job_id).attempt,
            error="lease expired",
        )
    )

    second = coordinator.dispatch_ready("rec-stale-request", worker="worker-b")

    assert [item.job_id for item in second] == [job_id]
    fresh = exchange.get_request(job_id)
    assert fresh.worker == "worker-b"
    assert fresh.lease_id != stale.lease_id
    quarantined = exchange.results / "quarantine" / f"{job_id}.json"
    assert quarantined.exists()
    assert "stale request after lease change" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")
