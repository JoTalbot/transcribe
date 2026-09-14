"""DB-API compatible SQL repository for canonical transcription state."""
from __future__ import annotations

from typing import Any, Protocol
import uuid

from .execution_lease import CLAIM_SQL, COMPLETE_SQL, FAIL_SQL, HEARTBEAT_SQL
from .job_store import ExecutionJob
from .repository import Recording, Repository


class Cursor(Protocol):
    def execute(self, operation: str, parameters: tuple[Any, ...] = ()) -> Any: ...
    def fetchone(self) -> tuple[Any, ...] | None: ...
    def fetchall(self) -> list[tuple[Any, ...]]: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class SqlRepository(Repository):
    """PostgreSQL-ready repository using only the DB-API connection contract."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def put_recording(self, recording: Recording) -> Recording:
        self._execute(
            """INSERT INTO recordings (recording_id, input_path, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (recording_id) DO NOTHING""",
            (recording.recording_id, recording.input_path, recording.status),
        )
        return self.get_recording(recording.recording_id) or recording

    def get_recording(self, recording_id: str) -> Recording | None:
        row = self._query_one(
            "SELECT recording_id, input_path, status FROM recordings WHERE recording_id = %s",
            (recording_id,),
        )
        if row is None:
            return None
        return Recording(row[0], row[1], row[2])

    def put_job(self, job: ExecutionJob) -> ExecutionJob:
        self._execute(
            """INSERT INTO execution_jobs
            (job_id, recording_id, stage, status, attempt, artifact_id, worker, error,
             updated_at, lease_id, lease_until, heartbeat_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id) DO NOTHING""",
            (job.job_id, job.recording_id, job.stage, job.status, job.attempt,
             job.artifact_id, job.worker, job.error, job.updated_at,
             job.lease_id, job.lease_until, job.heartbeat_at),
        )
        stored = self.get_job(job.job_id)
        if stored is None:
            raise RuntimeError(f"job insert failed: {job.job_id}")
        return stored

    def get_job(self, job_id: str) -> ExecutionJob | None:
        row = self._query_one(
            """SELECT job_id, recording_id, stage, status, attempt,
            artifact_id, worker, error, updated_at, lease_id, lease_until,
            heartbeat_at FROM execution_jobs WHERE job_id = %s""",
            (job_id,),
        )
        return self._job(row) if row else None

    def list_jobs(self, recording_id: str) -> list[ExecutionJob]:
        rows = self._query_all(
            """SELECT job_id, recording_id, stage, status, attempt,
            artifact_id, worker, error, updated_at, lease_id, lease_until,
            heartbeat_at FROM execution_jobs WHERE recording_id = %s
            ORDER BY stage, job_id""",
            (recording_id,),
        )
        return [self._job(row) for row in rows]

    def update_job(self, job: ExecutionJob) -> ExecutionJob:
        self._execute(
            """UPDATE execution_jobs SET recording_id = %s, stage = %s,
            status = %s, attempt = %s, artifact_id = %s, worker = %s,
            error = %s, updated_at = %s, lease_id = %s, lease_until = %s,
            heartbeat_at = %s WHERE job_id = %s""",
            (job.recording_id, job.stage, job.status, job.attempt, job.artifact_id,
             job.worker, job.error, job.updated_at, job.lease_id, job.lease_until,
             job.heartbeat_at, job.job_id),
        )
        stored = self.get_job(job.job_id)
        if stored is None:
            raise KeyError(f"unknown job: {job.job_id}")
        return stored

    def claim_next(self, worker: str, lease_seconds: int = 3600) -> ExecutionJob | None:
        """Atomically claim one queued/retry job for a worker."""
        if not worker:
            raise ValueError("worker is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        return self._lease_query(
            CLAIM_SQL, (worker, uuid.uuid4().hex, lease_seconds), expect_job=True
        )

    def heartbeat(self, job_id: str, worker: str, lease_id: str, lease_seconds: int = 900) -> ExecutionJob:
        """Refresh a live worker lease, rejecting stale or foreign ownership."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        row = self._lease_query(HEARTBEAT_SQL, (lease_seconds, job_id, worker, lease_id))
        if row is None:
            raise RuntimeError("lease heartbeat rejected")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        return job

    def complete(self, job_id: str, worker: str, lease_id: str, artifact_id: str) -> ExecutionJob:
        """Complete only the currently owned, unexpired lease."""
        if not artifact_id:
            raise ValueError("artifact_id is required")
        row = self._lease_query(COMPLETE_SQL, (artifact_id, job_id, worker, lease_id))
        if row is None:
            raise RuntimeError("lease completion rejected")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        return job

    def fail(self, job_id: str, worker: str, lease_id: str, error: str) -> ExecutionJob:
        """Fail only the currently owned, unexpired lease."""
        if not error.strip():
            raise ValueError("error must not be empty")
        row = self._lease_query(FAIL_SQL, (error, job_id, worker, lease_id))
        if row is None:
            raise RuntimeError("lease failure update rejected")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        return job

    def refresh_recording_status(self, recording_id: str) -> Recording | None:
        """Derive aggregate status atomically from persisted job state."""
        recording = self.get_recording(recording_id)
        if recording is None:
            return None
        jobs = self.list_jobs(recording_id)
        if not jobs:
            return recording
        statuses = {job.status for job in jobs}
        if "failed" in statuses:
            status = "failed"
        elif statuses == {"completed"}:
            status = "completed"
        elif "running" in statuses:
            status = "running"
        else:
            status = "queued"
        self._execute(
            "UPDATE recordings SET status = %s WHERE recording_id = %s",
            (status, recording_id),
        )
        return Recording(recording.recording_id, recording.input_path, status)

    def _lease_query(
        self, sql: str, parameters: tuple[Any, ...], expect_job: bool = False
    ) -> ExecutionJob | tuple[Any, ...] | None:
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, parameters)
            row = cursor.fetchone()
            self.connection.commit()
            if expect_job and row is not None:
                return self._job(row)
            return row
        except Exception:
            self.connection.rollback()
            raise

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, parameters)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _query_one(self, sql: str, parameters: tuple[Any, ...]) -> tuple[Any, ...] | None:
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, parameters)
            return cursor.fetchone()
        except Exception:
            self.connection.rollback()
            raise

    def _query_all(self, sql: str, parameters: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, parameters)
            return cursor.fetchall()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _job(row: tuple[Any, ...]) -> ExecutionJob:
        return ExecutionJob(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7],
            _iso(row[8]), _iso(row[9]), _iso(row[10]), _iso(row[11])
        )


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value
