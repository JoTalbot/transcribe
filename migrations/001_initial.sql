-- Canonical persistence schema for transcription orchestration.
-- PostgreSQL 14+.

CREATE TABLE IF NOT EXISTS recordings (
    recording_id TEXT PRIMARY KEY,
    input_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS execution_jobs (
    job_id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(recording_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    artifact_id TEXT,
    worker TEXT,
    error TEXT,
    updated_at TIMESTAMPTZ,
    UNIQUE (recording_id, stage)
);

CREATE INDEX IF NOT EXISTS execution_jobs_recording_idx
    ON execution_jobs (recording_id, stage);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(recording_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    input_artifact_id TEXT,
    status TEXT NOT NULL,
    model_version TEXT,
    uri TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (recording_id, stage, artifact_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(recording_id) ON DELETE CASCADE,
    segment_id TEXT,
    start_seconds DOUBLE PRECISION NOT NULL CHECK (start_seconds >= 0),
    end_seconds DOUBLE PRECISION NOT NULL CHECK (end_seconds >= start_seconds),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    text TEXT NOT NULL,
    method TEXT NOT NULL,
    model_version TEXT
);

CREATE INDEX IF NOT EXISTS evidence_recording_time_idx
    ON evidence (recording_id, start_seconds, end_seconds);
