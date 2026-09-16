"""Consume exchange jobs from a mounted Colab Drive workspace."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (SRC_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from transcribe_intelligence.artifact_resolver import ArtifactResolver
from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope, ResultEnvelope

try:
    from .colab_inference import InferenceConfig, make_processor
    from .colab_speaker_embeddings import EmbeddingConfig, extract_and_persist
except ImportError:
    from colab_inference import InferenceConfig, make_processor
    from colab_speaker_embeddings import EmbeddingConfig, extract_and_persist


def claim_request(exchange: FileExchange, job_id: str) -> Path:
    source = exchange.requests / f"{job_id}.json"
    processing = exchange.root / "processing"
    processing.mkdir(parents=True, exist_ok=True)
    target = processing / source.name
    if not source.is_file():
        raise FileNotFoundError(source)
    source.replace(target)
    return target

