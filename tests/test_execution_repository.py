from __future__ import annotations

import pytest

from transcribe_intelligence.execution import DryRunBackend, dispatch_one_repository
from transcribe_intelligence.job_store import ExecutionJob


class FakeLeaseRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, ExecutionJob] = {}
        self.completed: list[tuple[str, str, str, str]] = []
        self.failed: list[tuple[str, str, str, str]] = []

    def get_job(self, job_id: str) -> ExecutionJob | None:
        return self.jobs.get(job_id)

    def claim_job(self, job_id: str, worker: str, lease_seconds: int = 900) -> ExecutionJob | None:
        job = self.jobs.get(job_id)
        if job is None or job.status not in {"queued", "retry"}:
            return None
        claimed = ExecutionJob(
            job.job_id, job.recording_id, job.stage, "running", job.attempt + 1,
            job.artifact_id, worker, None, job.updated_at, f"lease-{worker}",
            "2099-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00",
        )
        self.jobs[job_id] = claimed
        return claimed

    def complete(self, job_id: str, worker: str, lease_id: str, artifact_id: str) -> ExecutionJob:
        self.completed.append((job_id, worker, lease_id, artifact_id))
        job = self.jobs[job_id]
        done = ExecutionJob(
            job.job_id, job.recording_id, job.stage, "completed", job.attempt,
            artifact_id, job.worker, None, job.updated_at, None, None, job.heartbeat_at,
        )
        self.jobs[job_id] = done
        return done

    def fail(self, job_id: str, worker: str, lease_id: str, error: str) -> ExecutionJob:
        self.failed.append((job_id, worker, lease_id, error))
        job = self.jobs[job_id]
        failed = ExecutionJob(
            job.job_id, job.recording_id, job.stage, "failed", job.attempt,
            job.artifact_id, job.worker, error, job.updated_at, None, None, job.heartbeat_at,
        )
        self.jobs[job_id] = failed
        return failed


def test_repository_dispatch_preserves_lease_identity_on_completion() -> None:
    repo = FakeLeaseRepository()
    repo.jobs["r:asr"] = ExecutionJob("r:asr", "r", "asr")

    done = dispatch_one_repository(repo, "r:asr", DryRunBackend(), "worker-a")

    assert done.status == "completed"
    assert repo.completed == [("r:asr", "worker-a", "lease-worker-a", "dry-run:r:asr")]


def test_repository_dispatch_does_not_finalize_when_backend_returns_wrong_job() -> None:
    class WrongJobBackend:
        name = "wrong"

        def execute(self, job: ExecutionJob):
            from transcribe_intelligence.execution import ExecutionResult
            return ExecutionResult("other-job", "completed", artifact_id="bad")

    repo = FakeLeaseRepository()
    repo.jobs["r:asr"] = ExecutionJob("r:asr", "r", "asr")

    with pytest.raises(RuntimeError, match="different job_id"):
        dispatch_one_repository(repo, "r:asr", WrongJobBackend(), "worker-a")
    assert repo.failed[0][:3] == ("r:asr", "worker-a", "lease-worker-a")


def test_repository_dispatch_refuses_unclaimed_job() -> None:
    repo = FakeLeaseRepository()
    repo.jobs["r:asr"] = ExecutionJob("r:asr", "r", "asr", "running", worker="worker-a")

    with pytest.raises(RuntimeError, match="could not be claimed"):
        dispatch_one_repository(repo, "r:asr", DryRunBackend(), "worker-b")


def test_repository_dispatch_validates_lease_id() -> None:
    class BrokenLeaseRepository(FakeLeaseRepository):
        def claim_job(self, job_id: str, worker: str, lease_seconds: int = 900):
            return ExecutionJob(job_id, "r", "asr", "running", 1, worker=worker)

    repo = BrokenLeaseRepository()
    repo.jobs["r:asr"] = ExecutionJob("r:asr", "r", "asr")

    with pytest.raises(RuntimeError, match="without a lease_id"):
        dispatch_one_repository(repo, "r:asr", DryRunBackend(), "worker-a")
