"""Worker capability profiles used to prevent unsupported stage dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .pipeline_contract import Stage


@dataclass(frozen=True, slots=True)
class WorkerCapabilities:
    """Immutable declaration of the pipeline stages a worker can execute."""

    worker: str
    stages: frozenset[Stage]

    def supports(self, stage: Stage | str) -> bool:
        value = stage if isinstance(stage, Stage) else Stage(stage)
        return value in self.stages


COLAB_GPU = WorkerCapabilities(
    worker="colab-gpu",
    stages=frozenset({Stage.ASR, Stage.DIARIZATION, Stage.EMBEDDINGS}),
)

ORACLE_LOCAL = WorkerCapabilities(
    worker="oracle-local",
    stages=frozenset({Stage.INGEST, Stage.NORMALIZE}),
)

DEFAULT_WORKER_CAPABILITIES: dict[str, WorkerCapabilities] = {
    COLAB_GPU.worker: COLAB_GPU,
    ORACLE_LOCAL.worker: ORACLE_LOCAL,
}

DEFAULT_STAGE_WORKERS: dict[Stage, str] = {
    Stage.INGEST: ORACLE_LOCAL.worker,
    Stage.NORMALIZE: ORACLE_LOCAL.worker,
    Stage.ASR: COLAB_GPU.worker,
    Stage.DIARIZATION: COLAB_GPU.worker,
    Stage.EMBEDDINGS: COLAB_GPU.worker,
}


def make_capabilities(worker: str, stages: Iterable[Stage | str]) -> WorkerCapabilities:
    """Build a validated immutable capability declaration."""

    if not worker.strip():
        raise ValueError("worker must be non-empty")
    normalized = frozenset(
        stage if isinstance(stage, Stage) else Stage(stage) for stage in stages
    )
    return WorkerCapabilities(worker=worker, stages=normalized)
