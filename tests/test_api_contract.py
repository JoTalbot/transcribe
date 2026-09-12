from transcribe_intelligence.api_contract import IngestRequest, JobPayload
from transcribe_intelligence.job_store import ExecutionJob


def test_ingest_request_rejects_empty_values() -> None:
    for value in ("", "   "):
        try:
            IngestRequest(value, "/audio.wav")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


def test_job_payload_serializes_execution_job() -> None:
    job = ExecutionJob("job-1", "rec-1", "ingest", status="completed", artifact_id="a")
    payload = JobPayload.from_job(job)
    assert payload.to_dict()["job_id"] == "job-1"
    assert payload.to_dict()["artifact_id"] == "a"
