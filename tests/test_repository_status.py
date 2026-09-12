from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import InMemoryRepository, Recording


def test_recording_status_follows_job_state() -> None:
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-1", "/tmp/audio.wav"))
    repository.put_job(ExecutionJob("job-1", "rec-1", "ingest", status="queued"))
    assert repository.get_recording("rec-1").status == "queued"

    repository.update_job(ExecutionJob("job-1", "rec-1", "ingest", status="running"))
    assert repository.get_recording("rec-1").status == "running"

    repository.update_job(
        ExecutionJob("job-1", "rec-1", "ingest", status="completed", artifact_id="a1")
    )
    assert repository.get_recording("rec-1").status == "completed"


def test_failed_job_has_priority_over_other_states() -> None:
    repository = InMemoryRepository()
    repository.put_recording(Recording("rec-1", "/tmp/audio.wav"))
    repository.put_job(ExecutionJob("job-1", "rec-1", "ingest", status="completed", artifact_id="a1"))
    repository.put_job(ExecutionJob("job-2", "rec-1", "asr", status="failed", error="boom"))

    assert repository.get_recording("rec-1").status == "failed"
