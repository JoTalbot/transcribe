"""Apply exchange results to the canonical PostgreSQL repository."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.exchange import FileExchange
from transcribe_intelligence.exchange_coordinator import ExchangeCoordinator
from transcribe_intelligence.sql_repository import SqlRepository


def apply_exchange_results(exchange: FileExchange, repository: SqlRepository) -> int:
    """Apply exchange results through the lease-aware canonical repository."""
    return ExchangeCoordinator(repository, exchange, verify_artifacts=True).apply_results()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", type=Path, default=Path("exchange"))
    parser.add_argument("--database-url", default=os.getenv("TRANSCRIBE_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or TRANSCRIBE_DATABASE_URL is required")

    import psycopg

    with psycopg.connect(args.database_url) as connection:
        repository = SqlRepository(connection)
        changed = apply_exchange_results(
            FileExchange(args.exchange.expanduser().resolve()), repository
        )
    print(f"Applied exchange results: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
