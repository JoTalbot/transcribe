"""Application service connecting worker exchange results to persistence."""
from __future__ import annotations

from dataclasses import dataclass

from .exchange import FileExchange
from .repository import Recording, Repository
from .result_service import apply_result


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    job_id: str
    status: str
    changed: bool


def reconcile_result(repository: Repository, exchange: FileExchange, job_id: str) -> ReconcileResult:
    """Apply one worker result idempotently and refresh aggregate recording status."""
    result = exchange.get_result(job_id)
    changed = apply_result(repository, result)
    job = repository.get_job(job_id)
    if job is None:
        raise KeyError(f"unknown job: {job_id}")
    refresh = getattr(repository, "refresh_recording_status", None)
    if callable(refresh):
        refresh(job.recording_id)
    return ReconcileResult(job_id, result.status, changed)


def reconcile_results(
    repository: Repository,
    exchange: FileExchange,
    job_ids: list[str] | None = None,
) -> list[ReconcileResult]:
    """Reconcile available result envelopes in deterministic job-id order."""
    ids = job_ids if job_ids is not None else [path.stem for path in exchange.results.glob("*.json")]
    return [reconcile_result(repository, exchange, job_id) for job_id in sorted(set(ids))]


def recording_status(repository: Repository, recording_id: str) -> Recording | None:
    """Return persisted aggregate status after refreshing SQL-backed repositories."""
    refresh = getattr(repository, "refresh_recording_status", None)
    if callable(refresh):
        return refresh(recording_id)
    return repository.get_recording(recording_id)
