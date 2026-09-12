from transcribe_intelligence.exchange import ResultEnvelope
from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import InMemoryRepository
from transcribe_intelligence.result_service import apply_result


def repository_with_job() -> InMemoryRepository:
    repository = InMemoryRepository()
    repository.put_job(ExecutionJob("job-1", "rec-1", "ingest", attempt=1))
    return repository


def test_completed_result_is_applied_once() -> None:
    repository = repository_with_job()
    result = ResultEnvelope("job-1", "completed", artifact_id="artifact-1")

    assert apply_result(repository, result) is True
    assert apply_result(repository, result) is False
    assert repository.get_job("job-1").status == "completed"
    assert repository.get_job("job-1").artifact_id == "artifact-1"


def test_failed_result_is_applied() -> None:
    repository = repository_with_job()
    result = ResultEnvelope("job-1", "failed", error="worker error")

    assert apply_result(repository, result) is True
    job = repository.get_job("job-1")
    assert job.status == "failed"
    assert job.error == "worker error"


def test_completed_result_requires_artifact() -> None:
    repository = repository_with_job()

    try:
        apply_result(repository, ResultEnvelope("job-1", "completed"))
    except ValueError as exc:
        assert "artifact_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_conflicting_replay_is_rejected() -> None:
    repository = repository_with_job()
    apply_result(repository, ResultEnvelope("job-1", "completed", artifact_id="a"))

    try:
        apply_result(repository, ResultEnvelope("job-1", "completed", artifact_id="b"))
    except ValueError as exc:
        assert "conflicting" in str(exc)
    else:
        raise AssertionError("expected ValueError")
