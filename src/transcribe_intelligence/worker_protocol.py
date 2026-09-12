"""Worker protocol for claiming, completing, and retrying queued jobs."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .job_store import ExecutionJob, JobStore, now_iso


class JobConflict(RuntimeError):
    """Raised when a worker attempts an invalid job transition."""


def _expired(job: ExecutionJob, lease_seconds: int) -> bool:
    if job.status != "running" or not job.updated_at:
        return False
    expires = datetime.fromisoformat(job.updated_at.replace("Z", "+00:00")) + timedelta(seconds=lease_seconds)
    return expires <= datetime.now(timezone.utc)


def claim(store: JobStore, job_id: str, worker: str, lease_seconds: int = 900) -> ExecutionJob:
    """Claim a queued job, or reclaim an expired lease."""
    if not worker.strip():
        raise ValueError("worker must not be empty")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    job = store.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status == "completed":
        return job
    if job.status == "running" and not _expired(job, lease_seconds):
        raise JobConflict(f"job {job_id} is leased by {job.worker}")
    return store.upsert(replace(job, status="running", attempt=job.attempt + 1, worker=worker, error=None, updated_at=now_iso()))


def complete(store: JobStore, job_id: str, worker: str, artifact_id: str) -> ExecutionJob:
    """Complete a job only when owned by the current worker."""
    if not artifact_id.strip():
        raise ValueError("artifact_id must not be empty")
    job = store.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status == "completed":
        return job
    if job.status != "running" or job.worker != worker:
        raise JobConflict(f"worker {worker} does not own job {job_id}")
    return store.upsert(replace(job, status="completed", artifact_id=artifact_id, error=None, updated_at=now_iso()))


def fail(store: JobStore, job_id: str, worker: str, error: str) -> ExecutionJob:
    """Return a worker-owned job to the queue for retry."""
    if not error.strip():
        raise ValueError("error must not be empty")
    job = store.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status != "running" or job.worker != worker:
        raise JobConflict(f"worker {worker} does not own job {job_id}")
    return store.upsert(replace(job, status="queued", worker=None, error=error, updated_at=now_iso()))
