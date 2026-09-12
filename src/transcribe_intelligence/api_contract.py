"""Framework-neutral API contracts for recording ingestion and job status."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .job_store import ExecutionJob
from .repository import Recording


@dataclass(frozen=True, slots=True)
class IngestRequest:
    recording_id: str
    input_path: str

    def __post_init__(self) -> None:
        if not self.recording_id.strip():
            raise ValueError("recording_id must not be empty")
        if not self.input_path.strip():
            raise ValueError("input_path must not be empty")


@dataclass(frozen=True, slots=True)
class JobPayload:
    job_id: str
    recording_id: str
    stage: str
    status: str
    attempt: int
    artifact_id: str | None
    worker: str | None
    error: str | None
    updated_at: str | None

    @classmethod
    def from_job(cls, job: ExecutionJob) -> "JobPayload":
        return cls(**asdict(job))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RecordingPayload:
    recording_id: str
    input_path: str
    status: str
    jobs: tuple[JobPayload, ...]

    @classmethod
    def from_snapshot(cls, recording: Recording, jobs: tuple[ExecutionJob, ...]) -> "RecordingPayload":
        return cls(recording.recording_id, recording.input_path, recording.status, tuple(JobPayload.from_job(job) for job in jobs))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ErrorPayload:
    error: str
    code: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
