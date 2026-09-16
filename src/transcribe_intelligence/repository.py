"""Backend-neutral persistence contracts and an in-memory reference backend."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid
from typing import Protocol

from .job_store import ExecutionJob, now_iso


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


class LeaseRepository(Protocol):
    """Optional transactional ownership API used by concurrent schedulers."""

    def claim_job(self, job_id: str, worker: str, lease_seconds: int = 900) -> ExecutionJob | None: ...
    def heartbeat(self, job_id: str, worker: str, lease_id: str, lease_seconds: int = 900) -> ExecutionJob: ...
    def complete(self, job_id: str, worker: str, lease_id: str, artifact_id: str) -> ExecutionJob: ...
    def fail(self, job_id: str, worker: str, lease_id: str, error: str) -> ExecutionJob: ...
    def release(self, job_id: str, worker: str, lease_id: str, error: str) -> ExecutionJob: ...
    def recover_stale(self, max_attempts: int = 3) -> tuple[int, int]: ...


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
        return sorted((job for job in self._jobs.values() if job.recording_id == recording_id), key=lambda job: (job.stage, job.job_id))

    def claim_job(self, job_id: str, worker: str, lease_seconds: int = 900) -> ExecutionJob | None:
        """Atomically model the ownership transition used by the SQL repository."""
        if not job_id or not worker or lease_seconds <= 0:
            raise ValueError("job_id, worker and positive lease_seconds are required")
        job = self._jobs.get(job_id)
        if job is None or job.status not in {"queued", "retry"}:
            return None
        now = datetime.now(timezone.utc)
        claimed = ExecutionJob(
            job.job_id,
            job.recording_id,
            job.stage,
            "running",
            job.attempt + 1,
            job.artifact_id,
            worker,
            None,
            now.isoformat(),
            uuid.uuid4().hex,
            (now + timedelta(seconds=lease_seconds)).isoformat(),
            now.isoformat(),
        )
        self._jobs[job_id] = claimed
        self._refresh_recording_status(job.recording_id)
        return claimed

    def _owned_live(self, job_id: str, worker: str, lease_id: str) -> ExecutionJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        if job.status != "running" or job.worker != worker or job.lease_id != lease_id:
            raise RuntimeError(f"job lease rejected: {job_id}")
        if not job.lease_until:
            # Preserve compatibility with legacy in-memory fixtures that predate
            # persisted lease expiry. Production PostgreSQL rows always carry it.
            return job
        try:
            lease_until = datetime.fromisoformat(job.lease_until)
        except ValueError as exc:
            raise RuntimeError(f"job lease rejected: {job_id}") from exc
        if lease_until.tzinfo is None:
            lease_until = lease_until.replace(tzinfo=timezone.utc)
        if lease_until <= datetime.now(timezone.utc):
            raise RuntimeError(f"job lease rejected: {job_id}")
        return job

    def heartbeat(self, job_id: str, worker: str, lease_id: str, lease_seconds: int = 900) -> ExecutionJob:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        job = self._owned_live(job_id, worker, lease_id)
        now = datetime.now(timezone.utc)
        refreshed = ExecutionJob(
            job.job_id, job.recording_id, job.stage, job.status, job.attempt,
            job.artifact_id, job.worker, job.error, now.isoformat(), job.lease_id,
            (now + timedelta(seconds=lease_seconds)).isoformat(), now.isoformat(),
        )
        return self.update_job(refreshed)

    def complete(self, job_id: str, worker: str, lease_id: str, artifact_id: str) -> ExecutionJob:
        if not artifact_id:
            raise ValueError("artifact_id is required")
        job = self._owned_live(job_id, worker, lease_id)
        completed = ExecutionJob(
            job.job_id, job.recording_id, job.stage, "completed", job.attempt,
            artifact_id, worker, None, now_iso(), None, None, job.heartbeat_at,
        )
        return self.update_job(completed)

    def fail(self, job_id: str, worker: str, lease_id: str, error: str) -> ExecutionJob:
        job = self._owned_live(job_id, worker, lease_id)
        failed = ExecutionJob(
            job.job_id, job.recording_id, job.stage, "failed", job.attempt,
            job.artifact_id, worker, error or "worker failed", now_iso(), None, None, job.heartbeat_at,
        )
        return self.update_job(failed)

    def release(self, job_id: str, worker: str, lease_id: str, error: str) -> ExecutionJob:
        job = self._owned_live(job_id, worker, lease_id)
        released = ExecutionJob(
            job.job_id, job.recording_id, job.stage, "retry", job.attempt,
            job.artifact_id, None, error or "worker released job", now_iso(), None, None, job.heartbeat_at,
        )
        return self.update_job(released)

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
        self._recordings[recording_id] = Recording(recording.recording_id, recording.input_path, status)
