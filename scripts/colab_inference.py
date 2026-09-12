"""Stage-aware Whisper + pyannote inference for a Colab GPU runtime."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from transcribe_intelligence.artifacts import ArtifactManifest, build_manifest, write_manifest
from transcribe_intelligence.exchange import JobEnvelope, ResultEnvelope
from transcribe_intelligence.stage_artifacts import DiarizedSegment, TranscriptSegment, diarized_payload, transcript_payload


@dataclass(frozen=True, slots=True)
class InferenceConfig:
    whisper_model: str = "large-v3"
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    compute_type: str = "float16"


def _stamp(seconds: float, comma: bool = False) -> str:
    ms = max(0, int(round(float(seconds) * 1000)))
    h, ms = divmod(ms, 3_600_000); m, ms = divmod(ms, 60_000); s, ms = divmod(ms, 1_000)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}" if comma else f"{h:02d}:{m:02d}:{s:02d}"


def _assign_speaker(start: float, end: float, turns: list[tuple[float, float, str]]) -> str:
    scores: dict[str, float] = {}
    for a, b, label in turns:
        overlap = max(0.0, min(end, b) - max(start, a))
        if overlap > 0:
            scores[label] = scores.get(label, 0.0) + overlap
    return max(scores, key=scores.get) if scores else "UNKNOWN"


def resolve_audio(input_dir: Path, request: JobEnvelope) -> Path:
    if request.input_path:
        candidate = (input_dir / request.input_path).resolve()
        root = input_dir.resolve()
        if root not in candidate.parents:
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


def _segments_from_whisper(audio: Path, whisper: Any) -> list[TranscriptSegment]:
    segments, _ = whisper.transcribe(str(audio), beam_size=5, vad_filter=True, word_timestamps=True)
    return [TranscriptSegment(float(seg.start), float(seg.end), seg.text.strip()) for seg in segments if seg.text.strip()]


def _diarize(audio: Path, transcript: list[TranscriptSegment], diarizer: Any) -> list[DiarizedSegment]:
    diar = diarizer(str(audio))
    turns = [(s.start, s.end, speaker) for s, _, speaker in diar.itertracks(yield_label=True)]
    return [DiarizedSegment(s.start, s.end, _assign_speaker(s.start, s.end, turns), s.text) for s in transcript]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_asr(audio: Path, output_dir: Path, recording_id: str, config: InferenceConfig, whisper: Any) -> list[ArtifactManifest]:
    segments = _segments_from_whisper(audio, whisper)
    payload = transcript_payload(recording_id, audio.name, f"whisper/{config.whisper_model}", segments)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "transcript.json"
    txt_path = output_dir / "transcript.txt"
    _write_json(json_path, payload)
    txt_path.write_text("\n".join(f'[{_stamp(s.start)} - {s.end:.2f}]: {s.text}' for s in segments) + "\n", encoding="utf-8")
    return [build_manifest(json_path, artifact_id=f"{recording_id}:asr:json", recording_id=recording_id, stage="asr", kind="transcript-json", producer="colab-faster-whisper", model_version=config.whisper_model), build_manifest(txt_path, artifact_id=f"{recording_id}:asr:txt", recording_id=recording_id, stage="asr", kind="transcript-txt", producer="colab-faster-whisper", model_version=config.whisper_model)]


def run_diarization(audio: Path, asr_json: Path, output_dir: Path, recording_id: str, config: InferenceConfig, diarizer: Any) -> list[ArtifactManifest]:
    payload = json.loads(asr_json.read_text(encoding="utf-8"))
    transcript = [TranscriptSegment(float(s["start"]), float(s["end"]), str(s["text"])) for s in payload["segments"]]
    segments = _diarize(audio, transcript, diarizer)
    result = diarized_payload(recording_id, audio.name, config.diarization_model, segments)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "diarized.json"
    txt_path = output_dir / "diarized.txt"
    srt_path = output_dir / "diarized.srt"
    _write_json(json_path, result)
    txt_path.write_text("\n".join(f'[{_stamp(s.start)} - {s.speaker}]: {s.text}' for s in segments) + "\n", encoding="utf-8")
    srt_path.write_text("\n".join(f'{i}\n{_stamp(s.start, True)} --> {_stamp(s.end, True)}\n[{s.speaker}] {s.text}\n' for i, s in enumerate(segments, 1)), encoding="utf-8")
    return [build_manifest(json_path, artifact_id=f"{recording_id}:diarization:json", recording_id=recording_id, stage="diarization", kind="diarized-json", producer="colab-pyannote", model_version=config.diarization_model), build_manifest(txt_path, artifact_id=f"{recording_id}:diarization:txt", recording_id=recording_id, stage="diarization", kind="diarized-txt", producer="colab-pyannote", model_version=config.diarization_model), build_manifest(srt_path, artifact_id=f"{recording_id}:diarization:srt", recording_id=recording_id, stage="diarization", kind="diarized-srt", producer="colab-pyannote", model_version=config.diarization_model)]


def make_processor(input_dir: Path, output_dir: Path, whisper: Any, diarizer: Any, config: InferenceConfig = InferenceConfig()):
    def process(request: JobEnvelope) -> ResultEnvelope:
        audio = resolve_audio(input_dir, request)
        root = output_dir / request.recording_id
        if request.stage == "asr":
            manifests = run_asr(audio, root / "asr", request.recording_id, config, whisper)
        elif request.stage == "diarization":
            asr_json = root / "asr" / "transcript.json"
            if not asr_json.is_file():
                raise FileNotFoundError(f"ASR artifact required before diarization: {asr_json}")
            manifests = run_diarization(audio, asr_json, root / "diarization", request.recording_id, config, diarizer)
        else:
            raise ValueError(f"unsupported Colab inference stage: {request.stage}")
        for manifest in manifests:
            write_manifest(manifest, root / manifest.stage / f"{manifest.kind}.manifest.json")
        return ResultEnvelope(request.job_id, "completed", artifact_id=manifests[0].artifact_id)
    return process
