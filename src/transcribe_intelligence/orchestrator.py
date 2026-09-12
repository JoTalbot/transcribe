"""Resumable orchestration primitives for the conversation-intelligence pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .dependencies import is_ready
from .job_store import ExecutionJob
from .pipeline_contract import Stage


@dataclass(frozen=True, slots=True)
class StageTask:
    recording_id: str
    stage: Stage
    input_artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class OrchestrationDecision:
    task: StageTask
    action: str
    reason: str


def build_ready_plan(
    jobs: Iterable[ExecutionJob],
    completed: set[tuple[str, Stage]],
) -> list[OrchestrationDecision]:
    """Return deterministic decisions without executing expensive work."""
    ordered = sorted(jobs, key=lambda job: (job.recording_id, job.stage.value, job.job_id))
    decisions: list[OrchestrationDecision] = []
    for job in ordered:
        key = (job.recording_id, job.stage)
        if key in completed:
            decisions.append(
                OrchestrationDecision(
                    StageTask(job.recording_id, job.stage),
                    "skip",
                    "stage already completed",
                )
            )
        elif is_ready(job.stage, {stage for recording, stage in completed if recording == job.recording_id}):
            decisions.append(
                OrchestrationDecision(
                    StageTask(job.recording_id, job.stage),
                    "run",
                    "dependencies satisfied",
                )
            )
        else:
            decisions.append(
                OrchestrationDecision(
                    StageTask(job.recording_id, job.stage),
                    "wait",
                    "dependencies incomplete",
                )
            )
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
