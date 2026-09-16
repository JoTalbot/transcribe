"""Dispatch ready transcription jobs through the canonical lease-aware repository."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.exchange import FileExchange
from transcribe_intelligence.recovery import RecoveryPolicy
from transcribe_intelligence.scheduler import Scheduler
from transcribe_intelligence.sql_repository import SqlRepository


def load_manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def recording_paths(manifest: dict[str, object]) -> dict[str, str]:
    records = manifest.get("recordings")
    if not isinstance(records, list):
        raise ValueError("manifest must contain a recordings list")
    result: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("manifest recording must be an object")
        recording_id = record.get("recording_id")
        path = record.get("path")
        if not isinstance(recording_id, str) or not recording_id.strip():
            raise ValueError("manifest recording_id must be a non-empty string")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"manifest path missing for {recording_id}")
        if recording_id in result and result[recording_id] != path:
            raise ValueError(f"duplicate recording_id with conflicting paths: {recording_id}")
        result[recording_id] = path
    return result


def dispatch_manifest(manifest: dict[str, object], exchange: FileExchange, database_url: str, worker: str, max_attempts: int, recording: str | None) -> int:
    paths = recording_paths(manifest)
    recording_ids = [recording] if recording else sorted(paths)
    if recording and recording not in paths:
        raise ValueError(f"recording {recording} is absent from manifest")

    import psycopg

    with psycopg.connect(database_url) as connection:
        repository = SqlRepository(connection)
        for recording_id in recording_ids:
            stored = repository.get_recording(recording_id)
            if stored is None:
                raise ValueError(f"recording {recording_id} is absent from canonical PostgreSQL state")
            if stored.input_path != paths[recording_id]:
                raise ValueError(
                    f"manifest path mismatch for {recording_id}: "
                    f"manifest={paths[recording_id]!r}, database={stored.input_path!r}"
                )

        scheduler = Scheduler(
            repository,
            exchange,
            policy=RecoveryPolicy(max_attempts=max_attempts),
            verify_artifacts=True,
        )
        report, dispatches = scheduler.run_once(recording_ids, worker=worker)

    for dispatch in dispatches:
        print(f"submitted {dispatch.job_id}\t{dispatch.request_path}")
    print(
        f"Exchange cycle: results={report.results_applied} "
        f"recovered={report.recovered} failed={report.failed} dispatched={report.dispatched}"
    )
    return len(dispatches)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--exchange", type=Path, default=Path("exchange"))
    parser.add_argument("--recording")
    parser.add_argument("--worker", default=os.getenv("TRANSCRIBE_WORKER", "oracle-1"))
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--database-url", default=os.getenv("TRANSCRIBE_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or TRANSCRIBE_DATABASE_URL is required")
    if not args.worker.strip():
        parser.error("--worker must not be empty")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be positive")

    submitted = dispatch_manifest(
        load_manifest(args.manifest.expanduser().resolve()),
        FileExchange(args.exchange.expanduser().resolve()),
        args.database_url,
        args.worker,
        args.max_attempts,
        args.recording,
    )
    print(f"Submitted exchange jobs: {submitted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
