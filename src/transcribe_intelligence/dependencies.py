"""Stage dependency and readiness rules."""
from __future__ import annotations

from .job_store import ExecutionJob, JobStore
from .pipeline_contract import Stage

DEPENDENCIES: dict[str, tuple[str, ...]] = {
    Stage.INGEST: (),
    Stage.NORMALIZE: (Stage.INGEST,),
    Stage.ASR: (Stage.NORMALIZE,),
    Stage.DIARIZATION: (Stage.ASR,),
    Stage.EMBEDDINGS: (Stage.DIARIZATION,),
    Stage.TEXT_ANALYSIS: (Stage.ASR,),
    Stage.TOPICS: (Stage.TEXT_ANALYSIS,),
    Stage.LINKING: (Stage.TOPICS, Stage.EMBEDDINGS),
    Stage.GRAPH: (Stage.LINKING,),
}


def dependencies(stage: str) -> tuple[str, ...]:
    """Return the stages that must complete for the given stage."""
    return DEPENDENCIES.get(stage, ())


def is_ready(store: JobStore, job: ExecutionJob) -> bool:
    """A queued job is ready only when all same-recording prerequisites completed."""
    if job.status != "queued":
        return False
    return all(
        (dependency := store.get(f"{job.recording_id}:{stage}")) is not None
        and dependency.status == "completed"
        and bool(dependency.artifact_id)
        for stage in dependencies(job.stage)
    )


def ready_jobs(store: JobStore) -> list[ExecutionJob]:
    """Return deterministic ready jobs sorted by recording and stage."""
    return sorted((job for job in store.load().values() if is_ready(store, job)), key=lambda item: (item.recording_id, item.stage, item.job_id))
