"""Apply completed or failed exchange results to the canonical repository."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.exchange import ExchangeError, FileExchange
from transcribe_intelligence.repository import InMemoryRepository
from transcribe_intelligence.result_service import apply_result


def apply_exchange_results(exchange: FileExchange, repository: InMemoryRepository) -> int:
    """Apply all result envelopes, returning the number of state changes."""
    changed = 0
    for path in sorted(exchange.results.glob("*.json")):
        try:
            result = exchange.get_result(path.stem)
            changed += int(apply_result(repository, result))
        except (ExchangeError, KeyError, ValueError) as exc:
            raise RuntimeError(f"cannot apply exchange result {path.name}: {exc}") from exc
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", type=Path, default=Path("exchange"))
    args = parser.parse_args()
    repository = InMemoryRepository()
    changed = apply_exchange_results(FileExchange(args.exchange), repository)
    print(f"Applied exchange results: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
