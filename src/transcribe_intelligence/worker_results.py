"""Worker-result application boundary."""
from __future__ import annotations

from .exchange import ResultEnvelope
from .repository import Repository
from .result_service import apply_result


def apply_worker_result(repository: Repository, result: ResultEnvelope) -> bool:
    """Apply a transport result without coupling workers to persistence."""
    return apply_result(repository, result)
