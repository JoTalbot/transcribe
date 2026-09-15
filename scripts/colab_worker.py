"""Run the Colab browser adapter periodically on a persistent worker host.

This worker never stores or transfers Google credentials. Authentication remains
inside a local Playwright persistent profile owned by the worker machine.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.colab_runner import run


async def worker(
    url: str,
    profile: Path,
    timeout: int,
    interval: int,
    headless: bool,
) -> None:
    while True:
        try:
            await run(url, profile, timeout, headless)
        except Exception as exc:
            print(f"Colab worker iteration failed: {exc}", flush=True)
        print(f"Sleeping {interval}s before the next Colab check.", flush=True)
        await asyncio.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebook-url",
        default=os.getenv(
            "TRANSCRIBE_COLAB_URL",
            "https://colab.research.google.com/github/JoTalbot/transcribe/blob/main/notebooks/transcribe_pipeline.ipynb",
        ),
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("TRANSCRIBE_COLAB_PROFILE", ".auth/colab"),
    )
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.getenv("TRANSCRIBE_COLAB_INTERVAL", "900")),
        help="Seconds between worker iterations (default: 900).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use Chromium headless mode; visible mode is more reliable for Google UI/auth.",
    )
    args = parser.parse_args()

    if args.interval < 60:
        parser.error("--interval must be at least 60 seconds")

    asyncio.run(
        worker(
            args.notebook_url,
            Path(args.profile).expanduser(),
            args.timeout,
            args.interval,
            args.headless,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
