"""Small HTTP-neutral API adapter over the application service layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .api_contract import ErrorPayload, IngestRequest, JobPayload, RecordingPayload
from .job_store import ExecutionJob
from .repository import Repository
from .service import ingest_recording, status


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """Transport-neutral response that an HTTP framework can serialize."""

    status_code: int
    body: dict[str, Any]


class ApiAdapter:
    """Expose stable recording/job routes without coupling the core to a web framework."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def handle(self, method: str, path: str, body: dict[str, Any] | None = None) -> ApiResponse:
        """Dispatch one request using HTTP method and normalized path."""
        normalized_method = method.upper().strip()
        normalized_path = "/" + path.strip("/") if path.strip("/") else "/"
        try:
            if normalized_method == "GET" and normalized_path == "/health":
                return ApiResponse(200, {"status": "ok"})
            if normalized_method == "GET" and normalized_path == "/ready":
                return ApiResponse(200, {"status": "ready"})
            if normalized_method == "POST" and normalized_path == "/recordings":
                return self._ingest(body)
            if normalized_method == "GET" and normalized_path.startswith("/recordings/"):
                recording_id = normalized_path.removeprefix("/recordings/")
                return self._recording(recording_id)
            if normalized_method == "GET" and normalized_path.startswith("/jobs/"):
                job_id = normalized_path.removeprefix("/jobs/")
                return self._job(job_id)
            return ApiResponse(404, ErrorPayload("route not found", "not_found").to_dict())
        except (KeyError, TypeError, ValueError) as exc:
            return ApiResponse(400, ErrorPayload(str(exc), "invalid_request").to_dict())

    def _ingest(self, body: dict[str, Any] | None) -> ApiResponse:
        if body is None:
            raise ValueError("request body is required")
        request = IngestRequest(**body)
        result = ingest_recording(self.repository, request.recording_id, request.input_path)
        payload = RecordingPayload.from_snapshot(result.recording, result.jobs)
        return ApiResponse(201, payload.to_dict())

    def _recording(self, recording_id: str) -> ApiResponse:
        if not recording_id:
            return ApiResponse(404, ErrorPayload("recording not found", "not_found").to_dict())
        recording, jobs = status(self.repository, recording_id)
        if recording is None:
            return ApiResponse(404, ErrorPayload("recording not found", "not_found").to_dict())
        return ApiResponse(200, RecordingPayload.from_snapshot(recording, jobs).to_dict())

    def _job(self, job_id: str) -> ApiResponse:
        if not job_id:
            return ApiResponse(404, ErrorPayload("job not found", "not_found").to_dict())
        job: ExecutionJob | None = self.repository.get_job(job_id)
        if job is None:
            return ApiResponse(404, ErrorPayload("job not found", "not_found").to_dict())
        return ApiResponse(200, JobPayload.from_job(job).to_dict())
