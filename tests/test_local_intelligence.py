import json
from pathlib import Path

from transcribe_intelligence.artifacts import build_manifest, write_manifest
from transcribe_intelligence.exchange import JobEnvelope
from transcribe_intelligence.local_intelligence import LocalIntelligenceProcessor


def _artifact(root: Path, artifact_id: str, stage: str, payload: dict) -> None:
    path = root / "rec" / stage / f"{stage}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = build_manifest(
        path,
        artifact_id=artifact_id,
        recording_id="rec",
        stage=stage,
        kind="json",
        producer="test",
    )
    write_manifest(manifest, path.with_name(f"{stage}.manifest.json"))


def test_post_asr_processors_produce_verified_artifacts(tmp_path: Path):
    root = tmp_path / "artifacts"
    _artifact(root, "rec:asr:json", "asr", {
        "schema_version": "1.0",
        "recording_id": "rec",
        "segments": [
            {"segment_id": "s1", "start": 0, "end": 2, "speaker": "SPEAKER_00", "text": "обсудим договор и оплату"},
            {"segment_id": "s2", "start": 2, "end": 4, "speaker": "SPEAKER_01", "text": "договор требует проверки"},
        ],
    })
    processor = LocalIntelligenceProcessor(root)
    text_result = processor.process(JobEnvelope("rec:text", "rec", "text_analysis", "rec:asr:json", worker="oracle-local", lease_id="l1"))
    assert text_result.artifact_id == "rec:text_analysis:json"
    assert processor.resolver.resolve_path(text_result.artifact_id).is_file()

    topic_result = processor.process(JobEnvelope("rec:topics", "rec", "topics", text_result.artifact_id, worker="oracle-local", lease_id="l2"))
    assert topic_result.artifact_id == "rec:topics:json"
    assert processor.resolver.resolve_path(topic_result.artifact_id).is_file()

    _artifact(root, "rec:embeddings:json", "embeddings", {
        "schema_version": "1.0",
        "embeddings": {
            "rec:SPEAKER_00": {"speaker": "SPEAKER_00", "vector": [1.0]},
            "rec:SPEAKER_01": {"speaker": "SPEAKER_01", "vector": [1.0]},
        },
    })
    link_result = processor.process(JobEnvelope(
        "rec:linking", "rec", "linking", topic_result.artifact_id,
        input_artifact_ids=(topic_result.artifact_id, "rec:embeddings:json"),
        worker="oracle-local", lease_id="l3",
    ))
    assert link_result.artifact_id == "rec:linking:json"
    assert processor.resolver.resolve_path(link_result.artifact_id).is_file()

    graph_result = processor.process(JobEnvelope("rec:graph", "rec", "graph", link_result.artifact_id, worker="oracle-local", lease_id="l4"))
    assert graph_result.artifact_id == "rec:graph:json"
    assert processor.resolver.resolve_path(graph_result.artifact_id).is_file()
