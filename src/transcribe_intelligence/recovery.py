"""Deterministic recovery policy for resumable execution jobs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .job_store import ExecutionJob


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    """Bound retries and reclaim workers that stopped heartbeating."""

    max_attempts: int = 3
    stale_after_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")


def recover_job(job: ExecutionJob, policy: RecoveryPolicy, now: datetime | None = None) -> ExecutionJob:
    """Convert a stale running job to retry, or permanently fail it."""
    if job.status != "running":
        return job
    current = now or datetime.now(timezone.utc)
    if not job.updated_at:
        return job
    updated = datetime.fromisoformat(job.updated_at)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if current - updated < timedelta(seconds=policy.stale_after_seconds):
        return job
    if job.attempt >= policy.max_attempts:
        return ExecutionJob(job.job_id, job.recording_id, job.stage, "failed", job.attempt, job.artifact_id, job.worker, "worker heartbeat stale; retry limit reached", current.isoformat())
    return ExecutionJob(job.job_id, job.recording_id, job.stage, "retry", job.attempt, job.artifact_id, job.worker, "worker heartbeat stale; scheduled for retry", current.isoformat())
