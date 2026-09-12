"""Resumable orchestration primitives for the conversation-intelligence pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .dependencies import dependencies
from .job_store import ExecutionJob


@dataclass(frozen=True, slots=True)
class StageTask:
    recording_id: str
    stage: str
    input_artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class OrchestrationDecision:
    task: StageTask
    action: str
    reason: str


def build_ready_plan(
    jobs: Iterable[ExecutionJob],
    completed: set[tuple[str, str]],
) -> list[OrchestrationDecision]:
    """Return deterministic run/skip/wait decisions without executing work."""
    ordered = sorted(jobs, key=lambda job: (job.recording_id, job.stage, job.job_id))
    decisions: list[OrchestrationDecision] = []
    for job in ordered:
        key = (job.recording_id, job.stage)
        task = StageTask(job.recording_id, job.stage, job.artifact_id)
        if job.status == "completed" or key in completed:
            decisions.append(OrchestrationDecision(task, "skip", "stage already completed"))
            continue
        prerequisite_keys = {
            (job.recording_id, stage) for stage in dependencies(job.stage)
        }
        if prerequisite_keys.issubset(completed):
            decisions.append(OrchestrationDecision(task, "run", "dependencies satisfied"))
        else:
            decisions.append(OrchestrationDecision(task, "wait", "dependencies incomplete"))
    return decisions


def execute_decisions(
    decisions: Iterable[OrchestrationDecision],
    runner: Callable[[StageTask], None],
) -> list[OrchestrationDecision]:
    """Execute only runnable decisions, preserving deterministic order."""
    executed: list[OrchestrationDecision] = []
    for decision in decisions:
        if decision.action != "run":
            continue
        runner(decision.task)
        executed.append(decision)
    return executed
