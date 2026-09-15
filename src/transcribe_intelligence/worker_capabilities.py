"""Worker capability profiles used to prevent unsupported stage dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .pipeline_contract import PipelineStage


@dataclass(frozen=True)
class WorkerCapabilities:
    """Immutable declaration of the pipeline stages a worker can execute."""

    worker: str
    stages: frozenset[PipelineStage]

    def supports(self, stage: PipelineStage | str) -> bool:
        value = stage if isinstance(stage, PipelineStage) else PipelineStage(stage)
        return value in self.stages


COLAB_GPU = WorkerCapabilities(
    worker="colab-gpu",
    stages=frozenset(
        {
            PipelineStage.ASR,
            PipelineStage.DIARIZATION,
            PipelineStage.EMBEDDINGS,
        }
    ),
)

ORACLE_LOCAL = WorkerCapabilities(
    worker="oracle-local",
    stages=frozenset({PipelineStage.INGEST, PipelineStage.NORMALIZE}),
)


DEFAULT_WORKER_CAPABILITIES: dict[str, WorkerCapabilities] = {
    COLAB_GPU.worker: COLAB_GPU,
    ORACLE_LOCAL.worker: ORACLE_LOCAL,
}


def make_capabilities(worker: str, stages: Iterable[PipelineStage | str]) -> WorkerCapabilities:
    """Build a validated immutable capability declaration."""

    normalized = frozenset(
        stage if isinstance(stage, PipelineStage) else PipelineStage(stage)
        for stage in stages
    )
    if not worker.strip():
        raise ValueError("worker must be non-empty")
    return WorkerCapabilities(worker=worker, stages=normalized)
