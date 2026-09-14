-- Recovery and dispatch use the explicit retry state between attempts.
ALTER TABLE execution_jobs
    DROP CONSTRAINT IF EXISTS execution_jobs_status_check;

ALTER TABLE execution_jobs
    ADD CONSTRAINT execution_jobs_status_check
    CHECK (status IN ('queued', 'running', 'retry', 'completed', 'failed'));

CREATE INDEX IF NOT EXISTS execution_jobs_retry_idx
    ON execution_jobs (status, attempt, updated_at)
    WHERE status = 'retry';
