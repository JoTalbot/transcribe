"""Materialize queued jobs as Drive/Colab exchange envelopes using manifest paths."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.exchange import FileExchange, JobEnvelope
from transcribe_intelligence.job_store import JobStore


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, default=Path("state/jobs.json"))
    parser.add_argument("--exchange", type=Path, default=Path("exchange"))
    parser.add_argument("--recording")
    args = parser.parse_args()

    paths = recording_paths(load_manifest(args.manifest.expanduser().resolve()))
    jobs = JobStore(args.jobs.expanduser().resolve()).load()
    exchange = FileExchange(args.exchange.expanduser().resolve())

    submitted = 0
    for job in sorted(jobs.values(), key=lambda item: item.job_id):
        if job.status not in {"queued", "retry"}:
            continue
        if args.recording and job.recording_id != args.recording:
            continue
        path = paths.get(job.recording_id)
        if path is None:
            raise ValueError(f"recording {job.recording_id} is absent from manifest")
        exchange.put_request(JobEnvelope(
            job_id=job.job_id,
            recording_id=job.recording_id,
            stage=job.stage,
            input_path=path,
        ))
        submitted += 1
        print(f"submitted {job.job_id}\t{path}")

    print(f"Submitted exchange jobs: {submitted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
