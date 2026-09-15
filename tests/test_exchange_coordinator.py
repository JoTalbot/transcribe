from pathlib import Path

import pytest

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


def test_publish_failure_releases_claim_for_immediate_retry(tmp_path: Path):
    class FailingExchange(FileExchange):
        def put_request(self, request):
            raise OSError("exchange unavailable")

    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-publish", "/audio/publish.wav"))
    job = ExecutionJob(stable_job_id("rec-publish", "ingest"), "rec-publish", "ingest")
    repository.put_job(job)

    coordinator = ExchangeCoordinator(repository, FailingExchange(tmp_path / "exchange"))
    assert coordinator.dispatch_ready("rec-publish", worker="colab") == []

    stored = repository.get_job(job.job_id)
    assert stored is not None
    assert stored.status == "retry"
    assert stored.attempt == 1
    assert stored.worker is None
    assert stored.lease_id is None
    assert stored.lease_until is None
    assert stored.error == "exchange publish failed: exchange unavailable"


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


def test_apply_results_quarantines_malformed_result_and_keeps_valid_result(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-4", "/audio/four.wav"))
    valid_id = stable_job_id("rec-4", "ingest")
    repository.put_job(ExecutionJob(valid_id, "rec-4", "ingest", "running", attempt=1))

    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope(valid_id, "completed", artifact_id="rec-4:ingest:json"))
    broken = exchange.results / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    changed = ExchangeCoordinator(repository, exchange).apply_results()

    assert changed == 1
    assert repository.get_job(valid_id).status == "completed"
    assert not broken.exists()
    assert (exchange.results / "quarantine" / "broken.json").exists()
    assert (exchange.results / "quarantine" / "broken.json.error").read_text(encoding="utf-8").strip()


def test_apply_results_quarantines_unknown_job_without_blocking_known_job(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-5", "/audio/five.wav"))
    known_id = stable_job_id("rec-5", "ingest")
    repository.put_job(ExecutionJob(known_id, "rec-5", "ingest", "running", attempt=1))

    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope("unknown-job", "completed", artifact_id="orphan:json"))
    exchange.put_result(ResultEnvelope(known_id, "completed", artifact_id="rec-5:ingest:json"))

    changed = ExchangeCoordinator(repository, exchange).apply_results()

    assert changed == 1
    assert repository.get_job(known_id).status == "completed"
    assert (exchange.results / "quarantine" / "unknown-job.json").exists()
    assert not (exchange.results / "unknown-job.json").exists()


def test_apply_results_quarantines_conflicting_result(tmp_path: Path):
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-6", "/audio/six.wav"))
    job_id = stable_job_id("rec-6", "ingest")
    repository.put_job(ExecutionJob(job_id, "rec-6", "ingest", "completed", artifact_id="artifact-a"))

    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope(job_id, "completed", artifact_id="artifact-b"))

    changed = ExchangeCoordinator(repository, exchange).apply_results()

    assert changed == 0
    assert repository.get_job(job_id).artifact_id == "artifact-a"
    assert (exchange.results / "quarantine" / f"{job_id}.json").exists()


def test_apply_results_propagates_repository_runtime_error_and_keeps_result(tmp_path: Path):
    class FailingRepository(InMemoryRepository):
        def complete(self, job_id: str, worker: str, lease_id: str, artifact_id: str):
            raise RuntimeError("database temporarily unavailable")

    repository = FailingRepository()
    repository.put_recording(Recording("rec-runtime", "/audio/runtime.wav"))
    job_id = stable_job_id("rec-runtime", "ingest")
    repository.put_job(
        ExecutionJob(
            job_id,
            "rec-runtime",
            "ingest",
            "running",
            attempt=1,
            worker="colab",
            lease_id="lease-runtime",
        )
    )

    exchange = FileExchange(tmp_path / "exchange")
    result_path = exchange.put_result(
        ResultEnvelope(
            job_id,
            "completed",
            artifact_id="rec-runtime:ingest:json",
            worker="colab",
            lease_id="lease-runtime",
        )
    )

    with pytest.raises(RuntimeError, match="database temporarily unavailable"):
        ExchangeCoordinator(repository, exchange).apply_results()

    assert result_path.exists()
    assert not (exchange.results / "quarantine" / result_path.name).exists()


def test_ready_jobs_is_deterministic_and_ignores_running_jobs():
    jobs = [
        ExecutionJob("b", "rec", "normalize"),
        ExecutionJob("a", "rec", "ingest"),
        ExecutionJob("c", "rec", "asr", "running"),
    ]
    ready = ready_jobs(jobs)
    assert [job.job_id for job in ready] == ["a"]
