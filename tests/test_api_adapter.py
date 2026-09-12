from transcribe_intelligence.api_adapter import ApiAdapter
from transcribe_intelligence.repository import InMemoryRepository


def make_api() -> ApiAdapter:
    return ApiAdapter(InMemoryRepository())


def test_health_and_readiness() -> None:
    api = make_api()
    assert api.handle("GET", "/health").body == {"status": "ok"}
    assert api.handle("GET", "/ready").body == {"status": "ready"}


def test_ingest_and_recording_status() -> None:
    api = make_api()
    response = api.handle(
        "POST",
        "/recordings",
        {"recording_id": "r1", "input_path": "/audio/r1.wav"},
    )
    assert response.status_code == 201
    assert response.body["recording_id"] == "r1"
    assert response.body["jobs"][0]["job_id"] == "r1:ingest"

    status = api.handle("GET", "/recordings/r1")
    assert status.status_code == 200
    assert status.body["jobs"][0]["status"] == "queued"


def test_ingest_is_idempotent() -> None:
    api = make_api()
    payload = {"recording_id": "r1", "input_path": "/audio/r1.wav"}
    first = api.handle("POST", "/recordings", payload)
    second = api.handle("POST", "/recordings", payload)
    assert first.status_code == second.status_code == 201
    assert first.body == second.body


def test_job_lookup_and_not_found() -> None:
    api = make_api()
    api.handle("POST", "/recordings", {"recording_id": "r1", "input_path": "/audio/r1.wav"})
    job = api.handle("GET", "/jobs/r1:ingest")
    assert job.status_code == 200
    assert job.body["recording_id"] == "r1"

    missing = api.handle("GET", "/jobs/missing")
    assert missing.status_code == 404
    assert missing.body["code"] == "not_found"


def test_invalid_request_and_unknown_route() -> None:
    api = make_api()
    invalid = api.handle("POST", "/recordings", {"recording_id": "", "input_path": "x"})
    assert invalid.status_code == 400
    assert invalid.body["code"] == "invalid_request"

    missing = api.handle("GET", "/does-not-exist")
    assert missing.status_code == 404
    assert missing.body["code"] == "not_found"
