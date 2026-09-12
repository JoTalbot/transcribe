"""Submit manifest-backed execution jobs to a Drive-compatible exchange."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from transcribe_intelligence.exchange import FileExchange, JobEnvelope
from transcribe_intelligence.job_store import JobStore


def load_manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("recordings"), list):
        raise ValueError("manifest must contain a recordings list")
    return payload


def submit(manifest: dict[str, object], exchange: FileExchange, jobs: JobStore, recording: str | None = None) -> int:
    count = 0
    for item in manifest["recordings"]:
        if not isinstance(item, dict):
            continue
        recording_id = str(item.get("recording_id", ""))
        source_path = str(item.get("path", ""))
        if not recording_id or not source_path or (recording and recording_id != recording):
            continue
        for stage in ("asr", "diarization"):
            job_id = f"{recording_id}:{stage}"
            job = jobs.get(job_id)
            if job and job.status == "completed":
                continue
            exchange.put_request(JobEnvelope(job_id, recording_id, stage, input_path=source_path))
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--exchange", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--recording")
    args = parser.parse_args()
    count = submit(load_manifest(args.manifest.resolve()), FileExchange(args.exchange.resolve()), JobStore(args.jobs.resolve()), args.recording)
    print(f"Submitted exchange requests: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
