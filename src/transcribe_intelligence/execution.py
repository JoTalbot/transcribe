"""Backend-neutral execution contract for pipeline workers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .job_store import ExecutionJob


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    job_id: str
    status: str
    artifact_id: str | None = None
    error: str | None = None


class ExecutionBackend(Protocol):
    name: str

    def execute(self, job: ExecutionJob) -> ExecutionResult:
        """Execute one claimed job."""


class DryRunBackend:
    name = "dry-run"

    def execute(self, job: ExecutionJob) -> ExecutionResult:
        return ExecutionResult(job.job_id, "completed", artifact_id=f"dry-run:{job.job_id}")
