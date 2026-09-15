from pathlib import Path
import wave

from scripts.oracle_local_worker import process_one
from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.exchange import FileExchange, JobEnvelope
from transcribe_intelligence.local_intelligence import LocalIntelligenceProcessor
from transcribe_intelligence.local_processors import LocalAudioProcessor


def _run(exchange: FileExchange, request: JobEnvelope, audio: LocalAudioProcessor, intelligence: LocalIntelligenceProcessor) -> str:
    result = process_one(exchange, request.job_id, audio, intelligence)
    assert result is not None
    assert result.status == "completed", result.error
    assert result.artifact_id is not None
    return result.artifact_id


def test_oracle_local_worker_runs_real_cpu_chain(tmp_path: Path) -> None:
    source = tmp_path / "input.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)

    root = tmp_path / "exchange"
    exchange = FileExchange(root)
    audio = LocalAudioProcessor(root / "artifacts")
    intelligence = LocalIntelligenceProcessor(root / "artifacts")

    ingest = JobEnvelope("recording:ingest", "recording", "ingest", input_path=str(source), worker="oracle-local", lease_id="l1")
    ingest_id = _run(exchange, ingest, audio, intelligence)

    normalize = JobEnvelope("recording:normalize", "recording", "normalize", input_artifact_id=ingest_id, worker="oracle-local", lease_id="l2")
    normalize_id = _run(exchange, normalize, audio, intelligence)
    assert normalize_id == "recording:normalize:audio"

    asr_path = root / "artifacts" / "recording" / "asr.json"
    asr_path.parent.mkdir(parents=True, exist_ok=True)
    asr_path.write_text('{"segments": [{"text": "hello world"}]}', encoding="utf-8")
    asr_manifest = build_manifest("recording:asr:json", "recording", "asr", "transcript", asr_path, "ci")
    write_manifest(asr_manifest, asr_path.with_name(asr_path.name + ".manifest.json"))

    text = JobEnvelope("recording:text_analysis", "recording", "text_analysis", input_artifact_id=asr_manifest.artifact_id, worker="oracle-local", lease_id="l3")
    text_id = _run(exchange, text, audio, intelligence)
    topics = JobEnvelope("recording:topics", "recording", "topics", input_artifact_id=text_id, worker="oracle-local", lease_id="l4")
    topics_id = _run(exchange, topics, audio, intelligence)

    embeddings_path = root / "artifacts" / "recording" / "embeddings.json"
    embeddings_path.write_text('{"embeddings": []}', encoding="utf-8")
    embeddings_manifest = build_manifest("recording:embeddings:json", "recording", "embeddings", "embeddings", embeddings_path, "ci")
    write_manifest(embeddings_manifest, embeddings_path.with_name(embeddings_path.name + ".manifest.json"))

    linking = JobEnvelope(
        "recording:linking", "recording", "linking",
        input_artifact_id=topics_id,
        input_artifact_ids=(topics_id, embeddings_manifest.artifact_id),
        worker="oracle-local", lease_id="l5",
    )
    linking_id = _run(exchange, linking, audio, intelligence)
    graph = JobEnvelope("recording:graph", "recording", "graph", input_artifact_id=linking_id, worker="oracle-local", lease_id="l6")
    graph_id = _run(exchange, graph, audio, intelligence)

    assert graph_id == "recording:graph:json"
    assert (root / "artifacts" / "recording").exists()
