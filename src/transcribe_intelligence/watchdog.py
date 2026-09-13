"""Deterministic watchdog/polling loop for the exchange scheduler."""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep
from typing import Callable, Iterable

from .exchange_coordinator import Dispatch
from .scheduler import ScheduleReport, Scheduler


@dataclass(frozen=True, slots=True)
class WatchdogCycle:
    report: ScheduleReport
    dispatches: tuple[Dispatch, ...]


class SchedulerWatchdog:
    """Run scheduler cycles with bounded, injectable polling behavior."""

    def __init__(self, scheduler: Scheduler, recording_ids: Iterable[str], worker: str = "colab"):
        self.scheduler = scheduler
        self.recording_ids = tuple(sorted(set(recording_ids)))
        self.worker = worker

    def cycle(self, now=None) -> WatchdogCycle:
        report, dispatches = self.scheduler.run_once(self.recording_ids, worker=self.worker, now=now)
        return WatchdogCycle(report, tuple(dispatches))

    def run_forever(
        self,
        interval_seconds: float = 5.0,
        stop: Callable[[], bool] | None = None,
        on_cycle: Callable[[WatchdogCycle], None] | None = None,
        sleep_fn: Callable[[float], None] = sleep,
        monotonic_fn: Callable[[], float] = monotonic,
    ) -> None:
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")
        stop_fn = stop or (lambda: False)
        while not stop_fn():
            started = monotonic_fn()
            result = self.cycle()
            if on_cycle:
                on_cycle(result)
            elapsed = max(0.0, monotonic_fn() - started)
            if stop_fn():
                break
            sleep_fn(max(0.0, interval_seconds - elapsed))
