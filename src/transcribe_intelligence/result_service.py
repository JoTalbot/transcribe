"""Idempotent application of worker result envelopes to persisted jobs."""
from __future__ import annotations

from .exchange import ResultEnvelope
from .job_store import now_iso
from .repository import Repository


def apply_result(repository: Repository, result: ResultEnvelope) -> bool:
    """Apply a worker result and return whether it changed persisted state.

    Replaying the same result is a no-op. A conflicting result for a completed
    job is rejected instead of silently corrupting the execution history.
    """
    job = repository.get_job(result.job_id)
    if job is None:
        raise KeyError(f"unknown job: {result.job_id}")
    if result.status == "completed" and not result.artifact_id:
        raise ValueError("completed result requires artifact_id")
    if result.status not in {"completed", "failed"}:
        raise ValueError("result status must be completed or failed")

    if job.status == result.status:
        if job.artifact_id == result.artifact_id and job.error == result.error:
            return False
        raise ValueError(f"conflicting result for job: {result.job_id}")
    if job.status == "completed":
        raise ValueError(f"cannot replace completed job: {result.job_id}")

    updated = type(job)(
        job.job_id,
        job.recording_id,
        job.stage,
        result.status,
        job.attempt,
        result.artifact_id,
        job.worker,
        result.error,
        now_iso(),
    )
    repository.update_job(updated)
    return True
