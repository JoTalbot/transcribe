from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import InMemoryRepository


def test_update_job_replaces_existing_state() -> None:
    repository = InMemoryRepository()
    original = ExecutionJob("job-1", "rec-1", "ingest")
    updated = ExecutionJob("job-1", "rec-1", "ingest", status="running", attempt=1)
    repository.put_job(original)

    assert repository.update_job(updated) == updated
    assert repository.get_job("job-1") == updated


def test_update_unknown_job_is_rejected() -> None:
    repository = InMemoryRepository()
    try:
        repository.update_job(ExecutionJob("missing", "rec-1", "ingest"))
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected KeyError")
