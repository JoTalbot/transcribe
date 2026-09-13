from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator, ready_jobs
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_dispatches_first_stage_and_marks_running(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-1", "/audio/one.wav"))
    job = ExecutionJob(stable_job_id("rec-1", "ingest"), "rec-1", "ingest")
    repository.put_job(job)

    exchange = FileExchange(tmp_path / "exchange")
    dispatches = ExchangeCoordinator(repository, exchange).dispatch_ready("rec-1", worker="colab-1")

    assert [item.job_id for item in dispatches] == [job.job_id]
    stored = repository.get_job(job.job_id)
    assert stored is not None
    assert stored.status == "running"
    assert stored.attempt == 1
    assert stored.worker == "colab-1"
    assert exchange.get_request(job.job_id).input_path == "/audio/one.wav"


def test_completed_dependency_dispatches_next_stage_with_artifact(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-2", "/audio/two.wav"))
    ingest_id = stable_job_id("rec-2", "ingest")
    normalize_id = stable_job_id("rec-2", "normalize")
    repository.put_job(ExecutionJob(ingest_id, "rec-2", "ingest", "completed", artifact_id="rec-2:ingest:json"))
    repository.put_job(ExecutionJob(normalize_id, "rec-2", "normalize"))

    exchange = FileExchange(tmp_path / "exchange")
    dispatches = ExchangeCoordinator(repository, exchange).dispatch_ready("rec-2")

    assert [item.job_id for item in dispatches] == [normalize_id]
    request = exchange.get_request(normalize_id)
    assert request.input_artifact_id == "rec-2:ingest:json"
    assert request.input_path is None


def test_cycle_applies_result_then_dispatches_newly_ready_job(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-3", "/audio/three.wav"))
    ingest_id = stable_job_id("rec-3", "ingest")
    normalize_id = stable_job_id("rec-3", "normalize")
    repository.put_job(ExecutionJob(ingest_id, "rec-3", "ingest", "running", attempt=1, worker="colab"))
    repository.put_job(ExecutionJob(normalize_id, "rec-3", "normalize"))

    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope(ingest_id, "completed", artifact_id="rec-3:ingest:json"))

    dispatches, changed = ExchangeCoordinator(repository, exchange).cycle("rec-3")

    assert changed == 1
    assert [item.job_id for item in dispatches] == [normalize_id]
    assert repository.get_job(ingest_id).status == "completed"
    assert repository.get_job(normalize_id).status == "running"


def test_ready_jobs_is_deterministic_and_ignores_running_jobs():
    jobs = [
        ExecutionJob("b", "rec", "normalize"),
        ExecutionJob("a", "rec", "ingest"),
        ExecutionJob("c", "rec", "asr", "running"),
    ]
    ready = ready_jobs(jobs)
    assert [job.job_id for job in ready] == ["a"]
