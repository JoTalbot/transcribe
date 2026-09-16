"""Coordinate PostgreSQL job state with the filesystem exchange."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .artifact_resolver import ArtifactResolutionError, ArtifactResolver
from .exchange import ExchangeError, FileExchange, JobEnvelope, ResultEnvelope
from .job_store import ExecutionJob
from .pipeline_contract import Stage, dependencies
from .repository import Repository
from .result_service import apply_result
from .worker_capabilities import DEFAULT_WORKER_CAPABILITIES, DEFAULT_STAGE_WORKERS, WorkerCapability


class ExchangeCoordinator:
    """Bridge durable execution state and worker exchange files."""

    def __init__(
        self,
        repository: Repository,
        exchange: FileExchange,
        *,
        worker_capabilities: dict[str, WorkerCapability] | None = None,
        stage_workers: dict[Stage, str] | None = None,
        artifact_root: Path | None = None,
        verify_artifacts: bool = False,
    ) -> None:
        self.repository = repository
        self.exchange = exchange
        self.worker_capabilities = worker_capabilities
        self.stage_workers = stage_workers or DEFAULT_STAGE_WORKERS
        self.artifact_root = artifact_root
        self.verify_artifacts = verify_artifacts
        self.artifact_resolver = ArtifactResolver(artifact_root) if artifact_root is not None else None

    def _exchange_has_job(self, job_id: str) -> bool:
        return self.exchange.has_request(job_id) or self.exchange.has_processing(job_id)

    def _target_worker(self, stage: Stage, fallback: str) -> str | None:
        target = self.stage_workers.get(stage, fallback)
        if self.worker_capabilities is None:
            return fallback
        capabilities = self.worker_capabilities.get(target)
        return target if capabilities is not None and capabilities.supports(stage) else None

    def _claim(self, job: ExecutionJob, worker: str) -> ExecutionJob | None:
        claim_job = getattr(self.repository, "claim_job", None)
        if callable(claim_job):
            return claim_job(job.job_id, worker)
        if job.status not in {"queued", "retry"}:
            return None
        return self.repository.update_job(job.next_attempt(worker))

    def _release(self, job: ExecutionJob, error: str) -> ExecutionJob:
        release = getattr(self.repository, "release", None)
        if callable(release) and job.lease_id:
            return release(job.job_id, job.worker or "", job.lease_id, error)
        return self.repository.update_job(ExecutionJob(job.job_id, job.recording_id, job.stage, "retry", job.attempt, job.artifact_id, None, error, job.updated_at, None, None, job.heartbeat_at))

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
            request = JobEnvelope(job_id=running.job_id, recording_id=running.recording_id, stage=running.stage, input_artifact_id=input_artifact_id, input_artifact_ids=input_artifact_ids, input_path=recording.input_path if not input_artifact_ids else None, worker=running.worker, lease_id=running.lease_id)
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
        if callable(heartbeat) and job.lease_id:
            if not worker:
                raise ValueError("worker is required for a leased job")
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
        """Re-check that a rejected result still belongs to the same owned lease."""
        current = self.repository.get_job(job.job_id)
        if current is None or current.status != "running" or current.worker != worker or current.lease_id != lease_id:
            return False
        if not current.lease_until:
            return True
        try:
            lease_until = datetime.fromisoformat(current.lease_until)
        except ValueError:
            return False
        if lease_until.tzinfo is None:
            lease_until = lease_until.replace(tzinfo=timezone.utc)
        return lease_until > datetime.now(timezone.utc)

    def _verify_result_artifact(self, result: object, job: ExecutionJob | None = None) -> None:
        """Verify a completed result points to an available, untampered, job-bound artifact."""
        if not self.verify_artifacts:
            return
        artifact_id = getattr(result, "artifact_id", None)
        if not artifact_id:
            raise ArtifactResolutionError("completed result requires artifact_id")
        assert self.artifact_resolver is not None
        if job is None:
            self.artifact_resolver.resolve_path(artifact_id)
            return
        manifest = self.artifact_resolver.resolve_for(
            artifact_id,
            recording_id=job.recording_id,
            stage=job.stage,
        )
        self.artifact_resolver.resolve_path(manifest.artifact_id)

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
            if result.status == "completed" and callable(complete) and result.lease_id:
                if result.worker != job.worker or result.lease_id != job.lease_id:
                    self.quarantine_result(path, f"stale or foreign result for job {result.job_id}")
                    continue
                if not result.artifact_id:
                    self.quarantine_result(path, "completed result requires artifact_id")
                    continue
                try:
                    self._verify_result_artifact(result, job)
                except (ArtifactResolutionError, FileNotFoundError, OSError, ValueError) as exc:
                    self.quarantine_result(path, f"invalid completed artifact for job {result.job_id}: {exc}")
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
            else:
                if result.status == "completed" and self.verify_artifacts:
                    try:
                        self._verify_result_artifact(result, job)
                    except (ArtifactResolutionError, FileNotFoundError, OSError, ValueError) as exc:
                        self.quarantine_result(path, f"invalid completed artifact for job {result.job_id}: {exc}")
                        continue
                if result.status == "failed" and callable(fail) and result.lease_id:
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
        changed = self.apply_results()
        return self.dispatch_ready(recording_id, worker=worker), changed


class Dispatch:
    def __init__(self, job_id: str, path: str):
        self.job_id = job_id
        self.path = path


def ready_jobs(jobs: list[ExecutionJob]) -> list[ExecutionJob]:
    return sorted((job for job in jobs if job.status in {"queued", "retry"}), key=lambda job: job.job_id)
