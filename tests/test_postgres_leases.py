from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import uuid

import pytest
import psycopg

from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import Recording
from transcribe_intelligence.sql_repository import SqlRepository

DATABASE_URL = os.getenv("TRANSCRIBE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TRANSCRIBE_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture
def postgres_schema():
    assert DATABASE_URL is not None
    schema = f"transcribe_test_{uuid.uuid4().hex[:12]}"
    migrations_dir = Path(__file__).parents[1] / "migrations"
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
        connection.execute(f'SET search_path TO "{schema}"')
        for migration in sorted(migrations_dir.glob("*.sql")):
            for statement in migration.read_text(encoding="utf-8").split(";"):
                statement = statement.strip()
                if statement:
                    connection.execute(statement)
    try:
        yield schema
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def connect(schema: str):
    assert DATABASE_URL is not None
    connection = psycopg.connect(DATABASE_URL)
    connection.execute(f'SET search_path TO "{schema}"')
    return connection


def seed_job(schema: str, job_id: str = "r1:asr") -> None:
    with connect(schema) as connection:
        repository = SqlRepository(connection)
        repository.put_recording(Recording("r1", "/audio/r1.wav"))
        repository.put_job(ExecutionJob(job_id, "r1", "asr"))


def test_only_one_worker_can_claim_a_job(postgres_schema):
    seed_job(postgres_schema)

    def claim(worker: str):
        with connect(postgres_schema) as connection:
            return SqlRepository(connection).claim_next(worker, lease_seconds=60)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["worker-a", "worker-b"]))

    claimed = [job for job in results if job is not None]
    assert len(claimed) == 1
    assert claimed[0].worker in {"worker-a", "worker-b"}
    assert claimed[0].lease_id


def test_stale_worker_cannot_complete_after_reclaim(postgres_schema):
    seed_job(postgres_schema)

    with connect(postgres_schema) as connection:
        repository = SqlRepository(connection)
        first = repository.claim_job("r1:asr", "worker-a", lease_seconds=60)
        assert first is not None

    with connect(postgres_schema) as connection:
        connection.execute(
            "UPDATE execution_jobs SET lease_until = NOW() - INTERVAL '1 second' WHERE job_id = %s",
            ("r1:asr",),
        )
        connection.commit()
        second = SqlRepository(connection).claim_job("r1:asr", "worker-b", lease_seconds=60)
        assert second is not None
        assert second.lease_id != first.lease_id

    with connect(postgres_schema) as connection:
        repository = SqlRepository(connection)
        with pytest.raises(RuntimeError, match="lease completion rejected"):
            repository.complete("r1:asr", "worker-a", first.lease_id, "stale-artifact")

    with connect(postgres_schema) as connection:
        job = SqlRepository(connection).complete("r1:asr", "worker-b", second.lease_id, "fresh-artifact")
        assert job.status == "completed"
        assert job.artifact_id == "fresh-artifact"


def test_heartbeat_extends_only_live_owned_lease(postgres_schema):
    seed_job(postgres_schema)

    with connect(postgres_schema) as connection:
        repository = SqlRepository(connection)
        claimed = repository.claim_job("r1:asr", "worker-a", lease_seconds=60)
        assert claimed is not None

    with connect(postgres_schema) as connection:
        repository = SqlRepository(connection)
        refreshed = repository.heartbeat("r1:asr", "worker-a", claimed.lease_id, lease_seconds=120)
        assert refreshed.lease_until is not None
        assert refreshed.heartbeat_at is not None
        with pytest.raises(RuntimeError, match="lease heartbeat rejected"):
            repository.heartbeat("r1:asr", "worker-b", claimed.lease_id, lease_seconds=120)


def test_expired_lease_recovery_requeues_job(postgres_schema):
    seed_job(postgres_schema)

    with connect(postgres_schema) as connection:
        repository = SqlRepository(connection)
        claimed = repository.claim_job("r1:asr", "worker-a", lease_seconds=60)
        assert claimed is not None
        connection.execute(
            "UPDATE execution_jobs SET lease_until = NOW() - INTERVAL '1 second' WHERE job_id = %s",
            ("r1:asr",),
        )
        connection.commit()
        retried, failed = repository.recover_stale(max_attempts=3)
        assert (retried, failed) == (1, 0)

    with connect(postgres_schema) as connection:
        job = SqlRepository(connection).get_job("r1:asr")
        assert job is not None
        assert job.status == "retry"
        assert job.worker is None
        assert job.lease_id is None
