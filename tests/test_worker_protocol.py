from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from transcribe_intelligence.job_store import ExecutionJob, JobStore
from transcribe_intelligence.worker_protocol import JobConflict, claim, complete, fail


def test_claim_complete_and_idempotent_completion(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    store.upsert(ExecutionJob("r:asr", "r", "asr"))
    claimed = claim(store, "r:asr", "worker-a", lease_seconds=60)
    assert claimed.status == "running"
    assert claimed.attempt == 1
    assert claimed.worker == "worker-a"
    done = complete(store, "r:asr", "worker-a", "artifact-1")
    assert done.status == "completed"
    assert complete(store, "r:asr", "worker-b", "artifact-1") == done


def test_second_worker_cannot_claim_active_lease(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    store.upsert(ExecutionJob("r:asr", "r", "asr"))
    claim(store, "r:asr", "worker-a", lease_seconds=60)
    with pytest.raises(JobConflict):
        claim(store, "r:asr", "worker-b", lease_seconds=60)


def test_expired_lease_reclaimed_and_failure_requeued(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    expired = datetime.now(timezone.utc) - timedelta(seconds=30)
    store.upsert(ExecutionJob("r:asr", "r", "asr", "running", 1, None, "worker-a", None, expired.isoformat()))
    claimed = claim(store, "r:asr", "worker-b", lease_seconds=10)
    assert claimed.attempt == 2
    queued = fail(store, "r:asr", "worker-b", "temporary failure")
    assert queued.status == "queued"
    assert queued.worker is None
    assert queued.error == "temporary failure"


def test_invalid_inputs_rejected(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    store.upsert(ExecutionJob("r:asr", "r", "asr"))
    with pytest.raises(ValueError):
        claim(store, "r:asr", "", 10)
    with pytest.raises(ValueError):
        claim(store, "r:asr", "worker", 0)
    claim(store, "r:asr", "worker", 10)
    with pytest.raises(ValueError):
        complete(store, "r:asr", "worker", "")
    with pytest.raises(ValueError):
        fail(store, "r:asr", "worker", "")
