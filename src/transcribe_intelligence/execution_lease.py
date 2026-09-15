"""PostgreSQL execution-lease contract for concurrent workers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid


@dataclass(frozen=True, slots=True)
class Lease:
    job_id: str
    worker: str
    lease_id: str
    lease_until: datetime


def new_lease(job_id: str, worker: str, lease_seconds: int = 3600) -> Lease:
    if not job_id or not worker:
        raise ValueError("job_id and worker are required")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = datetime.now(timezone.utc)
    return Lease(job_id, worker, uuid.uuid4().hex, now + timedelta(seconds=lease_seconds))


CLAIM_SQL = """
WITH candidate AS (
    SELECT job_id FROM execution_jobs
    WHERE status IN ('queued', 'retry')
      AND (lease_until IS NULL OR lease_until <= NOW())
       OR status = 'running' AND lease_until <= NOW()
    ORDER BY recording_id, stage, job_id FOR UPDATE SKIP LOCKED LIMIT 1
)
UPDATE execution_jobs AS j
SET status = 'running', attempt = j.attempt + 1, worker = %s,
    lease_id = %s, lease_until = NOW() + (%s * INTERVAL '1 second'),
    heartbeat_at = NOW(), error = NULL, updated_at = NOW()
FROM candidate WHERE j.job_id = candidate.job_id
RETURNING j.job_id, j.recording_id, j.stage, j.status, j.attempt,
          j.artifact_id, j.worker, j.error, j.updated_at, j.lease_id, j.lease_until, j.heartbeat_at
"""

CLAIM_JOB_SQL = """
UPDATE execution_jobs
SET status = 'running', attempt = attempt + 1, worker = %s,
    lease_id = %s, lease_until = NOW() + (%s * INTERVAL '1 second'),
    heartbeat_at = NOW(), error = NULL, updated_at = NOW()
WHERE job_id = %s
  AND (
      status IN ('queued', 'retry')
      AND (lease_until IS NULL OR lease_until <= NOW())
      OR status = 'running' AND lease_until <= NOW()
  )
RETURNING job_id, recording_id, stage, status, attempt,
          artifact_id, worker, error, updated_at, lease_id, lease_until, heartbeat_at
"""

HEARTBEAT_SQL = """
UPDATE execution_jobs
SET lease_until = NOW() + (%s * INTERVAL '1 second'), heartbeat_at = NOW(), updated_at = NOW()
WHERE job_id = %s AND status = 'running' AND worker = %s AND lease_id = %s AND lease_until > NOW()
RETURNING job_id, lease_until, heartbeat_at
"""

COMPLETE_SQL = """
UPDATE execution_jobs
SET status = 'completed', artifact_id = %s, lease_id = NULL, lease_until = NULL,
    heartbeat_at = NOW(), updated_at = NOW(), error = NULL
WHERE job_id = %s AND status = 'running' AND worker = %s AND lease_id = %s AND lease_until > NOW()
RETURNING job_id
"""

FAIL_SQL = """
UPDATE execution_jobs
SET status = 'failed', error = %s, lease_id = NULL, lease_until = NULL,
    heartbeat_at = NOW(), updated_at = NOW()
WHERE job_id = %s AND status = 'running' AND worker = %s AND lease_id = %s AND lease_until > NOW()
RETURNING job_id
"""

RECOVER_STALE_SQL = """
WITH stale AS (
    SELECT job_id, attempt FROM execution_jobs
    WHERE status = 'running' AND lease_until IS NOT NULL AND lease_until <= NOW()
    FOR UPDATE SKIP LOCKED
)
UPDATE execution_jobs AS j
SET status = CASE WHEN stale.attempt >= %s THEN 'failed' ELSE 'retry' END,
    error = CASE WHEN stale.attempt >= %s
        THEN 'worker lease expired; retry limit reached'
        ELSE 'worker lease expired; scheduled for retry' END,
    worker = NULL, lease_id = NULL, lease_until = NULL,
    heartbeat_at = NOW(), updated_at = NOW()
FROM stale WHERE j.job_id = stale.job_id
RETURNING j.job_id, j.status
"""
