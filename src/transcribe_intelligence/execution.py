"""Backend-neutral execution contract and dispatcher for pipeline workers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .job_store import ExecutionJob, JobStore
from .repository import LeaseRepository
from .worker_protocol import claim, complete, fail


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    job_id: str
    status: str
    artifact_id: str | None = None
    error: str | None = None


class ExecutionBackend(Protocol):
    """Minimal contract implemented by local, Colab, or future GPU backends."""

    name: str

    def execute(self, job: ExecutionJob) -> ExecutionResult:
        """Execute one claimed job."""


class DryRunBackend:
    """Deterministic backend used by orchestration tests without inference."""

    name = "dry-run"

    def execute(self, job: ExecutionJob) -> ExecutionResult:
        return ExecutionResult(job.job_id, "completed", artifact_id=f"dry-run:{job.job_id}")


def dispatch_one(store: JobStore, job_id: str, backend: ExecutionBackend, worker: str, lease_seconds: int = 900) -> ExecutionJob:
    """Legacy file-store dispatcher with worker ownership checks."""
    job = claim(store, job_id, worker, lease_seconds)
    if job.status == "completed":
        return job
    try:
        result = backend.execute(job)
        if result.job_id != job.job_id:
            raise RuntimeError("backend returned a different job_id")
        if result.status == "completed" and result.artifact_id:
            return complete(store, job_id, worker, result.artifact_id)
        error = result.error or "backend did not complete the job"
        return fail(store, job_id, worker, error)
    except Exception as exc:
        return fail(store, job_id, worker, str(exc))


def dispatch_one_repository(
    repository: LeaseRepository,
    job_id: str,
    backend: ExecutionBackend,
    worker: str,
    lease_seconds: int = 900,
) -> ExecutionJob:
    """Claim, execute, and finalize one job through the transactional lease API.

    This is the production path for PostgreSQL-backed orchestration. The lease
    identity returned by claim_job is retained through completion/failure, so a
    stale worker cannot finalize a job after another worker has reclaimed it.
    """
    job = repository.claim_job(job_id, worker, lease_seconds)
    if job is None:
        current = repository.get_job(job_id)
        if current is None:
            raise KeyError(job_id)
        if current.status == "completed":
            return current
        raise RuntimeError(f"job {job_id} could not be claimed")
    if not job.lease_id:
        raise RuntimeError(f"job {job_id} was claimed without a lease_id")

    try:
        result = backend.execute(job)
    except Exception as exc:
        try:
            return repository.fail(job.job_id, worker, job.lease_id, str(exc))
        except RuntimeError:
            # The lease may have expired while the backend was running. Do not
            # overwrite a newer worker's state; the scheduler will recover it.
            raise exc

    if result.job_id != job.job_id:
        error = "backend returned a different job_id"
        try:
            repository.fail(job.job_id, worker, job.lease_id, error)
        except RuntimeError:
            # A lease may have been reclaimed while the invalid result was in flight.
            pass
        raise RuntimeError(error)

    if result.status == "completed" and result.artifact_id:
        return repository.complete(job.job_id, worker, job.lease_id, result.artifact_id)
    return repository.fail(job.job_id, worker, job.lease_id, result.error or "backend did not complete the job")
