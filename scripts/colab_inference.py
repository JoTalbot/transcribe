"""Whisper + pyannote inference adapters for a Colab GPU runtime."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from transcribe_intelligence.artifact_resolver import ArtifactResolver
from transcribe_intelligence.artifacts import ArtifactManifest, build_manifest, write_manifest
from transcribe_intelligence.exchange import JobEnvelope, ResultEnvelope


@dataclass(frozen=True, slots=True)
class InferenceConfig:
    whisper_model: str = "large-v3"
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    compute_type: str = "float16"


def _stamp(seconds: float, comma: bool = False) -> str:
    ms = max(0, int(round(float(seconds) * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}" if comma else f"{h:02d}:{m:02d}:{s:02d}"


def _assign_speaker(start: float, end: float, turns: list[tuple[float, float, str]]) -> str:
    scores: dict[str, float] = {}
    for a, b, label in turns:
        overlap = max(0.0, min(end, b) - max(start, a))
        if overlap > 0:
            scores[label] = scores.get(label, 0.0) + overlap
    return max(scores, key=scores.get) if scores else "UNKNOWN"


def resolve_audio(input_dir: Path, request: JobEnvelope, artifact_root: Path | None = None) -> Path:
    """Resolve audio from an artifact dependency or an explicit legacy path."""
    if request.input_artifact_id and artifact_root is not None:
        resolver = ArtifactResolver(artifact_root)
        manifest = resolver.resolve(request.input_artifact_id)
        if manifest.stage == "normalize" and manifest.kind == "audio_wav_pcm16_mono_16khz":
            return resolver.resolve_path(request.input_artifact_id)
        if manifest.stage == "ingest" and manifest.kind == "source_audio":
            return resolver.resolve_path(request.input_artifact_id)
    if request.input_path:
        candidate = (input_dir / request.input_path).resolve()
        root = input_dir.resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError("input_path escapes input directory")
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(candidate)
    direct = (input_dir / request.recording_id).resolve()
    if input_dir.resolve() in direct.parents and direct.is_file():
        return direct
    matches = list(input_dir.rglob(f"{request.recording_id}.*"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"audio for recording {request.recording_id!r} not found")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def transcribe_asr_file(audio: Path, output_dir: Path, recording_id: str, config: InferenceConfig, whisper: Any) -> list[ArtifactManifest]:
    segments, _ = whisper.transcribe(str(audio), beam_size=5, vad_filter=True, word_timestamps=True)
    rows = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            rows.append({"start": float(seg.start), "end": float(seg.end), "text": text})
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{recording_id}.asr.json"
    txt_path = output_dir / f"{recording_id}.asr.txt"
    payload = {"schema_version": "1.0", "recording_id": recording_id, "source": audio.name, "model": f"whisper/{config.whisper_model}", "segments": rows}
    _write(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    _write(txt_path, "\n".join(r["text"] for r in rows) + "\n")
    return [
        build_manifest(json_path, artifact_id=f"{recording_id}:asr:json", recording_id=recording_id, stage="asr", kind="transcript", producer="colab-faster-whisper", model_version=config.whisper_model),
        build_manifest(txt_path, artifact_id=f"{recording_id}:asr:txt", recording_id=recording_id, stage="asr", kind="transcript_txt", producer="colab-faster-whisper", model_version=config.whisper_model),
    ]


def transcribe_file(audio: Path, output_dir: Path, recording_id: str, config: InferenceConfig, whisper: Any, diarizer: Any) -> list[ArtifactManifest]:
    """Backward-compatible combined ASR + diarization artifact producer."""
    diar = diarizer(str(audio))
    turns = [(s.start, s.end, speaker) for s, _, speaker in diar.itertracks(yield_label=True)]
    segments, _ = whisper.transcribe(str(audio), beam_size=5, vad_filter=True, word_timestamps=True)
    rows = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            rows.append({"start": float(seg.start), "end": float(seg.end), "speaker": _assign_speaker(seg.start, seg.end, turns), "text": text})
    output_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join(f'[{_stamp(r["start"])} - {r["speaker"]}]: {r["text"]}' for r in rows) + "\n"
    payload = {"schema_version": "1.0", "recording_id": recording_id, "source": audio.name, "model": f"whisper/{config.whisper_model}", "diarization": config.diarization_model, "segments": rows}
    srt = "\n".join(f'{i}\n{_stamp(r["start"], True)} --> {_stamp(r["end"], True)}\n[{r["speaker"]}] {r["text"]}\n' for i, r in enumerate(rows, 1))
    paths = {"txt": output_dir / f"{recording_id}.txt", "json": output_dir / f"{recording_id}.json", "srt": output_dir / f"{recording_id}.srt"}
    _write(paths["txt"], txt)
    _write(paths["json"], json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    _write(paths["srt"], srt)
    return [build_manifest(p, artifact_id=f"{recording_id}:{kind}", recording_id=recording_id, stage="diarization", kind=kind, producer="colab-whisper-pyannote", model_version=config.whisper_model) for kind, p in paths.items()]


def diarize_asr_file(audio: Path, output_dir: Path, recording_id: str, config: InferenceConfig, diarizer: Any, asr_path: Path | None = None) -> list[ArtifactManifest]:
    asr_path = asr_path or output_dir / f"{recording_id}.asr.json"
    if not asr_path.is_file():
        raise FileNotFoundError(f"ASR artifact not found: {asr_path}")
    payload = json.loads(asr_path.read_text(encoding="utf-8"))
    diar = diarizer(str(audio))
    turns = [(s.start, s.end, speaker) for s, _, speaker in diar.itertracks(yield_label=True)]
    rows = [{**segment, "speaker": _assign_speaker(float(segment["start"]), float(segment["end"]), turns)} for segment in payload.get("segments", [])]
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{recording_id}.json"
    txt_path = output_dir / f"{recording_id}.txt"
    srt_path = output_dir / f"{recording_id}.srt"
    _write(json_path, json.dumps({**payload, "diarization": config.diarization_model, "segments": rows}, ensure_ascii=False, indent=2) + "\n")
    _write(txt_path, "\n".join(f'[{_stamp(r["start"])} - {r["speaker"]}]: {r["text"]}' for r in rows) + "\n")
    _write(srt_path, "\n".join(f'{i}\n{_stamp(r["start"], True)} --> {_stamp(r["end"], True)}\n[{r["speaker"]}] {r["text"]}\n' for i, r in enumerate(rows, 1)))
    return [
        build_manifest(json_path, artifact_id=f"{recording_id}:diarization:json", recording_id=recording_id, stage="diarization", kind="json", producer="colab-whisper-pyannote", model_version=config.diarization_model),
        build_manifest(txt_path, artifact_id=f"{recording_id}:diarization:txt", recording_id=recording_id, stage="diarization", kind="txt", producer="colab-whisper-pyannote", model_version=config.diarization_model),
        build_manifest(srt_path, artifact_id=f"{recording_id}:diarization:srt", recording_id=recording_id, stage="diarization", kind="srt", producer="colab-whisper-pyannote", model_version=config.diarization_model),
    ]


def make_processor(input_dir: Path, output_dir: Path, whisper: Any, diarizer: Any, config: InferenceConfig = InferenceConfig()):
    """Build an exchange processor with artifact-driven ASR and diarization."""
    artifact_resolver = ArtifactResolver(output_dir)

    def process(request: JobEnvelope) -> ResultEnvelope:
        recording_dir = output_dir / request.recording_id
        if request.stage == "asr":
            if not request.input_artifact_id:
                raise ValueError("asr request requires input_artifact_id")
            manifest = artifact_resolver.resolve(request.input_artifact_id)
            if manifest.stage != "normalize" or manifest.kind != "audio_wav_pcm16_mono_16khz":
                raise ValueError("asr input artifact must be normalized audio")
            audio = artifact_resolver.resolve_path(request.input_artifact_id)
            manifests = transcribe_asr_file(audio, recording_dir, request.recording_id, config, whisper)
        elif request.stage == "diarization":
            if not request.input_artifact_id:
                audio = resolve_audio(input_dir, request, output_dir)
                manifests = transcribe_file(audio, recording_dir, request.recording_id, config, whisper, diarizer)
                manifests = [
                    build_manifest(
                        recording_dir / f"{request.recording_id}.json",
                        artifact_id=f"{request.recording_id}:diarization:json",
                        recording_id=request.recording_id,
                        stage="diarization",
                        kind="json",
                        producer="colab-whisper-pyannote",
                        model_version=config.diarization_model,
                    )
                ]
            else:
                asr_manifest = artifact_resolver.resolve(request.input_artifact_id)
                if asr_manifest.stage != "asr" or asr_manifest.kind != "transcript":
                    raise ValueError("diarization input artifact must be an ASR transcript")
                asr_path = artifact_resolver.resolve_path(request.input_artifact_id)
                normalize_id = f"{request.recording_id}:normalize:audio"
                audio = artifact_resolver.resolve_path(normalize_id)
                manifests = diarize_asr_file(audio, recording_dir, request.recording_id, config, diarizer, asr_path)
        else:
            raise ValueError(f"unsupported inference stage: {request.stage}")
        for manifest in manifests:
            write_manifest(manifest, recording_dir / f"{manifest.artifact_id.replace(':', '_')}.manifest.json")
        return ResultEnvelope(request.job_id, "completed", artifact_id=manifests[0].artifact_id)
    return process
