from datetime import datetime, timezone
from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording
from transcribe_intelligence.scheduler import Scheduler


def test_scheduler_dispatches_multiple_recordings_deterministically(tmp_path: Path):
    repository = InMemoryRepository()
    for recording_id in ("rec-b", "rec-a"):
        repository.put_recording(Recording(recording_id, f"/input/{recording_id}.wav"))
        repository.put_job(ExecutionJob(stable_job_id(recording_id, "ingest"), recording_id, "ingest"))

    scheduler = Scheduler(repository, FileExchange(tmp_path / "exchange"))
    report, dispatches = scheduler.run_once(["rec-b", "rec-a"], worker="colab-1")

    assert report.recovered == 0
    assert report.failed == 0
    assert report.results_applied == 0
    assert [item.job_id for item in dispatches] == ["rec-a:ingest", "rec-b:ingest"]
    assert repository.get_job("rec-a:ingest").status == "running"
    assert repository.get_job("rec-a:ingest").worker == "colab-1"


def test_scheduler_applies_result_then_dispatches_next_stage(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-1", "/input/audio.wav"))
    repository.put_job(ExecutionJob(stable_job_id("rec-1", "asr"), "rec-1", "asr"))
    repository.put_job(ExecutionJob(stable_job_id("rec-1", "diarization"), "rec-1", "diarization"))
    exchange = FileExchange(tmp_path / "exchange")
    scheduler = Scheduler(repository, exchange)

    scheduler.run_once(["rec-1"])
    exchange.put_result(ResultEnvelope("rec-1:asr", "completed", artifact_id="rec-1:asr:json"))
    report, dispatches = scheduler.run_once(["rec-1"])

    assert report.results_applied == 1
    assert [item.job_id for item in dispatches] == ["rec-1:diarization"]
    request = exchange.get_request("rec-1:diarization")
    assert request.input_artifact_id == "rec-1:asr:json"
    assert request.input_path is None


def test_scheduler_result_wins_over_stale_recovery(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-1", "/input/audio.wav"))
    stale = datetime(2026, 9, 13, 14, 0, tzinfo=timezone.utc).isoformat()
    job_id = stable_job_id("rec-1", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-1", "ingest", "running", 1, updated_at=stale))
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope(job_id, "completed", artifact_id="rec-1:ingest:json"))
    scheduler = Scheduler(repository, exchange)

    report, dispatches = scheduler.run_once(["rec-1"], now=datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc))

    assert report.results_applied == 1
    assert report.recovered == 0
    assert report.failed == 0
    assert dispatches == []
    assert repository.get_job(job_id).status == "completed"


def test_scheduler_recovers_stale_job(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-1", "/input/audio.wav"))
    stale = datetime(2026, 9, 13, 14, 0, tzinfo=timezone.utc).isoformat()
    job_id = stable_job_id("rec-1", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-1", "ingest", "running", 1, updated_at=stale))
    scheduler = Scheduler(repository, FileExchange(tmp_path / "exchange"))

    report, dispatches = scheduler.run_once(["rec-1"], now=datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc))
    assert report.recovered == 1
    assert len(dispatches) == 1
    assert repository.get_job(job_id).attempt == 2
