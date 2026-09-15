from pathlib import Path

import pytest

from scripts.oracle_worker import run_forever


def test_oracle_worker_runs_cycle_then_stops(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"recordings": []}', encoding="utf-8")
    calls: list[tuple[Path, str, str, int, None]] = []
    seen = []

    def dispatch(payload, exchange, database_url, worker, max_attempts, recording):
        calls.append((exchange.root, database_url, worker, max_attempts, recording))
        seen.append(True)
        return 0

    run_forever(
        manifest,
        tmp_path / "exchange",
        "postgresql://test",
        "oracle-test",
        4,
        10,
        stop=lambda: bool(seen),
        dispatch_fn=dispatch,
        sleep_fn=lambda _: pytest.fail("worker should stop after first cycle"),
    )

    assert calls == [(tmp_path / "exchange", "postgresql://test", "oracle-test", 4, None)]


def test_oracle_worker_rejects_non_positive_interval(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"recordings": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="positive"):
        run_forever(
            manifest,
            tmp_path / "exchange",
            "postgresql://test",
            "oracle-test",
            3,
            0,
        )
