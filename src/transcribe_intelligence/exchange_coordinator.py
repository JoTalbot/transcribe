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

    def _exchange_has_job(self, job_id: str) -> bool:
        return any(
            path.exists()
            for path in (
                self.exchange.requests / f"{job_id}.json",
                self.exchange.results / f"{job_id}.json",
                self.exchange.root / "processing" / f"{job_id}.json",
            )
        )

    def _claim(self, job: ExecutionJob, worker: str) -> ExecutionJob | None:
        claim_job = getattr(self.repository, "claim_job", None)
        if callable(claim_job):
            return claim_job(job.job_id, worker)
        return self.repository.update_job(job.next_attempt(worker))

    def _release(self, job: ExecutionJob, error: str) -> None:
        """Return a claimed job to retry without leaving a long-lived lease."""
        release = getattr(self.repository, "release", None)
        if callable(release) and job.worker and job.lease_id:
            release(job.job_id, job.worker, job.lease_id, error)
            return
        self.repository.update_job(
            ExecutionJob(
                job.job_id,
                job.recording_id,
                job.stage,
                "retry",
                job.attempt,
                job.artifact_id,
                None,
                error,
                job.updated_at,
                None,
                None,
                None,
            )
        )

    def dispatch_ready(self, recording_id: str, worker: str = "colab") -> list[Dispatch]:
        recording = self.repository.get_recording(recording_id)
        if recording is None:
            raise KeyError(f"unknown recording: {recording_id}")
        jobs = self.repository.list_jobs(recording_id)
        completed = {job.stage: job.artifact_id for job in jobs if job.status == "completed" and job.artifact_id}
        dispatches: list[Dispatch] = []
        for job in jobs:
            if job.status not in {"queued", "retry"}:
                continue
            required = dependencies(job.stage)
            if not all(stage in completed for stage in required) or self._exchange_has_job(job.job_id):
                continue
            running = self._claim(job, worker)
            if running is None:
                continue
            input_artifact_id = completed[required[0]] if required else None
            request = JobEnvelope(
                job_id=running.job_id,
                recording_id=running.recording_id,
                stage=running.stage,
                input_artifact_id=input_artifact_id,
                input_path=recording.input_path if input_artifact_id is None else None,
                worker=running.worker,
                lease_id=running.lease_id,
            )
            try:
                path = self.exchange.put_request(request)
            except Exception as exc:
                self._release(running, f"exchange publish failed: {exc}")
                continue
            dispatches.append(Dispatch(running.job_id, str(path)))
        return dispatches

    def heartbeat(self, job_id: str, worker: str | None = None) -> ExecutionJob:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        heartbeat = getattr(self.repository, "heartbeat", None)
        if callable(heartbeat):
            if not worker or not job.lease_id:
                raise ValueError("worker and persisted lease_id are required")
            return heartbeat(job_id, worker, job.lease_id)
        refreshed = job.heartbeat(worker)
        return self.repository.update_job(refreshed)

    def quarantine_result(self, path: Path, reason: str) -> Path:
        quarantine = self.exchange.results / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        target = quarantine / path.name
        if target.exists():
            target = quarantine / f"{path.stem}.quarantined.json"
        path.replace(target)
        target.with_suffix(target.suffix + ".error").write_text(reason + "\n", encoding="utf-8")
        return target

    def apply_results(self) -> int:
        changed = 0
        for path in sorted(self.exchange.results.glob("*.json")):
            try:
                result = self.exchange.get_result(path.stem)
                job = self.repository.get_job(result.job_id)
            except (ExchangeError, KeyError, ValueError) as exc:
                self.quarantine_result(path, str(exc))
                continue

            if job is None:
                self.quarantine_result(path, f"unknown job: {result.job_id}")
                continue

            complete = getattr(self.repository, "complete", None)
            fail = getattr(self.repository, "fail", None)
            if callable(complete) and callable(fail):
                if result.worker != job.worker or result.lease_id != job.lease_id:
                    self.quarantine_result(path, f"stale or foreign result for job {result.job_id}")
                    continue
                if result.status == "completed":
                    if not result.artifact_id:
                        self.quarantine_result(path, "completed result requires artifact_id")
                        continue
                    complete(result.job_id, result.worker, result.lease_id, result.artifact_id)
                elif result.status == "failed":
                    fail(result.job_id, result.worker, result.lease_id, result.error or "worker failed")
                else:
                    self.quarantine_result(path, "result status must be completed or failed")
                    continue
                changed += 1
            else:
                try:
                    changed += int(apply_result(self.repository, result))
                except (ExchangeError, KeyError, ValueError) as exc:
                    self.quarantine_result(path, str(exc))
        return changed

    def cycle(self, recording_id: str, worker: str = "colab") -> tuple[list[Dispatch], int]:
        changed = self.apply_results()
        dispatches = self.dispatch_ready(recording_id, worker=worker)
        return dispatches, changed


def ready_jobs(jobs: list[ExecutionJob]) -> list[ExecutionJob]:
    completed = {job.stage for job in jobs if job.status == "completed" and job.artifact_id}
    return [
        job
        for job in sorted(jobs, key=lambda item: (item.stage, item.job_id))
        if job.status in {"queued", "retry"} and all(stage in completed for stage in dependencies(job.stage))
    ]
