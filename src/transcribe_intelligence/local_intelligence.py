"""Dependency-free Oracle processors for post-ASR intelligence stages."""
from __future__ import annotations

from collections import Counter
import json
import re
from pathlib import Path

from .artifact_resolver import ArtifactResolver
from .artifacts import build_manifest, write_manifest
from .exchange import ExchangeError, JobEnvelope, ResultEnvelope

_WORD = re.compile(r"[\wА-Яа-яЁёІіЇїЄєҐґ'-]{3,}")
_STOPWORDS = {
    "это", "как", "что", "так", "для", "при", "или", "если", "она", "они", "его", "ее",
    "the", "and", "that", "this", "with", "from", "have", "are", "you", "your", "was",
}


class LocalIntelligenceProcessor:
    """Produce deterministic, auditable JSON artifacts without model dependencies."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.resolver = ArtifactResolver(self.root)

    def _recording_dir(self, recording_id: str) -> Path:
        if not recording_id.strip() or "/" in recording_id or "\\" in recording_id:
            raise ValueError("recording_id must be a non-empty path-safe identifier")
        return self.root / recording_id

    def _json_input(self, artifact_id: str, *, stage: str) -> tuple[dict[str, object], Path]:
        manifest = self.resolver.resolve(artifact_id)
        if manifest.stage != stage:
            raise ExchangeError(f"input artifact must be stage {stage}, got {manifest.stage}")
        path = self.resolver.resolve_path(artifact_id)
        try:
            return json.loads(path.read_text(encoding="utf-8")), path
        except (OSError, json.JSONDecodeError) as exc:
            raise ExchangeError(f"invalid JSON artifact: {artifact_id}") from exc

    def _write(self, recording_id: str, stage: str, payload: dict[str, object]) -> str:
        directory = self._recording_dir(recording_id) / stage
        directory.mkdir(parents=True, exist_ok=True)
        artifact_id = f"{recording_id}:{stage}:json"
        path = directory / f"{recording_id}.{stage}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = build_manifest(
            path,
            artifact_id=artifact_id,
            recording_id=recording_id,
            stage=stage,
            kind="json",
            producer="oracle-local-rules",
            model_version="rules-v1",
        )
        write_manifest(manifest, directory / f"{recording_id}.{stage}.manifest.json")
        return artifact_id

    def text_analysis(self, request: JobEnvelope) -> ResultEnvelope:
        if not request.input_artifact_id:
            raise ExchangeError("text_analysis request requires input_artifact_id")
        payload, _ = self._json_input(request.input_artifact_id, stage="asr")
        segments = []
        for index, segment in enumerate(payload.get("segments", [])):
            text = str(segment.get("text", "")).strip()
            words = [word.casefold() for word in _WORD.findall(text) if word.casefold() not in _STOPWORDS]
            segments.append({
                "segment_id": str(segment.get("segment_id", index)),
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "speaker": segment.get("speaker"),
                "text": text,
                "word_count": len(words),
                "keywords": sorted(set(words)),
            })
        artifact_id = self._write(request.recording_id, "text_analysis", {
            "schema_version": "1.0",
            "recording_id": request.recording_id,
            "source_artifact_id": request.input_artifact_id,
            "segments": segments,
        })
        return ResultEnvelope(request.job_id, "completed", artifact_id=artifact_id, worker=request.worker, lease_id=request.lease_id)

    def topics(self, request: JobEnvelope) -> ResultEnvelope:
        if not request.input_artifact_id:
            raise ExchangeError("topics request requires input_artifact_id")
        payload, _ = self._json_input(request.input_artifact_id, stage="text_analysis")
        counts = Counter(
            keyword
            for segment in payload.get("segments", [])
            for keyword in segment.get("keywords", [])
            if isinstance(keyword, str)
        )
        topics = [
            {"topic_id": f"{request.recording_id}:topic:{word}", "label": word, "score": round(min(1.0, count / 5), 3), "mentions": count}
            for word, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ]
        artifact_id = self._write(request.recording_id, "topics", {
            "schema_version": "1.0",
            "recording_id": request.recording_id,
            "source_artifact_id": request.input_artifact_id,
            "topics": topics,
        })
        return ResultEnvelope(request.job_id, "completed", artifact_id=artifact_id, worker=request.worker, lease_id=request.lease_id)

    def linking(self, request: JobEnvelope) -> ResultEnvelope:
        if len(request.input_artifact_ids) < 2:
            raise ExchangeError("linking request requires topic and embedding artifact IDs")
        topics_id, embeddings_id = request.input_artifact_ids[:2]
        topics, _ = self._json_input(topics_id, stage="topics")
        embeddings_manifest = self.resolver.resolve(embeddings_id)
        if embeddings_manifest.stage != "embeddings":
            raise ExchangeError("linking embedding dependency must be an embeddings artifact")
        embeddings_path = self.resolver.resolve_path(embeddings_id)
        try:
            embeddings = json.loads(embeddings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExchangeError("invalid embeddings artifact") from exc
        speakers = sorted({str(value.get("speaker")) for value in embeddings.get("embeddings", {}).values() if value.get("speaker")})
        links = [
            {"link_id": f"{topic['topic_id']}:{speaker}", "topic_id": topic["topic_id"], "speaker": speaker, "confidence": topic["score"]}
            for topic in topics.get("topics", [])
            for speaker in speakers
        ]
        artifact_id = self._write(request.recording_id, "linking", {
            "schema_version": "1.0",
            "recording_id": request.recording_id,
            "source_artifact_ids": [topics_id, embeddings_id],
            "links": links,
        })
        return ResultEnvelope(request.job_id, "completed", artifact_id=artifact_id, worker=request.worker, lease_id=request.lease_id)

    def graph(self, request: JobEnvelope) -> ResultEnvelope:
        if not request.input_artifact_id:
            raise ExchangeError("graph request requires input_artifact_id")
        payload, _ = self._json_input(request.input_artifact_id, stage="linking")
        nodes: dict[str, dict[str, object]] = {}
        edges = []
        for link in payload.get("links", []):
            topic_id = str(link["topic_id"])
            speaker = str(link["speaker"])
            nodes.setdefault(topic_id, {"id": topic_id, "type": "topic"})
            speaker_id = f"speaker:{speaker}"
            nodes.setdefault(speaker_id, {"id": speaker_id, "type": "speaker", "label": speaker})
            edges.append({"source": topic_id, "target": speaker_id, "confidence": link.get("confidence", 0.0)})
        artifact_id = self._write(request.recording_id, "graph", {
            "schema_version": "1.0",
            "recording_id": request.recording_id,
            "source_artifact_id": request.input_artifact_id,
            "nodes": [nodes[key] for key in sorted(nodes)],
            "edges": sorted(edges, key=lambda item: (item["source"], item["target"])),
        })
        return ResultEnvelope(request.job_id, "completed", artifact_id=artifact_id, worker=request.worker, lease_id=request.lease_id)

    def process(self, request: JobEnvelope) -> ResultEnvelope:
        handlers = {
            "text_analysis": self.text_analysis,
            "topics": self.topics,
            "linking": self.linking,
            "graph": self.graph,
        }
        try:
            return handlers[request.stage](request)
        except KeyError as exc:
            raise LocalIntelligenceProcessorError(f"unsupported intelligence stage: {request.stage}") from exc


class LocalIntelligenceProcessorError(RuntimeError):
    """Raised for unsupported local intelligence stages."""
