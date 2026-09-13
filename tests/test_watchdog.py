from pathlib import Path

import pytest

from transcribe_intelligence.repository import InMemoryRepository, Recording
from transcribe_intelligence.scheduler import Scheduler, ScheduleReport
from transcribe_intelligence.watchdog import SchedulerWatchdog
from transcribe_intelligence.exchange import FileExchange
from transcribe_intelligence.job_store import ExecutionJob, stable_job_id


def make_scheduler(tmp_path: Path) -> Scheduler:
    repository = InMemoryRepository()
    repository.put_recording(Recording("r1", "/input/r1.wav"))
    repository.put_job(ExecutionJob(stable_job_id("r1", "ingest"), "r1", "ingest"))
    return Scheduler(repository, FileExchange(tmp_path / "exchange"))


def test_watchdog_orders_recordings_once(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    watchdog = SchedulerWatchdog(scheduler, ["r1"], worker="colab-1")
    cycle = watchdog.cycle()
    assert isinstance(cycle.report, ScheduleReport)
    assert [item.job_id for item in cycle.dispatches] == ["r1:ingest"]


def test_watchdog_rejects_negative_interval(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    watchdog = SchedulerWatchdog(scheduler, ["r1"])
    with pytest.raises(ValueError, match="non-negative"):
        watchdog.run_forever(interval_seconds=-1)


def test_watchdog_stop_hook_can_end_after_first_cycle(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    watchdog = SchedulerWatchdog(scheduler, ["r1"])
    seen = []
    watchdog.run_forever(
        interval_seconds=0,
        stop=lambda: bool(seen),
        on_cycle=seen.append,
        sleep_fn=lambda _: None,
    )
    assert len(seen) == 1
