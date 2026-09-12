"""Consume filesystem exchange jobs from a mounted Colab Drive workspace.

The worker is transport-only: model inference remains in the notebook/runtime.
It claims a job by moving the request into a processing directory, invokes an
injected processor, and atomically publishes a result envelope.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Callable

from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope, ResultEnvelope

Processor = Callable[[JobEnvelope], ResultEnvelope]


def claim_request(exchange: FileExchange, job_id: str) -> Path:
    """Move a queued request into processing atomically on one filesystem."""
    source = exchange.requests / f"{job_id}.json"
    processing = exchange.root / "processing"
    processing.mkdir(parents=True, exist_ok=True)
    target = processing / source.name
    if not source.is_file():
        raise FileNotFoundError(source)
    source.replace(target)
    return target


def read_claimed(path: Path) -> JobEnvelope:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        request = JobEnvelope(**payload)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ExchangeError(f"invalid claimed request {path}") from exc
    if not request.job_id.strip() or not request.recording_id.strip() or not request.stage.strip():
        raise ExchangeError(f"claimed request {path} contains empty required fields")
    return request


def process_one(exchange: FileExchange, job_id: str, processor: Processor) -> ResultEnvelope:
    """Claim, process and publish one request; failures become retryable results."""
    path = claim_request(exchange, job_id)
    request = read_claimed(path)
    try:
        result = processor(request)
        if result.job_id != request.job_id:
            raise ExchangeError("processor returned a different job_id")
        exchange.put_result(result)
        return result
    except Exception as exc:  # noqa: BLE001
        result = ResultEnvelope(request.job_id, "failed", error=str(exc))
        exchange.put_result(result)
        return result
    finally:
        path.unlink(missing_ok=True)


def dry_run_processor(request: JobEnvelope) -> ResultEnvelope:
    """Deterministic processor used to verify exchange plumbing."""
    return ResultEnvelope(request.job_id, "completed", artifact_id=f"dry-run:{request.job_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.getenv("TRANSCRIBE_EXCHANGE_ROOT", "/content/drive/MyDrive/transcribe/exchange"))
    parser.add_argument("--poll", type=int, default=int(os.getenv("TRANSCRIBE_EXCHANGE_POLL", "30")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.poll < 1:
        parser.error("--poll must be at least 1 second")

    exchange = FileExchange(Path(args.root))
    while True:
        requests = exchange.list_requests()
        for path in requests:
            try:
                result = process_one(exchange, path.stem, dry_run_processor)
                print(f"{result.job_id}\t{result.status}\t{result.artifact_id or result.error}", flush=True)
            except (FileNotFoundError, ExchangeError) as exc:
                print(f"exchange iteration failed: {exc}", flush=True)
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
