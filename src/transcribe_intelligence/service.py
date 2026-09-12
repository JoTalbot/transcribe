"""Application service for idempotent ingestion and job status."""
from __future__ import annotations

from dataclasses import dataclass

from .job_store import ExecutionJob, stable_job_id
from .pipeline_contract import Stage
from .repository import Recording, Repository


@dataclass(frozen=True, slots=True)
class IngestResult:
    recording: Recording
    jobs: tuple[ExecutionJob, ...]


def ingest_recording(repository: Repository, recording_id: str, input_path: str) -> IngestResult:
    """Register a recording once and create the initial ingest job idempotently."""
    if not recording_id.strip():
        raise ValueError("recording_id must not be empty")
    if not input_path.strip():
        raise ValueError("input_path must not be empty")
    recording = repository.put_recording(Recording(recording_id, input_path))
    existing = repository.get_job(stable_job_id(recording_id, Stage.INGEST.value))
    if existing is None:
        existing = repository.put_job(
            ExecutionJob(
                stable_job_id(recording_id, Stage.INGEST.value),
                recording_id,
                Stage.INGEST.value,
            )
        )
    return IngestResult(recording, (existing,))


def status(
    repository: Repository, recording_id: str
) -> tuple[Recording | None, tuple[ExecutionJob, ...]]:
    """Return a deterministic recording status snapshot."""
    recording = repository.get_recording(recording_id)
    return recording, tuple(repository.list_jobs(recording_id))
