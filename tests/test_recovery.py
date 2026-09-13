from datetime import datetime, timedelta, timezone

from transcribe_intelligence.job_store import ExecutionJob
from transcribe_intelligence.recovery import RecoveryPolicy, recover_job


def job(attempt=1, status="running"):
    now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    return ExecutionJob("j1", "r1", "asr", status, attempt, updated_at=(now - timedelta(hours=2)).isoformat())


def test_stale_running_job_becomes_retry():
    now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    recovered = recover_job(job(), RecoveryPolicy(max_attempts=3, stale_after_seconds=3600), now)
    assert recovered.status == "retry"
    assert recovered.attempt == 1


def test_retry_limit_turns_stale_job_failed():
    now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    recovered = recover_job(job(attempt=3), RecoveryPolicy(max_attempts=3, stale_after_seconds=3600), now)
    assert recovered.status == "failed"
    assert "retry limit" in (recovered.error or "")


def test_fresh_running_job_is_unchanged():
    now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    fresh = ExecutionJob("j1", "r1", "asr", "running", 1, updated_at=(now - timedelta(minutes=5)).isoformat())
    assert recover_job(fresh, RecoveryPolicy(stale_after_seconds=3600), now) == fresh


def test_non_running_job_is_unchanged():
    queued = job(status="queued")
    assert recover_job(queued, RecoveryPolicy()) == queued
