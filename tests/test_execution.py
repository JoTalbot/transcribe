from pathlib import Path

from transcribe_intelligence.execution import DryRunBackend, dispatch_one
from transcribe_intelligence.job_store import ExecutionJob, JobStore


def test_dispatch_one_completes_with_backend_artifact(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    job = ExecutionJob("r:asr", "r", "asr")
    store.upsert(job)

    done = dispatch_one(store, job.job_id, DryRunBackend(), "worker-a")

    assert done.status == "completed"
    assert done.artifact_id == "dry-run:r:asr"
    assert done.attempt == 1


def test_dispatch_one_reuses_completed_job(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    job = ExecutionJob("r:asr", "r", "asr")
    store.upsert(job)
    first = dispatch_one(store, job.job_id, DryRunBackend(), "worker-a")
    second = dispatch_one(store, job.job_id, DryRunBackend(), "worker-b")

    assert second == first
