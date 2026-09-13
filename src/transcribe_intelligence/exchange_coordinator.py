"""Backend-neutral coordinator for dispatching jobs and consuming worker results."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dependencies import dependencies
from .exchange import ExchangeError, FileExchange, JobEnvelope
from .job_store import ExecutionJob
from .repository import Repository
from .result_service import apply_result


@dataclass(frozen=True, slots=True)
class Dispatch:
    """A job transitioned to running and published to the worker exchange."""

    job_id: str
    request_path: str


class ExchangeCoordinator:
    """Drive one deterministic exchange cycle against a canonical repository."""

    def __init__(self, repository: Repository, exchange: FileExchange):
        self.repository = repository
        self.exchange = exchange

    def dispatch_ready(self, recording_id: str, worker: str = "colab") -> list[Dispatch]:
        """Publish ready queued/retry jobs and persist their running state."""
        recording = self.repository.get_recording(recording_id)
        if recording is None:
            raise KeyError(f"unknown recording: {recording_id}")

        jobs = self.repository.list_jobs(recording_id)
        completed = {
            job.stage: job.artifact_id
            for job in jobs
            if job.status == "completed" and job.artifact_id
        }
        dispatches: list[Dispatch] = []

        for job in jobs:
            if job.status not in {"queued", "retry"}:
                continue
            required = dependencies(job.stage)
            if not all(stage in completed for stage in required):
                continue

            input_artifact_id = completed[required[0]] if required else None
            running = job.next_attempt(worker)
            self.repository.update_job(running)
            request = JobEnvelope(
                job_id=running.job_id,
                recording_id=running.recording_id,
                stage=running.stage,
                input_artifact_id=input_artifact_id,
                input_path=recording.input_path if input_artifact_id is None else None,
            )
            path = self.exchange.put_request(request)
            dispatches.append(Dispatch(running.job_id, str(path)))

        return dispatches

    def quarantine_result(self, path: Path, reason: str) -> Path:
        """Move a bad result aside so one poisoned envelope cannot block the queue."""
        quarantine = self.exchange.results / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        target = quarantine / path.name
        if target.exists():
            target = quarantine / f"{path.stem}.quarantined.json"
        path.replace(target)
        target.with_suffix(target.suffix + ".error").write_text(reason + "\n", encoding="utf-8")
        return target

    def apply_results(self) -> int:
        """Consume valid results and quarantine malformed/conflicting ones."""
        changed = 0
        for path in sorted(self.exchange.results.glob("*.json")):
            try:
                result = self.exchange.get_result(path.stem)
                changed += int(apply_result(self.repository, result))
            except (ExchangeError, KeyError, ValueError) as exc:
                self.quarantine_result(path, str(exc))
        return changed

    def cycle(self, recording_id: str, worker: str = "colab") -> tuple[list[Dispatch], int]:
        """Apply available results, then dispatch newly-ready work."""
        changed = self.apply_results()
        dispatches = self.dispatch_ready(recording_id, worker=worker)
        return dispatches, changed


def ready_jobs(jobs: list[ExecutionJob]) -> list[ExecutionJob]:
    """Return queued/retry jobs whose stage prerequisites are completed."""
    completed = {job.stage for job in jobs if job.status == "completed" and job.artifact_id}
    return [
        job
        for job in sorted(jobs, key=lambda item: (item.stage, item.job_id))
        if job.status in {"queued", "retry"}
        and all(stage in completed for stage in dependencies(job.stage))
    ]
