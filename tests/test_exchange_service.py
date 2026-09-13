from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_service import reconcile_result, reconcile_results
from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import InMemoryRepository, Recording
from transcribe_intelligence.service import ingest_recording


def _repository() -> InMemoryRepository:
    repository = InMemoryRepository()
    ingest_recording(repository, "rec-1", "/audio/rec-1.wav")
    repository.put_job(ExecutionJob("rec-1:normalize", "rec-1", "normalize"))
    return repository


def test_reconcile_result_updates_job_and_aggregate_status(tmp_path: Path):
    repository = _repository()
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope("rec-1:ingest", "completed", "rec-1:ingest:json"))

    result = reconcile_result(repository, exchange, "rec-1:ingest")

    assert result.changed is True
    assert repository.get_job("rec-1:ingest").status == "completed"
    assert repository.get_recording("rec-1").status == "queued"


def test_reconcile_is_idempotent(tmp_path: Path):
    repository = _repository()
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope("rec-1:ingest", "completed", "artifact-1"))

    first = reconcile_result(repository, exchange, "rec-1:ingest")
    second = reconcile_result(repository, exchange, "rec-1:ingest")

    assert first.changed is True
    assert second.changed is False
    assert repository.get_job("rec-1:ingest").artifact_id == "artifact-1"


def test_reconcile_results_is_sorted_and_deduplicated(tmp_path: Path):
    repository = _repository()
    repository.put_job(ExecutionJob("rec-1:normalize", "rec-1", "normalize"))
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope("rec-1:normalize", "completed", "artifact-n"))
    exchange.put_result(ResultEnvelope("rec-1:ingest", "completed", "artifact-i"))

    results = reconcile_results(
        repository,
        exchange,
        ["rec-1:normalize", "rec-1:ingest", "rec-1:normalize"],
    )

    assert [item.job_id for item in results] == ["rec-1:ingest", "rec-1:normalize"]
    assert all(item.changed for item in results)


def test_recording_status_helper_uses_repository_state(tmp_path: Path):
    repository = _repository()
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_result(ResultEnvelope("rec-1:ingest", "failed", error="boom"))
    reconcile_result(repository, exchange, "rec-1:ingest")

    from transcribe_intelligence.exchange_service import recording_status

    assert recording_status(repository, "rec-1") == Recording("rec-1", "/audio/rec-1.wav", "failed")
