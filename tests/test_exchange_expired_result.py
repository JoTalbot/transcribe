from datetime import datetime, timedelta, timezone
from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_expired_lease_result_is_quarantined_instead_of_aborting_cycle(tmp_path: Path) -> None:
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-expired", "/audio/expired.wav"))
    job_id = stable_job_id("rec-expired", "ingest")
    expired = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    repository.put_job(
        ExecutionJob(
            job_id,
            "rec-expired",
            "ingest",
            "running",
            attempt=1,
            worker="worker-a",
            lease_id="expired-lease",
            lease_until=expired,
        )
    )
    exchange = FileExchange(tmp_path / "exchange")
    result_path = exchange.put_result(
        ResultEnvelope(
            job_id,
            "completed",
            artifact_id="rec-expired:ingest:json",
            worker="worker-a",
            lease_id="expired-lease",
        )
    )

    changed = ExchangeCoordinator(repository, exchange).apply_results()

    assert changed == 0
    assert not result_path.exists()
    quarantined = exchange.results / "quarantine" / result_path.name
    assert quarantined.exists()
    assert "stale or foreign result" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")
