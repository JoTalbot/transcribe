# Worker result propagation

Worker results are applied through `transcribe_intelligence.result_service.apply_result`.

The repository boundary exposes an explicit `update_job` operation. Result application is idempotent: replaying the same terminal result is a no-op, while conflicting terminal results are rejected. A completed result must include an artifact ID.
