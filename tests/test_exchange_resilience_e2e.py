from itertools import pairwise
from pathlib import Path

import pytest

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_dispatch_does_not_double_publish_existing_request(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-7", "/audio/seven.wav"))
    job_id = stable_job_id("rec-7", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-7", "ingest"))
    exchange = FileExchange(tmp_path / "exchange")
    coordinator = ExchangeCoordinator(repository, exchange)

    first = coordinator.dispatch_ready("rec-7", worker="colab-1")
    second = coordinator.dispatch_ready("rec-7", worker="colab-1")

    assert [item.job_id for item in first] == [job_id]
    assert second == []
    assert repository.get_job(job_id).attempt == 1


def test_dispatch_does_not_duplicate_claimed_exchange_job(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-8", "/audio/eight.wav"))
    job_id = stable_job_id("rec-8", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-8", "ingest", "retry", attempt=1))
    exchange = FileExchange(tmp_path / "exchange")
    processing = exchange.root / "processing"
    processing.mkdir(parents=True)
    (processing / f"{job_id}.json").write_text("{}", encoding="utf-8")

    assert ExchangeCoordinator(repository, exchange).dispatch_ready("rec-8") == []
    assert repository.get_job(job_id).attempt == 1


def test_heartbeat_refreshes_lease_without_changing_attempt():
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-9", "/audio/nine.wav"))
    job_id = stable_job_id("rec-9", "ingest")
    job = ExecutionJob(job_id, "rec-9", "ingest", "running", attempt=2, worker="colab-9", updated_at="2026-01-01T00:00:00+00:00")
    repository.put_job(job)

    refreshed = ExchangeCoordinator(repository, FileExchange(Path("/tmp/unused"))).heartbeat(job_id, "colab-9")

    assert refreshed.attempt == 2
    assert refreshed.worker == "colab-9"
    assert refreshed.updated_at != job.updated_at


def test_heartbeat_rejects_wrong_worker():
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-10", "/audio/ten.wav"))
    job_id = stable_job_id("rec-10", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-10", "ingest", "running", attempt=1, worker="owner"))

    with pytest.raises(ValueError, match="owned by worker"):
        ExchangeCoordinator(repository, FileExchange(Path("/tmp/unused"))).heartbeat(job_id, "other")


def test_true_exchange_pipeline_advances_ingest_normalize_asr(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-e2e", "/audio/e2e.wav"))
    jobs = [
        ExecutionJob(stable_job_id("rec-e2e", stage), "rec-e2e", stage)
        for stage in ("ingest", "normalize", "asr")
    ]
    for job in jobs:
        repository.put_job(job)

    exchange = FileExchange(tmp_path / "exchange")
    coordinator = ExchangeCoordinator(repository, exchange)
    expected = {
        "ingest": "rec-e2e:ingest:json",
        "normalize": "rec-e2e:normalize:json",
        "asr": "rec-e2e:asr:json",
    }

    dispatches = coordinator.dispatch_ready("rec-e2e", worker="colab")
    assert [item.job_id for item in dispatches] == [jobs[0].job_id]

    for current, next_job in pairwise(jobs):
        exchange.put_result(ResultEnvelope(current.job_id, "completed", artifact_id=expected[current.stage]))
        dispatches, changed = coordinator.cycle("rec-e2e", worker="colab")
        assert changed == 1
        assert [item.job_id for item in dispatches] == [next_job.job_id]
        request = exchange.get_request(next_job.job_id)
        assert request.input_artifact_id == expected[current.stage]

    exchange.put_result(ResultEnvelope(jobs[-1].job_id, "completed", artifact_id=expected["asr"]))
    assert coordinator.apply_results() == 1
    assert all(repository.get_job(job.job_id).status == "completed" for job in jobs)
