"""Backend-neutral coordinator for dispatching jobs and consuming worker results."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dependencies import dependencies
from .exchange import ExchangeError, FileExchange, JobEnvelope
from .job_store import ExecutionJob
from .pipeline_contract import Stage
from .repository import Repository
from .result_service import apply_result
from .worker_capabilities import DEFAULT_STAGE_WORKERS, WorkerCapabilities


@dataclass(frozen=True, slots=True)
class Dispatch:
    """A job transitioned to running and published to the worker exchange."""

    job_id: str
    request_path: str


class ExchangeCoordinator:
    """Drive one deterministic exchange cycle against a canonical repository."""

    def __init__(
        self,
        repository: Repository,
        exchange: FileExchange,
        worker_capabilities: dict[str, WorkerCapabilities] | None = None,
        stage_workers: dict[Stage | str, str] | None = None,
    ):
        self.repository = repository
        self.exchange = exchange
        self.worker_capabilities = worker_capabilities
        self.stage_workers = {
            stage if isinstance(stage, Stage) else Stage(stage): worker
            for stage, worker in (stage_workers or {}).items()
        }

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

    def _target_worker(self, stage: Stage, fallback: str) -> str | None:
        """Resolve an explicit route or a deterministic capable default."""
        explicit = self.stage_workers.get(stage)
        if explicit is not None:
            if self.worker_capabilities is None:
                return explicit
            capabilities = self.worker_capabilities.get(explicit)
            return explicit if capabilities is not None and capabilities.supports(stage) else None

        if fallback == "colab":
            candidates = self.worker_capabilities
            default_worker = DEFAULT_STAGE_WORKERS.get(stage)
            if candidates is None:
                return default_worker
            if default_worker is not None:
                capabilities = candidates.get(default_worker)
                if capabilities is not None and capabilities.supports(stage):
                    return default_worker
            for worker_name in sorted(candidates):
                if candidates[worker_name].supports(stage):
                    return worker_name
            return None

        if self.worker_capabilities is None:
            return fallback
        capabilities = self.worker_capabilities.get(fallback)
        return fallback if capabilities is not None and capabilities.supports(stage) else None

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
            try:
                stage = Stage(job.stage)
            except ValueError:
                continue
            target_worker = self._target_worker(stage, worker)
            if target_worker is None:
                continue
            required = dependencies(job.stage)
            if not all(stage_name in completed for stage_name in required) or self._exchange_has_job(job.job_id):
                continue
            running = self._claim(job, target_worker)
            if running is None:
                continue
            input_artifact_ids = tuple(completed[stage_name] for stage_name in required)
            input_artifact_id = input_artifact_ids[0] if input_artifact_ids else None
            request = JobEnvelope(
                job_id=running.job_id,
                recording_id=running.recording_id,
                stage=running.stage,
                input_artifact_id=input_artifact_id,
                input_artifact_ids=input_artifact_ids,
                input_path=recording.input_path if not input_artifact_ids else None,
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

    def _consume_result(self, path: Path) -> None:
        """Remove a successfully persisted result so it cannot be replayed as stale."""
        path.unlink()

    def _lease_still_matches(self, job: ExecutionJob, worker: str | None, lease_id: str | None) -> bool:
        """Re-check ownership after a lease-aware mutation rejects a result."""
        current = self.repository.get_job(job.job_id)
        return (
            current is not None
            and current.status == "running"
            and current.worker == worker
            and current.lease_id == lease_id
        )

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
            if result.status == "completed" and callable(complete):
                if result.worker != job.worker or result.lease_id != job.lease_id:
                    self.quarantine_result(path, f"stale or foreign result for job {result.job_id}")
                    continue
                if not result.artifact_id:
                    self.quarantine_result(path, "completed result requires artifact_id")
                    continue
                try:
                    complete(result.job_id, result.worker, result.lease_id, result.artifact_id)
                except RuntimeError as exc:
                    if self._lease_still_matches(job, result.worker, result.lease_id):
                        raise
                    self.quarantine_result(path, f"stale or foreign result for job {result.job_id}: {exc}")
                    continue
                self._consume_result(path)
                changed += 1
            elif result.status == "failed" and callable(fail):
                if result.worker != job.worker or result.lease_id != job.lease_id:
                    self.quarantine_result(path, f"stale or foreign result for job {result.job_id}")
                    continue
                try:
                    fail(result.job_id, result.worker, result.lease_id, result.error or "worker failed")
                except RuntimeError as exc:
                    if self._lease_still_matches(job, result.worker, result.lease_id):
                        raise
                    self.quarantine_result(path, f"stale or foreign result for job {result.job_id}: {exc}")
                    continue
                self._consume_result(path)
                changed += 1
            else:
                try:
                    applied = apply_result(self.repository, result)
                except (ExchangeError, KeyError, ValueError) as exc:
                    self.quarantine_result(path, str(exc))
                    continue
                if applied:
                    self._consume_result(path)
                changed += applied
        return changed

    def cycle(self, recording_id: str, worker: str = "colab") -> tuple[list[Dispatch], int]:
        """Apply available results, then dispatch the newly ready jobs."""
        changed = self.apply_results()
        dispatches = self.dispatch_ready(recording_id, worker=worker)
        return dispatches, changed


def ready_jobs(jobs: list[ExecutionJob]) -> list[ExecutionJob]:
    """Return deterministic queued jobs whose prerequisites are completed."""
    completed = {
        (job.recording_id, job.stage): job.artifact_id
        for job in jobs
        if job.status == "completed" and job.artifact_id
    }
    ready: list[ExecutionJob] = []
    for job in jobs:
        if job.status != "queued":
            continue
        required = dependencies(job.stage)
        if all((job.recording_id, stage) in completed for stage in required):
            ready.append(job)
    return sorted(ready, key=lambda item: (item.recording_id, item.stage, item.job_id))
