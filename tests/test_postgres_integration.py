from __future__ import annotations

import os
from pathlib import Path
import threading
import time

import pytest

from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.sql_repository import SqlRepository


DATABASE_URL = os.getenv("TRANSCRIBE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TRANSCRIBE_TEST_DATABASE_URL is not configured")


@pytest.fixture()
def postgres_database():
    psycopg = pytest.importorskip("psycopg")
    connection = psycopg.connect(DATABASE_URL)
    connection.autocommit = True
    migrations = Path(__file__).parents[1] / "migrations"
    with connection.cursor() as cursor:
        for path in sorted(migrations.glob("*.sql")):
            cursor.execute(path.read_text(encoding="utf-8"))
        cursor.execute("TRUNCATE TABLE evidence, artifacts, execution_jobs, recordings CASCADE")
    connection.close()
    yield psycopg
    connection = psycopg.connect(DATABASE_URL)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE evidence, artifacts, execution_jobs, recordings CASCADE")
    connection.close()


def _repository(psycopg) -> SqlRepository:
    return SqlRepository(psycopg.connect(DATABASE_URL))


def _seed(repo: SqlRepository, job_id: str = "r:asr") -> None:
    from transcribe_intelligence.repository import Recording

    repo.put_recording(Recording("r", "/audio/r.wav"))
    repo.put_job(ExecutionJob(job_id, "r", "asr"))


def test_two_workers_cannot_claim_the_same_job(postgres_database) -> None:
    repo = _repository(postgres_database)
    _seed(repo)
    repo.connection.close()

    barrier = threading.Barrier(2)
    results: list[tuple[str, str | None]] = []
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        local = _repository(postgres_database)
        try:
            barrier.wait(timeout=5)
            job = local.claim_job("r:asr", name, lease_seconds=30)
            results.append((name, job.lease_id if job else None))
        except BaseException as exc:
            errors.append(exc)
        finally:
            local.connection.close()

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("worker-a", "worker-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert sorted(item[1] is not None for item in results) == [False, True]
    claimed = _repository(postgres_database).get_job("r:asr")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt == 1


def test_reclaimed_lease_rejects_stale_worker_completion(postgres_database) -> None:
    first = _repository(postgres_database)
    _seed(first)
    claimed_a = first.claim_job("r:asr", "worker-a", lease_seconds=1)
    assert claimed_a is not None and claimed_a.lease_id
    first.connection.close()

    time.sleep(1.2)
    second = _repository(postgres_database)
    claimed_b = second.claim_job("r:asr", "worker-b", lease_seconds=30)
    assert claimed_b is not None and claimed_b.lease_id != claimed_a.lease_id

    with pytest.raises(RuntimeError, match="lease completion rejected"):
        second.complete("r:asr", "worker-a", claimed_a.lease_id, "stale-artifact")

    done = second.complete("r:asr", "worker-b", claimed_b.lease_id, "fresh-artifact")
    assert done.status == "completed"
    assert done.artifact_id == "fresh-artifact"
    second.connection.close()


def test_expired_lease_is_recovered_to_retry(postgres_database) -> None:
    repo = _repository(postgres_database)
    _seed(repo)
    claimed = repo.claim_job("r:asr", "worker-a", lease_seconds=1)
    assert claimed is not None
    repo.connection.close()

    time.sleep(1.2)
    recovery = _repository(postgres_database)
    assert recovery.recover_stale(max_attempts=3) == (1, 0)
    recovered = recovery.get_job("r:asr")
    assert recovered is not None
    assert recovered.status == "retry"
    assert recovered.worker is None
    assert recovered.lease_id is None
    recovery.connection.close()
