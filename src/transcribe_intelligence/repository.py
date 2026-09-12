"""Backend-neutral persistence contracts and an in-memory reference backend."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .job_store import ExecutionJob


@dataclass(frozen=True, slots=True)
class Recording:
    recording_id: str
    input_path: str
    status: str = "queued"


class Repository(Protocol):
    """Canonical persistence boundary for API and orchestration layers."""

    def put_recording(self, recording: Recording) -> Recording: ...

    def get_recording(self, recording_id: str) -> Recording | None: ...

    def put_job(self, job: ExecutionJob) -> ExecutionJob: ...

    def get_job(self, job_id: str) -> ExecutionJob | None: ...

    def list_jobs(self, recording_id: str) -> list[ExecutionJob]: ...

    def update_job(self, job: ExecutionJob) -> ExecutionJob: ...


class InMemoryRepository:
    """Deterministic reference implementation used by tests and local runs."""

    def __init__(self) -> None:
        self._recordings: dict[str, Recording] = {}
        self._jobs: dict[str, ExecutionJob] = {}

    def put_recording(self, recording: Recording) -> Recording:
        existing = self._recordings.get(recording.recording_id)
        if existing is not None:
            return existing
        self._recordings[recording.recording_id] = recording
        return recording

    def get_recording(self, recording_id: str) -> Recording | None:
        return self._recordings.get(recording_id)

    def put_job(self, job: ExecutionJob) -> ExecutionJob:
        existing = self._jobs.get(job.job_id)
        if existing is not None:
            return existing
        self._jobs[job.job_id] = job
        self._refresh_recording_status(job.recording_id)
        return job

    def get_job(self, job_id: str) -> ExecutionJob | None:
        return self._jobs.get(job_id)

    def update_job(self, job: ExecutionJob) -> ExecutionJob:
        if job.job_id not in self._jobs:
            raise KeyError(f"unknown job: {job.job_id}")
        self._jobs[job.job_id] = job
        self._refresh_recording_status(job.recording_id)
        return job

    def list_jobs(self, recording_id: str) -> list[ExecutionJob]:
        return sorted(
            (job for job in self._jobs.values() if job.recording_id == recording_id),
            key=lambda job: (job.stage, job.job_id),
        )

    def _refresh_recording_status(self, recording_id: str) -> None:
        recording = self._recordings.get(recording_id)
        if recording is None:
            return
        jobs = self.list_jobs(recording_id)
        if not jobs:
            return
        statuses = {job.status for job in jobs}
        if "failed" in statuses:
            status = "failed"
        elif statuses == {"completed"}:
            status = "completed"
        elif "running" in statuses:
            status = "running"
        else:
            status = "queued"
        self._recordings[recording_id] = Recording(
            recording.recording_id, recording.input_path, status
        )
