"""Colab execution adapter boundary.

This module deliberately does not automate authentication or browser controls.
The Colab worker consumes a job/artifact contract and returns a normal execution result.
"""
from __future__ import annotations

from dataclasses import dataclass

from .execution import ExecutionResult
from .job_store import ExecutionJob


@dataclass(frozen=True, slots=True)
class ColabJobRequest:
    job_id: str
    recording_id: str
    stage: str
    input_artifact_id: str | None = None


class ColabExecutionBackend:
    """Transport-neutral adapter for a Colab GPU worker.

    A transport implementation can submit ``ColabJobRequest`` to the worker.
    Keeping submission injectable prevents browser automation from leaking into
    pipeline orchestration and makes a future API/queue transport interchangeable.
    """

    name = "colab"

    def __init__(self, submit):
        self._submit = submit

    def execute(self, job: ExecutionJob) -> ExecutionResult:
        request = ColabJobRequest(job.job_id, job.recording_id, job.stage, job.artifact_id)
        result = self._submit(request)
        if not isinstance(result, ExecutionResult):
            raise TypeError("Colab submitter must return ExecutionResult")
        if result.job_id != job.job_id:
            raise RuntimeError("Colab worker returned a different job_id")
        return result
