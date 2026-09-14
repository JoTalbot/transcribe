-- Lease/retry fields for atomic PostgreSQL worker ownership.
ALTER TABLE execution_jobs
    ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS execution_jobs_lease_idx
    ON execution_jobs (status, lease_until);

-- Claiming a job must be performed transactionally by the application:
-- SELECT ... FOR UPDATE SKIP LOCKED, then UPDATE the selected row with
-- worker ownership and lease timestamps before COMMIT.

CREATE INDEX IF NOT EXISTS execution_jobs_dispatch_idx
    ON execution_jobs (recording_id, status, stage, job_id);
