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


def read_claimed(path: Path) -> JobEnvelope:
    import json
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        request = JobEnvelope(**payload)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ExchangeError(f"invalid claimed request {path}") from exc
    if not request.job_id.strip() or not request.recording_id.strip() or not request.stage.strip():
        raise ExchangeError(f"claimed request {path} contains empty required fields")
    if not request.worker or not request.lease_id:
        raise ExchangeError(f"claimed request {path} is missing worker or lease_id")
    return request


def quarantine_claim(exchange: FileExchange, path: Path) -> Path:
    quarantine = exchange.results / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / path.name
    if target.exists():
        target = quarantine / f"{path.stem}.{time.time_ns()}{path.suffix}"
    path.replace(target)
    return target


def process_one(exchange: FileExchange, job_id: str, processor) -> ResultEnvelope:
    path = claim_request(exchange, job_id)
    try:
        request = read_claimed(path)
    except ExchangeError:
        quarantine_claim(exchange, path)
        raise
    try:
        result = processor(request)
        if result.job_id != request.job_id:
            raise ExchangeError("processor returned a different job_id")
        if result.status not in {"completed", "failed"}:
            raise ExchangeError(f"processor returned unsupported status: {result.status}")
        result = ResultEnvelope(result.job_id, result.status, result.artifact_id, result.error, request.worker, request.lease_id)
        exchange.put_result(result)
        return result
    except Exception as exc:
        result = ResultEnvelope(request.job_id, "failed", error=str(exc), worker=request.worker, lease_id=request.lease_id)
        exchange.put_result(result)
        return result
    finally:
        path.unlink(missing_ok=True)


def dry_run_processor(request: JobEnvelope) -> ResultEnvelope:
    """Return a deterministic result without loading GPU models or touching audio."""
    return ResultEnvelope(
        request.job_id,
        "completed",
        artifact_id=f"dry-run:{request.job_id}",
        worker=request.worker,
        lease_id=request.lease_id,
    )


def load_models(config: InferenceConfig, embedding_config: EmbeddingConfig):
    import torch
    from faster_whisper import WhisperModel
    from google.colab import userdata
    from pyannote.audio import Pipeline
    from speechbrain.inference.speaker import EncoderClassifier
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required")
    token = userdata.get("HUGGINGFACE_TOKEN")
    if not token:
        raise RuntimeError("Colab Secret HUGGINGFACE_TOKEN is required")
    whisper = WhisperModel(config.whisper_model, device="cuda", compute_type=config.compute_type)
    diarizer = Pipeline.from_pretrained(config.diarization_model, use_auth_token=token)
    diarizer.to(torch.device("cuda"))
    embedder = EncoderClassifier.from_hparams(source=embedding_config.model_name, savedir="/content/speechbrain_ecapa", run_opts={"device": "cuda"})
    return whisper, diarizer, embedder


def build_processor(input_dir: Path, output_dir: Path, whisper, diarizer, embedder, config: InferenceConfig, embedding_config: EmbeddingConfig):
    base_processor = make_processor(input_dir, output_dir, whisper, diarizer, config)
    from transcribe_intelligence.artifact_resolver import ArtifactResolver
    artifact_resolver = ArtifactResolver(output_dir)

    def process(request: JobEnvelope) -> ResultEnvelope:
        if request.stage != "embeddings":
            result = base_processor(request)
            return ResultEnvelope(result.job_id, result.status, result.artifact_id, result.error, request.worker, request.lease_id)
        if not request.input_artifact_id:
            raise ExchangeError("embeddings request requires input_artifact_id")
        manifest = artifact_resolver.resolve(request.input_artifact_id)
        if manifest.stage != "diarization" or manifest.kind != "json":
            raise ExchangeError(f"embeddings input artifact must be a diarization json artifact, got {manifest.stage}/{manifest.kind}")
        diarized_json = artifact_resolver.resolve_path(request.input_artifact_id)
        audio = artifact_resolver.resolve_path(f"{request.recording_id}:normalize:audio")
        embeddings = extract_and_persist(audio=audio, diarized_json=diarized_json, output_dir=output_dir / request.recording_id / "embeddings", recording_id=request.recording_id, model=embedder, config=embedding_config)
        if not embeddings:
            raise RuntimeError(f"no usable speaker segments for {request.recording_id}")
        return ResultEnvelope(request.job_id, "completed", artifact_id=f"{request.recording_id}:embeddings:json", worker=request.worker, lease_id=request.lease_id)

    return process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.getenv("TRANSCRIBE_EXCHANGE_ROOT", "/content/drive/MyDrive/transcribe/exchange"))
    parser.add_argument("--input", default=os.getenv("TRANSCRIBE_INPUT_ROOT", "/content/drive/MyDrive/transcribe/input"))
    parser.add_argument("--output", default=os.getenv("TRANSCRIBE_OUTPUT_ROOT", "/content/drive/MyDrive/transcribe/exchange/artifacts"))
    parser.add_argument("--poll", type=int, default=int(os.getenv("TRANSCRIBE_EXCHANGE_POLL", "30")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.poll < 1:
        parser.error("--poll must be at least 1 second")
    config = InferenceConfig()
    embedding_config = EmbeddingConfig()
    whisper, diarizer, embedder = load_models(config, embedding_config)
    processor = build_processor(Path(args.input), Path(args.output), whisper, diarizer, embedder, config, embedding_config)
    exchange = FileExchange(Path(args.root))
    while True:
        for path in exchange.list_requests():
            try:
                result = process_one(exchange, path.stem, processor)
                print(f"{result.job_id}\t{result.status}\t{result.artifact_id or result.error}", flush=True)
            except (FileNotFoundError, ExchangeError) as exc:
                print(f"exchange iteration failed: {exc}", flush=True)
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
