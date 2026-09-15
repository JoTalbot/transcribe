"""Persistent Oracle-side scheduler for the PostgreSQL/exchange execution path.

Oracle is the durable orchestrator, not the GPU inference worker. Each cycle opens
its own PostgreSQL connection, consumes exchange results, reclaims expired leases,
and dispatches ready jobs. No legacy JobStore state is used here.
"""
from __future__ import annotations

import argparse
import os
import signal
import time
from pathlib import Path
from types import FrameType
from typing import Callable

from scripts.submit_exchange_jobs import dispatch_manifest, load_manifest
from transcribe_intelligence.exchange import FileExchange


class ShutdownFlag:
    """Signal-safe stop flag shared by the daemon loop."""

    def __init__(self) -> None:
        self.requested = False

    def request(self, _signum: int, _frame: FrameType | None) -> None:
        self.requested = True


def run_forever(
    manifest: Path,
    exchange: Path,
    database_url: str,
    worker: str,
    max_attempts: int,
    interval_seconds: float,
    stop: Callable[[], bool] | None = None,
    dispatch_fn: Callable[..., int] = dispatch_manifest,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Run safe scheduling cycles with a fresh DB connection per cycle."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    stop_fn = stop or (lambda: False)
    payload = load_manifest(manifest)
    while not stop_fn():
        started = time.monotonic()
        dispatch_fn(payload, FileExchange(exchange), database_url, worker, max_attempts, None)
        if stop_fn():
            break
        elapsed = max(0.0, time.monotonic() - started)
        sleep_fn(max(0.0, interval_seconds - elapsed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--exchange", type=Path, default=Path("exchange"))
    parser.add_argument("--worker", default=os.getenv("TRANSCRIBE_WORKER", "oracle-1"))
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--database-url", default=os.getenv("TRANSCRIBE_DATABASE_URL"))
    parser.add_argument("--once", action="store_true", help="run one scheduling cycle and exit")
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url or TRANSCRIBE_DATABASE_URL is required")
    if not args.worker.strip():
        parser.error("--worker must not be empty")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be positive")
    if args.interval <= 0:
        parser.error("--interval must be positive")

    manifest = args.manifest.expanduser().resolve()
    exchange = args.exchange.expanduser().resolve()
    if args.once:
        dispatch_manifest(
            load_manifest(manifest),
            FileExchange(exchange),
            args.database_url,
            args.worker,
            args.max_attempts,
            None,
        )
        return 0

    shutdown = ShutdownFlag()
    previous_int = signal.signal(signal.SIGINT, shutdown.request)
    previous_term = signal.signal(signal.SIGTERM, shutdown.request)
    try:
        run_forever(
            manifest,
            exchange,
            args.database_url,
            args.worker,
            args.max_attempts,
            args.interval,
            stop=lambda: shutdown.requested,
        )
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
