"""Build, persist, and inspect the canonical PostgreSQL execution queue."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.job_store import ExecutionJob, stable_job_id
from transcribe_intelligence.pipeline_contract import Stage
from transcribe_intelligence.repository import Recording
from transcribe_intelligence.sql_repository import SqlRepository


def load_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def manifest_recordings(manifest: dict[str, object]) -> list[tuple[str, str]]:
    records = manifest.get("recordings")
    if not isinstance(records, list):
        raise ValueError("manifest recordings must be a list")
    result: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("manifest recording must be an object")
        recording_id = record.get("recording_id")
        path = record.get("path")
        if not isinstance(recording_id, str) or not recording_id.strip():
            raise ValueError("manifest recording_id must be a non-empty string")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"manifest path missing for {recording_id}")
        if recording_id in seen and seen[recording_id] != path:
            raise ValueError(f"duplicate recording_id with conflicting paths: {recording_id}")
        if recording_id not in seen:
            seen[recording_id] = path
            result.append((recording_id, path))
    return result


def seed_manifest(repository: SqlRepository, manifest: dict[str, object], recording: str | None) -> list[ExecutionJob]:
    recordings = manifest_recordings(manifest)
    if recording:
        recordings = [item for item in recordings if item[0] == recording]
        if not recordings:
            raise ValueError(f"recording {recording} is absent from manifest")

    seeded: list[ExecutionJob] = []
    for recording_id, input_path in recordings:
        existing_recording = repository.get_recording(recording_id)
        if existing_recording is not None and existing_recording.input_path != input_path:
            raise ValueError(
                f"canonical path mismatch for {recording_id}: "
                f"database={existing_recording.input_path!r}, manifest={input_path!r}"
            )
        repository.put_recording(Recording(recording_id, input_path))
        for stage in Stage:
            job = repository.put_job(ExecutionJob(stable_job_id(recording_id, stage.value), recording_id, stage.value))
            seeded.append(job)
    return seeded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--recording")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("TRANSCRIBE_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or TRANSCRIBE_DATABASE_URL is required")

    manifest = load_manifest(args.manifest.expanduser().resolve())
    import psycopg

    with psycopg.connect(args.database_url) as connection:
        repository = SqlRepository(connection)
        jobs = seed_manifest(repository, manifest, args.recording)
        if args.plan_only:
            for job in jobs:
                print(f"{job.recording_id}\t{job.stage}\t{job.status}")
            return 0

    print(f"Canonical PostgreSQL jobs: {len(jobs)}")
    for job in jobs:
        print(f"{job.job_id}\t{job.status}\tattempt={job.attempt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
