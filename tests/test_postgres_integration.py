from __future__ import annotations

import os
from pathlib import Path
import threading
import time

import pytest

from transcribe_intelligence.exchange import FileExchange, ResultEnvelope
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.repository import Recording
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
    try:
        yield psycopg
    finally:
        connection = psycopg.connect(DATABASE_URL)
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE evidence, artifacts, execution_jobs, recordings CASCADE")
        finally:
            connection.close()


def _repository(psycopg) -> SqlRepository:
    connection = psycopg.connect(DATABASE_URL)
    connection.autocommit = True
    return SqlRepository(connection)


def _close_repository(repo: SqlRepository) -> None:
    repo.connection.rollback()
    repo.connection.close()


def _seed(repo: SqlRepository, job_id: str = "r:asr") -> None:
    repo.put_recording(Recording("r", "/audio/r.wav"))
    repo.put_job(ExecutionJob(job_id, "r", "asr"))


def _seed_exchange_pipeline(repo: SqlRepository) -> None:
    repo.put_recording(Recording("r", "/audio/r.wav"))
    repo.put_job(ExecutionJob("r:ingest", "r", "ingest"))
    repo.put_job(ExecutionJob("r:normalize", "r", "normalize"))
    repo.put_job(ExecutionJob("r:asr", "r", "asr"))


def _wait_for_reclaim(repo: SqlRepository, job_id: str, worker: str, timeout: float = 5.0) -> ExecutionJob:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        claimed = repo.claim_job(job_id, worker, lease_seconds=30)
        if claimed is not None:
            return claimed
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} was not reclaimed within {timeout:.1f}s")


def _wait_for_recovery(repo: SqlRepository, max_attempts: int, expected: tuple[int, int], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if repo.recover_stale(max_attempts=max_attempts) == expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"recovery did not return {expected} within {timeout:.1f}s")


def test_two_workers_cannot_claim_the_same_job(postgres_database) -> None:
    repo = _repository(postgres_database)
    try:
        _seed(repo)
    finally:
        _close_repository(repo)

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
            _close_repository(local)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("worker-a", "worker-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert sorted(item[1] is not None for item in results) == [False, True]
    claimed_repo = _repository(postgres_database)
    try:
        claimed = claimed_repo.get_job("r:asr")
        assert claimed is not None
        assert claimed.status == "running"
        assert claimed.attempt == 1
    finally:
        _close_repository(claimed_repo)


def test_reclaimed_lease_rejects_stale_worker_completion(postgres_database) -> None:
    first = _repository(postgres_database)
    try:
        _seed(first)
        claimed_a = first.claim_job("r:asr", "worker-a", lease_seconds=1)
        assert claimed_a is not None and claimed_a.lease_id
    finally:
        _close_repository(first)

    second = _repository(postgres_database)
    try:
        time.sleep(1.05)
        claimed_b = _wait_for_reclaim(second, "r:asr", "worker-b")
        assert claimed_b.lease_id != claimed_a.lease_id

        with pytest.raises(RuntimeError, match="lease completion rejected"):
            second.complete("r:asr", "worker-a", claimed_a.lease_id, "stale-artifact")

        done = second.complete("r:asr", "worker-b", claimed_b.lease_id, "fresh-artifact")
        assert done.status == "completed"
        assert done.artifact_id == "fresh-artifact"
    finally:
        _close_repository(second)


def test_heartbeat_extends_only_the_current_lease(postgres_database) -> None:
    repo = _repository(postgres_database)
    try:
        _seed(repo)
        claimed = repo.claim_job("r:asr", "worker-a", lease_seconds=1)
        assert claimed is not None and claimed.lease_id
        refreshed = repo.heartbeat("r:asr", "worker-a", claimed.lease_id, lease_seconds=30)
        assert refreshed.status == "running"
        assert refreshed.lease_id == claimed.lease_id
        assert refreshed.worker == "worker-a"

        with pytest.raises(RuntimeError, match="lease heartbeat rejected"):
            repo.heartbeat("r:asr", "worker-b", claimed.lease_id, lease_seconds=30)

        with pytest.raises(RuntimeError, match="lease heartbeat rejected"):
            repo.heartbeat("r:asr", "worker-a", "wrong-lease", lease_seconds=30)
    finally:
        _close_repository(repo)


def test_expired_lease_is_recovered_to_retry(postgres_database) -> None:
    repo = _repository(postgres_database)
    try:
        _seed(repo)
        claimed = repo.claim_job("r:asr", "worker-a", lease_seconds=1)
        assert claimed is not None
    finally:
        _close_repository(repo)

    recovery = _repository(postgres_database)
    try:
        time.sleep(1.05)
        _wait_for_recovery(recovery, max_attempts=3, expected=(1, 0))
        recovered = recovery.get_job("r:asr")
        assert recovered is not None
        assert recovered.status == "retry"
        assert recovered.worker is None
        assert recovered.lease_id is None
    finally:
        _close_repository(recovery)


def test_max_attempts_recovery_marks_job_failed(postgres_database) -> None:
    repo = _repository(postgres_database)
    try:
        _seed(repo)
        claimed = repo.claim_job("r:asr", "worker-a", lease_seconds=1)
        assert claimed is not None
    finally:
        _close_repository(repo)

    recovery = _repository(postgres_database)
    try:
        time.sleep(1.05)
        _wait_for_recovery(recovery, max_attempts=1, expected=(0, 1))
        failed = recovery.get_job("r:asr")
        assert failed is not None
        assert failed.status == "failed"
        assert failed.worker is None
        assert failed.lease_id is None
        assert failed.error
    finally:
        _close_repository(recovery)


def test_exchange_accepts_current_lease_and_quarantines_reclaimed_worker_result(postgres_database, tmp_path: Path) -> None:
    repository = _repository(postgres_database)
    try:
        _seed_exchange_pipeline(repository)
        exchange = FileExchange(tmp_path / "exchange")
        coordinator = ExchangeCoordinator(repository, exchange)

        first = coordinator.dispatch_ready("r", worker="worker-a")
        assert len(first) == 1
        request = exchange.get_request("r:ingest")
        assert request.worker == "worker-a"
        assert request.lease_id
        stale_lease = request.lease_id
        request_path = exchange.requests / "r:ingest.json"
        request_path.unlink()

        # ExchangeCoordinator uses the normal repository lease duration. Expire
        # it explicitly so this integration test is deterministic.
        with repository.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE execution_jobs SET lease_until = NOW() - INTERVAL '1 second' WHERE job_id = %s",
                ("r:ingest",),
            )
        reclaimed = _wait_for_reclaim(repository, "r:ingest", "worker-b")
        assert reclaimed.lease_id != stale_lease

        exchange.put_result(ResultEnvelope("r:ingest", "completed", artifact_id="stale", worker="worker-a", lease_id=stale_lease))
        assert coordinator.apply_results() == 0
        assert (exchange.results / "quarantine" / "r:ingest.json").exists()

        exchange.put_result(ResultEnvelope("r:ingest", "completed", artifact_id="fresh", worker="worker-b", lease_id=reclaimed.lease_id))
        assert coordinator.apply_results() == 1
        assert repository.get_job("r:ingest").status == "completed"
        assert repository.get_job("r:ingest").artifact_id == "fresh"
    finally:
        _close_repository(repository)
