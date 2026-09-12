from transcribe_intelligence.repository import InMemoryRepository
from transcribe_intelligence.service import ingest_recording, status


def test_ingest_is_idempotent():
    repository = InMemoryRepository()
    first = ingest_recording(repository, "r1", "/audio/a.wav")
    second = ingest_recording(repository, "r1", "/audio/a.wav")
    assert first.recording == second.recording
    assert first.jobs == second.jobs
    assert len(repository.list_jobs("r1")) == 1


def test_status_returns_recording_and_jobs():
    repository = InMemoryRepository()
    ingest_recording(repository, "r1", "/audio/a.wav")
    recording, jobs = status(repository, "r1")
    assert recording is not None
    assert recording.recording_id == "r1"
    assert [job.stage for job in jobs] == ["ingest"]


def test_status_for_unknown_recording_is_empty():
    recording, jobs = status(InMemoryRepository(), "missing")
    assert recording is None
    assert jobs == ()
