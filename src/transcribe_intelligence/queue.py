"""Turn pending planner items into stable execution jobs."""
from __future__ import annotations

from .job_store import ExecutionJob, JobStore, stable_job_id
from .planner import PlanItem


def enqueue(items: list[PlanItem], jobs: JobStore) -> list[ExecutionJob]:
    """Create missing queue records without duplicating existing jobs."""
    result: list[ExecutionJob] = []
    existing = jobs.load()
    for item in items:
        job_id = stable_job_id(item.recording_id, item.stage.value)
        job = existing.get(job_id)
        if job is None:
            job = jobs.upsert(ExecutionJob(job_id, item.recording_id, item.stage.value))
        result.append(job)
    return result
