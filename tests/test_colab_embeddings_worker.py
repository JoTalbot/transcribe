from pathlib import Path

import scripts.colab_exchange_worker as colab_worker
from scripts.colab_exchange_worker import build_processor, process_one
from scripts.colab_inference import InferenceConfig
from scripts.colab_speaker_embeddings import EmbeddingConfig
from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.exchange import FileExchange, JobEnvelope


def _publish_artifact(root: Path, artifact_id: str, recording_id: str, stage: str, kind: str, name: str, payload: bytes) -> Path:
    artifact = root / recording_id / name
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(payload)
    manifest = build_manifest(
        artifact,
        artifact_id=artifact_id,
        recording_id=recording_id,
        stage=stage,
        kind=kind,
        producer="test",
        model_version="test",
    )
    write_manifest(manifest, artifact.with_name(f"{artifact.name}.manifest.json"))
    return artifact


def test_colab_embeddings_entrypoint_resolves_shared_artifacts_and_publishes_result(tmp_path: Path, monkeypatch):
    exchange = FileExchange(tmp_path / "exchange")
    artifacts = exchange.root / "artifacts"
    recording_id = "rec-embeddings"
    job_id = "job-embeddings"

    _publish_artifact(
        artifacts,
        f"{recording_id}:normalize:audio",
        recording_id,
        "normalize",
        "audio_wav_pcm16_mono_16khz",
        "normalized.wav",
        b"normalized-audio",
    )
    _publish_artifact(
        artifacts,
        f"{recording_id}:diarization:json",
        recording_id,
        "diarization",
        "json",
        "diarization.json",
        b'{"segments":[{"start":0,"end":1,"speaker":"SPEAKER_00"}]}\n',
    )

    request = JobEnvelope(
        job_id,
        recording_id,
        "embeddings",
        input_artifact_id=f"{recording_id}:diarization:json",
        input_artifact_ids=(f"{recording_id}:diarization:json",),
        worker="colab-gpu",
        lease_id="lease-1",
    )
    exchange.put_request(request)

    captured: dict[str, Path] = {}

    def fake_extract_and_persist(*, audio, diarized_json, output_dir, recording_id, model, config):
        captured.update(audio=audio, diarized_json=diarized_json, output_dir=output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "speaker_embeddings.json"
        output.write_text('{"recording_id":"rec-embeddings"}\n', encoding="utf-8")
        manifest = build_manifest(
            output,
            artifact_id=f"{recording_id}:embeddings:json",
            recording_id=recording_id,
            stage="embeddings",
            kind="speaker_embeddings",
            producer="test-ecapa",
            model_version=config.model_name,
        )
        write_manifest(manifest, output_dir / "speaker_embeddings.manifest.json")
        return [object()]

    monkeypatch.setattr(colab_worker, "extract_and_persist", fake_extract_and_persist)
    processor = build_processor(
        tmp_path / "input",
        artifacts,
        whisper=object(),
        diarizer=object(),
        embedder=object(),
        config=InferenceConfig(),
        embedding_config=EmbeddingConfig(),
    )

    result = process_one(exchange, job_id, processor)

    assert result.status == "completed"
    assert result.artifact_id == f"{recording_id}:embeddings:json"
    assert result.worker == "colab-gpu"
    assert result.lease_id == "lease-1"
    assert captured["audio"] == artifacts / recording_id / "normalized.wav"
    assert captured["diarized_json"] == artifacts / recording_id / "diarization.json"
    assert captured["output_dir"] == artifacts / recording_id / "embeddings"
    assert not (exchange.root / "processing" / f"{job_id}.json").exists()
    assert (exchange.results / f"{job_id}.json").is_file()
    assert (artifacts / recording_id / "embeddings" / "speaker_embeddings.manifest.json").is_file()
