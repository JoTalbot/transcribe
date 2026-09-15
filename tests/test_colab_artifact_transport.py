from pathlib import Path

from scripts import colab_exchange_worker
from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.exchange import FileExchange, JobEnvelope


def _manifest(root: Path, artifact_id: str, recording_id: str, stage: str, kind: str, name: str, content: str) -> Path:
    directory = root / recording_id / stage
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / name
    artifact.write_text(content, encoding="utf-8")
    manifest = build_manifest(
        artifact,
        artifact_id=artifact_id,
        recording_id=recording_id,
        stage=stage,
        kind=kind,
        producer="oracle-test",
    )
    path = directory / f"{artifact.stem}.manifest.json"
    write_manifest(manifest, path)
    return artifact


def test_colab_embeddings_resolves_oracle_absolute_manifests_from_shared_root(tmp_path: Path, monkeypatch):
    """A Drive-mounted Colab worker must resolve artifacts produced on another host."""
    shared = tmp_path / "exchange"
    normalized = _manifest(
        shared / "artifacts",
        "rec1:normalize:audio",
        "rec1",
        "normalize",
        "audio_wav_pcm16_mono_16khz",
        "audio.wav",
        "normalized audio bytes\n",
    )
    diarized = _manifest(
        shared / "artifacts",
        "rec1:diarization:json",
        "rec1",
        "diarization",
        "json",
        "diarized.json",
        '{"segments": [{"speaker": "SPEAKER_00", "start": 0, "end": 1}]}\n',
    )

    calls: dict[str, Path] = {}

    def fake_extract_and_persist(*, audio, diarized_json, output_dir, recording_id, model, config):
        calls["audio"] = audio
        calls["diarized"] = diarized_json
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "speaker_embeddings.json").write_text('{"embeddings": []}\n', encoding="utf-8")
        return [object()]

    monkeypatch.setattr(colab_exchange_worker, "extract_and_persist", fake_extract_and_persist)

    request = JobEnvelope(
        "rec1:embeddings",
        "rec1",
        "embeddings",
        input_artifact_id="rec1:diarization:json",
        input_artifact_ids=("rec1:diarization:json",),
        worker="colab-gpu",
        lease_id="lease-1",
    )
    processor = colab_exchange_worker.build_processor(
        shared / "input",
        shared / "artifacts",
        whisper=object(),
        diarizer=object(),
        embedder=object(),
        config=object(),
        embedding_config=object(),
    )

    result = processor(request)

    assert result.status == "completed"
    assert result.artifact_id == "rec1:embeddings:json"
    assert calls == {"audio": normalized.resolve(), "diarized": diarized.resolve()}


def test_colab_process_one_removes_processing_file_after_failed_artifact_transport(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    request = JobEnvelope(
        "job-1",
        "rec1",
        "embeddings",
        input_artifact_id="missing:diarization:json",
        worker="colab-gpu",
        lease_id="lease-1",
    )
    exchange.put_request(request)

    result = colab_exchange_worker.process_one(
        exchange,
        request.job_id,
        lambda current: (_ for _ in ()).throw(RuntimeError("artifact unavailable")),
    )

    assert result.status == "failed"
    assert result.worker == "colab-gpu"
    assert result.lease_id == "lease-1"
    assert not (exchange.root / "processing" / "job-1.json").exists()
    assert exchange.get_result("job-1").error == "artifact unavailable"
