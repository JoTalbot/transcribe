from pathlib import Path

from transcribe_intelligence.dependencies import is_ready, ready_jobs
from transcribe_intelligence.job_store import ExecutionJob, JobStore


def test_only_ingest_is_initially_ready(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    for stage in ("ingest", "normalize", "asr"):
        store.upsert(ExecutionJob(f"r:{stage}", "r", stage))

    ready = ready_jobs(store)
    assert [job.stage for job in ready] == ["ingest"]


def test_dependent_job_becomes_ready_after_artifact(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    ingest = ExecutionJob("r:ingest", "r", "ingest", "completed", artifact_id="a1")
    normalize = ExecutionJob("r:normalize", "r", "normalize")
    store.upsert(ingest)
    store.upsert(normalize)

    assert is_ready(store, normalize)
    assert [job.job_id for job in ready_jobs(store)] == ["r:normalize"]


def test_linking_requires_topics_and_embeddings(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    for stage in ("topics", "embeddings"):
        store.upsert(ExecutionJob(f"r:{stage}", "r", stage, "completed", artifact_id=stage))
    linking = ExecutionJob("r:linking", "r", "linking")
    store.upsert(linking)

    assert is_ready(store, linking)
