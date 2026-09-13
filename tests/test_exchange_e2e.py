from pathlib import Path

from transcribe_intelligence.exchange import FileExchange, JobEnvelope, ResultEnvelope
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.repository import InMemoryRepository, Recording
from transcribe_intelligence.result_service import apply_result


def test_exchange_result_is_persisted_idempotently(tmp_path: Path):
    repository = InMemoryRepository()
    recording_id = "rec-e2e"
    job_id = stable_job_id(recording_id, "asr")
    repository.put_recording(Recording(recording_id, "/input/audio.wav"))
    repository.put_job(ExecutionJob(job_id, recording_id, "asr"))

    exchange = FileExchange(tmp_path / "exchange")
    request = JobEnvelope(job_id, recording_id, "asr", input_path="/input/audio.wav")
    exchange.put_request(request)
    assert exchange.get_request(job_id) == request

    result = ResultEnvelope(job_id, "completed", artifact_id="rec-e2e:asr:json")
    exchange.put_result(result)
    assert exchange.get_result(job_id) == result

    assert apply_result(repository, exchange.get_result(job_id)) is True
    assert apply_result(repository, exchange.get_result(job_id)) is False
    stored = repository.get_job(job_id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.artifact_id == result.artifact_id
    assert repository.get_recording(recording_id).status == "completed"


def test_exchange_failed_result_reaches_persisted_job(tmp_path: Path):
    repository = InMemoryRepository()
    recording_id = "rec-failed"
    job_id = stable_job_id(recording_id, "asr")
    repository.put_recording(Recording(recording_id, "/input/audio.wav"))
    repository.put_job(ExecutionJob(job_id, recording_id, "asr"))

    exchange = FileExchange(tmp_path / "exchange")
    result = ResultEnvelope(job_id, "failed", error="GPU worker unavailable")
    exchange.put_result(result)

    assert apply_result(repository, exchange.get_result(job_id)) is True
    stored = repository.get_job(job_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error == result.error
    assert repository.get_recording(recording_id).status == "failed"
