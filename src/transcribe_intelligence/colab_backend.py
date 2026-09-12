"""Colab execution adapter boundary."""
from __future__ import annotations

from dataclasses import dataclass
import time

from .exchange import FileExchange, JobEnvelope, ResultEnvelope
from .execution import ExecutionResult
from .job_store import ExecutionJob


@dataclass(frozen=True, slots=True)
class ColabJobRequest:
    job_id: str
    recording_id: str
    stage: str
    input_artifact_id: str | None = None


class ColabExecutionBackend:
    """Transport-neutral adapter for a Colab GPU worker.

    Authentication and browser controls remain outside orchestration. A submitter
    may use a local Drive mount, an API, or another queue transport.
    """

    name = "colab"

    def __init__(self, submit):
        self._submit = submit

    def execute(self, job: ExecutionJob) -> ExecutionResult:
        request = ColabJobRequest(job.job_id, job.recording_id, job.stage, job.artifact_id)
        result = self._submit(request)
        if not isinstance(result, ExecutionResult):
            raise TypeError("Colab submitter must return ExecutionResult")
        if result.job_id != job.job_id:
            raise RuntimeError("Colab worker returned a different job_id")
        return result


class FileColabSubmitter:
    """Exchange-backed submitter for a Google Drive-mounted Colab worker."""

    def __init__(self, exchange: FileExchange, *, poll_seconds: float = 2.0, timeout_seconds: float = 900.0):
        if poll_seconds <= 0 or timeout_seconds <= 0:
            raise ValueError("poll_seconds and timeout_seconds must be positive")
        self.exchange = exchange
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def __call__(self, request: ColabJobRequest) -> ExecutionResult:
        self.exchange.put_request(JobEnvelope(request.job_id, request.recording_id, request.stage, request.input_artifact_id))
        deadline = time.monotonic() + self.timeout_seconds
        result_path = self.exchange.results / f"{request.job_id}.json"
        while time.monotonic() < deadline:
            if result_path.is_file():
                result: ResultEnvelope = self.exchange.get_result(request.job_id)
                return ExecutionResult(request.job_id, result.status, result.artifact_id, result.error)
            time.sleep(self.poll_seconds)
        return ExecutionResult(request.job_id, "failed", error="Colab worker result timeout")
