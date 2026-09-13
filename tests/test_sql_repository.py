from __future__ import annotations

from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import Recording
from transcribe_intelligence.sql_repository import SqlRepository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def execute(self, operation, parameters=()):
        self.connection.calls.append((operation, parameters))
        if operation.startswith("SELECT recording_id"):
            row = self.connection.recordings.get(parameters[0])
            self.rows = [row] if row else []
        elif operation.startswith("SELECT job_id") and "WHERE job_id" in operation:
            row = self.connection.jobs.get(parameters[0])
            self.rows = [row] if row else []
        elif operation.startswith("SELECT job_id"):
            self.rows = sorted(
                (row for row in self.connection.jobs.values() if row[1] == parameters[0]),
                key=lambda row: (row[2], row[0]),
            )
        elif operation.startswith("INSERT INTO recordings"):
            self.connection.recordings.setdefault(parameters[0], parameters)
        elif operation.startswith("INSERT INTO execution_jobs"):
            self.connection.jobs.setdefault(parameters[0], parameters)
        elif operation.startswith("UPDATE execution_jobs"):
            job_id = parameters[-1]
            if job_id in self.connection.jobs:
                self.connection.jobs[job_id] = (job_id, *parameters[:-1])
        elif operation.startswith("UPDATE recordings"):
            recording_id = parameters[1]
            old = self.connection.recordings[recording_id]
            self.connection.recordings[recording_id] = (old[0], old[1], parameters[0])

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.recordings = {}
        self.jobs = {}
        self.calls = []
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


def test_sql_repository_round_trip_and_aggregate_status():
    repo = SqlRepository(FakeConnection())
    recording = repo.put_recording(Recording("r1", "/audio.wav"))
    job = ExecutionJob("r1:ingest", "r1", "ingest")
    repo.put_job(job)
    assert repo.get_recording("r1") == recording
    assert repo.get_job(job.job_id) == job

    completed = ExecutionJob(
        job.job_id, job.recording_id, job.stage, "completed", 1,
        "artifact-1", "worker-1", None, "2026-09-13T10:00:00+00:00"
    )
    repo.update_job(completed)
    refreshed = repo.refresh_recording_status("r1")
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert repo.list_jobs("r1") == [completed]


def test_sql_repository_missing_job_update_raises():
    repo = SqlRepository(FakeConnection())
    missing = ExecutionJob("missing", "r1", "ingest", "completed", artifact_id="a")
    try:
        repo.update_job(missing)
    except KeyError as exc:
        assert str(exc) == "'unknown job: missing'"
    else:
        raise AssertionError("expected KeyError")
