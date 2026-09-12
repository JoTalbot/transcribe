"""Build, persist, and inspect a resumable execution queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.planner import plan_from_manifest
from transcribe_intelligence.queue import enqueue
from transcribe_intelligence.job_store import JobStore
from transcribe_intelligence.state_store import StateStore


def load_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path("state/pipeline.json"))
    parser.add_argument("--jobs", type=Path, default=Path("state/jobs.json"))
    parser.add_argument("--recording")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest.expanduser().resolve())
    state = StateStore(args.state.expanduser().resolve())
    items = plan_from_manifest(manifest, state)
    if args.recording:
        items = [item for item in items if item.recording_id == args.recording]

    print(f"Planned stages: {len(items)}")
    if args.plan_only:
        for item in items:
            print(f"{item.recording_id}\t{item.stage.value}\t{item.status}")
        return 0

    jobs = enqueue(items, JobStore(args.jobs.expanduser().resolve()))
    print(f"Queued jobs: {len(jobs)}")
    for job in jobs:
        print(f"{job.job_id}\t{job.status}\tattempt={job.attempt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
