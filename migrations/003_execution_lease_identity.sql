-- Unique lease identity prevents a stale worker from completing a reclaimed job.
ALTER TABLE execution_jobs
    ADD COLUMN IF NOT EXISTS lease_id TEXT;

CREATE INDEX IF NOT EXISTS execution_jobs_lease_identity_idx
    ON execution_jobs (job_id, lease_id);
