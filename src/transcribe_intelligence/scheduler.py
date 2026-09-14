"""Deterministic multi-recording scheduler built on the repository boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .exchange import FileExchange
from .recovery import RecoveryPolicy, recover_job
from .repository import Repository
from .exchange_coordinator import Dispatch, ExchangeCoordinator


@dataclass(frozen=True, slots=True)
class ScheduleReport:
    recovered: int
    failed: int
    dispatched: int
    results_applied: int


class Scheduler:
    """Consume results, recover stale work, and dispatch ready recordings."""

    def __init__(self, repository: Repository, exchange: FileExchange, policy: RecoveryPolicy | None = None):
        self.repository = repository
        self.exchange = exchange
        self.policy = policy or RecoveryPolicy()
        self.coordinator = ExchangeCoordinator(repository, exchange)

    def recover(self, recording_ids: Iterable[str], now=None) -> tuple[int, int]:
        """Recover stale work through the DB lease boundary when available."""
        recover_stale = getattr(self.repository, "recover_stale", None)
        if callable(recover_stale) and now is None:
            return recover_stale(self.policy.max_attempts)
        recovered = failed = 0
        for recording_id in sorted(set(recording_ids)):
            for job in self.repository.list_jobs(recording_id):
                updated = recover_job(job, self.policy, now=now)
                if updated == job:
                    continue
                self.repository.update_job(updated)
                if updated.status == "failed":
                    failed += 1
                else:
                    recovered += 1
        return recovered, failed

    def run_once(self, recording_ids: Iterable[str], worker: str = "colab", now=None) -> tuple[ScheduleReport, list[Dispatch]]:
        """Run one safe cycle: consume results before reclaiming stale work."""
        ids = sorted(set(recording_ids))
        applied = self.coordinator.apply_results()
        recovered, failed = self.recover(ids, now=now)
        dispatches: list[Dispatch] = []
        for recording_id in ids:
            dispatches.extend(self.coordinator.dispatch_ready(recording_id, worker=worker))
        return ScheduleReport(recovered, failed, len(dispatches), applied), dispatches
