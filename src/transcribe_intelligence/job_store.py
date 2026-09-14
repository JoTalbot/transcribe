"""Dependency-free execution job records for resumable workers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExecutionJob:
    job_id: str
    recording_id: str
    stage: str
    status: str = "queued"
    attempt: int = 0
    artifact_id: str | None = None
    worker: str | None = None
    error: str | None = None
    updated_at: str | None = None
    lease_id: str | None = None
    lease_until: str | None = None
    heartbeat_at: str | None = None

    def next_attempt(self, worker: str | None = None) -> "ExecutionJob":
        return ExecutionJob(
            self.job_id, self.recording_id, self.stage, "running",
            self.attempt + 1, self.artifact_id, worker or self.worker,
            None, now_iso(), None, None, None,
        )

    def heartbeat(self, worker: str | None = None) -> "ExecutionJob":
        """Refresh the local heartbeat without changing lease ownership."""
        if self.status != "running":
            raise ValueError("only running jobs can heartbeat")
        if worker is not None and self.worker not in {None, worker}:
            raise ValueError(f"job is owned by worker {self.worker!r}")
        heartbeat_at = now_iso()
        return ExecutionJob(
            self.job_id, self.recording_id, self.stage, self.status,
            self.attempt, self.artifact_id, worker or self.worker,
            self.error, heartbeat_at, self.lease_id, self.lease_until,
            heartbeat_at,
        )


class JobStore:
    """Atomically persist execution jobs keyed by stable job_id."""
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, ExecutionJob]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: ExecutionJob(**value) for key, value in raw.items()}

    def get(self, job_id: str) -> ExecutionJob | None:
        return self.load().get(job_id)

    def upsert(self, job: ExecutionJob) -> ExecutionJob:
        jobs = self.load()
        stored = ExecutionJob(**{**asdict(job), "updated_at": job.updated_at or now_iso()})
        jobs[stored.job_id] = stored
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({key: asdict(value) for key, value in sorted(jobs.items())}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return stored


def stable_job_id(recording_id: str, stage: str) -> str:
    return f"{recording_id}:{stage}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
