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


def test_oracle_worker_retries_after_transient_cycle_failure(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"recordings": []}', encoding="utf-8")
    attempts = 0
    sleeps: list[float] = []
    errors: list[str] = []

    def dispatch(*_args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary database outage")
        return 0

    run_forever(
        manifest,
        tmp_path / "exchange",
        "postgresql://test",
        "oracle-test",
        3,
        10,
        stop=lambda: attempts >= 2,
        dispatch_fn=dispatch,
        sleep_fn=sleeps.append,
        log_fn=errors.append,
    )

    assert attempts == 2
    assert errors == ["Oracle worker cycle failed: temporary database outage"]
    assert sleeps == []


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
