from pathlib import Path

from transcribe_intelligence.exchange import FileExchange
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_stale_processing_marker_is_quarantined_and_retry_is_redispatched(tmp_path: Path):
    repository = InMemoryRepository()
    recording_id = "rec-stale-processing"
    job_id = stable_job_id(recording_id, "ingest")
    repository.put_recording(Recording(recording_id, "/audio/input.wav"))
    repository.put_job(ExecutionJob(job_id, recording_id, "ingest", "retry", attempt=1))

    exchange = FileExchange(tmp_path / "exchange")
    processing = exchange.root / "processing"
    processing.mkdir(parents=True)
    processing_file = processing / f"{job_id}.json"
    processing_file.write_text(
        f'{{"job_id":"{job_id}","recording_id":"{recording_id}","stage":"ingest","worker":"old-worker","lease_id":"expired"}}\n',
        encoding="utf-8",
    )

    coordinator = ExchangeCoordinator(repository, exchange)
    dispatches = coordinator.dispatch_ready(recording_id, worker="new-worker")

    assert [dispatch.job_id for dispatch in dispatches] == [job_id]
    request = exchange.get_request(job_id)
    assert request.worker == "new-worker"
    assert request.lease_id is not None
    assert not processing_file.exists()
    quarantined = exchange.results / "quarantine" / processing_file.name
    assert quarantined.exists()
    assert "orphaned processing marker" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")
