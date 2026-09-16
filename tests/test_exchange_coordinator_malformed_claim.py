from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, JobEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_dispatch_quarantines_malformed_request_and_retries_job(tmp_path: Path):
    repository = InMemoryRepository()
    recording_id = "rec-malformed-request"
    repository.put_recording(Recording(recording_id, "/audio/input.wav"))
    job_id = stable_job_id(recording_id, "ingest")
    repository.put_job(ExecutionJob(job_id, recording_id, "ingest"))
    exchange = FileExchange(tmp_path / "exchange")

    request = exchange.requests / f"{job_id}.json"
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text("{not-json", encoding="utf-8")

    dispatches = ExchangeCoordinator(repository).dispatch_ready(recording_id)

    assert [item.job_id for item in dispatches] == [job_id]
    assert repository.get_job(job_id).status == "running"
    assert not request.exists()
    quarantined = exchange.results / "quarantine" / request.name
    assert quarantined.exists()
    assert "malformed exchange request" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")


def test_dispatch_quarantines_malformed_processing_claim_and_retries_job(tmp_path: Path):
    repository = InMemoryRepository()
    recording_id = "rec-malformed-processing"
    repository.put_recording(Recording(recording_id, "/audio/input.wav"))
    job_id = stable_job_id(recording_id, "ingest")
    repository.put_job(ExecutionJob(job_id, recording_id, "ingest"))
    exchange = FileExchange(tmp_path / "exchange")

    processing = exchange.root / "processing" / f"{job_id}.json"
    processing.parent.mkdir(parents=True, exist_ok=True)
    processing.write_text("{not-json", encoding="utf-8")

    dispatches = ExchangeCoordinator(repository).dispatch_ready(recording_id)

    assert [item.job_id for item in dispatches] == [job_id]
    assert repository.get_job(job_id).status == "running"
    assert not processing.exists()
    quarantined = exchange.results / "quarantine" / processing.name
    assert quarantined.exists()
    assert "malformed processing claim" in quarantined.with_suffix(quarantined.suffix + ".error").read_text(encoding="utf-8")


def test_dispatch_quarantines_invalid_processing_claim_fields(tmp_path: Path):
    repository = InMemoryRepository()
    recording_id = "rec-invalid-processing"
    repository.put_recording(Recording(recording_id, "/audio/input.wav"))
    job_id = stable_job_id(recording_id, "ingest")
    repository.put_job(ExecutionJob(job_id, recording_id, "ingest"))
    exchange = FileExchange(tmp_path / "exchange")

    processing = exchange.root / "processing" / f"{job_id}.json"
    processing.parent.mkdir(parents=True, exist_ok=True)
    processing.write_text(
        '{"job_id":"%s","recording_id":"%s","stage":"ingest","worker":"","lease_id":""}'
        % (job_id, recording_id),
        encoding="utf-8",
    )

    dispatches = ExchangeCoordinator(repository).dispatch_ready(recording_id)

    assert [item.job_id for item in dispatches] == [job_id]
    assert repository.get_job(job_id).status == "running"
    assert not processing.exists()
    quarantined = exchange.results / "quarantine" / processing.name
    assert quarantined.exists()
