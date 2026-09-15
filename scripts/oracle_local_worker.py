"""Process Oracle-local ingest and normalize jobs from the shared exchange."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope, ResultEnvelope
from transcribe_intelligence.local_processors import LocalAudioProcessor

LOCAL_STAGES = {"ingest", "normalize"}


def _claim_local(exchange: FileExchange, job_id: str) -> Path | None:
    source = exchange.requests / f"{job_id}.json"
    processing = exchange.root / "processing"
    processing.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        return None
    request = exchange.get_request(job_id)
    if request.stage not in LOCAL_STAGES:
        return None
    target = processing / source.name
    try:
        source.replace(target)
    except FileNotFoundError:
        return None
    return target


def process_one(exchange: FileExchange, job_id: str, processor: LocalAudioProcessor) -> ResultEnvelope | None:
    path = _claim_local(exchange, job_id)
    if path is None:
        return None
    try:
        try:
            request = JobEnvelope(**__import__("json").loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise ExchangeError(f"invalid claimed local request {path}") from exc
        if not request.worker or not request.lease_id:
            raise ExchangeError(f"claimed request {path} is missing worker or lease_id")
        result = processor.process(request)
        if result.job_id != request.job_id:
            raise ExchangeError("local processor returned a different job_id")
        result = ResultEnvelope(
            result.job_id,
            result.status,
            result.artifact_id,
            result.error,
            request.worker,
            request.lease_id,
        )
        exchange.put_result(result)
        return result
    except Exception as exc:
        result = ResultEnvelope(
            request.job_id if "request" in locals() else job_id,
            "failed",
            error=str(exc),
            worker=request.worker if "request" in locals() else None,
            lease_id=request.lease_id if "request" in locals() else None,
        )
        exchange.put_result(result)
        return result
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default=os.getenv("TRANSCRIBE_EXCHANGE_ROOT", "exchange"))
    parser.add_argument("--poll", type=int, default=int(os.getenv("TRANSCRIBE_LOCAL_POLL", "5")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.poll < 1:
        parser.error("--poll must be at least 1 second")

    exchange = FileExchange(Path(args.exchange).expanduser())
    processor = LocalAudioProcessor(exchange.root / "artifacts")
    while True:
        for path in exchange.list_requests():
            try:
                result = process_one(exchange, path.stem, processor)
                if result is not None:
                    print(f"{result.job_id}\t{result.status}\t{result.artifact_id or result.error}", flush=True)
            except (ExchangeError, FileNotFoundError) as exc:
                print(f"local exchange iteration failed: {exc}", flush=True)
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
