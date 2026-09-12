"""Real Whisper + pyannote inference adapter for a Colab GPU runtime."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

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


def resolve_audio(input_dir: Path, request: JobEnvelope) -> Path:
    """Resolve audio from an explicit exchange path, then safe fallbacks."""
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


def transcribe_file(audio: Path, output_dir: Path, recording_id: str, config: InferenceConfig, whisper: Any, diarizer: Any) -> list[ArtifactManifest]:
    """Run ASR + diarization and emit TXT/JSON/SRT artifacts."""
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
    payload = {"recording_id": recording_id, "source": audio.name, "model": f"whisper/{config.whisper_model}", "diarization": config.diarization_model, "segments": rows}
    srt = "\n".join(f'{i}\n{_stamp(r["start"], True)} --> {_stamp(r["end"], True)}\n[{r["speaker"]}] {r["text"]}\n' for i, r in enumerate(rows, 1))

    paths = {"txt": output_dir / f"{recording_id}.txt", "json": output_dir / f"{recording_id}.json", "srt": output_dir / f"{recording_id}.srt"}
    paths["txt"].write_text(txt, encoding="utf-8")
    paths["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["srt"].write_text(srt, encoding="utf-8")

    return [build_manifest(p, artifact_id=f"{recording_id}:{kind}", recording_id=recording_id, stage="diarization", kind=kind, producer="colab-whisper-pyannote", model_version=config.whisper_model) for kind, p in paths.items()]


def make_processor(input_dir: Path, output_dir: Path, whisper: Any, diarizer: Any, config: InferenceConfig = InferenceConfig()):
    """Build an exchange processor around already-loaded GPU models."""
    def process(request: JobEnvelope) -> ResultEnvelope:
        audio = resolve_audio(input_dir, request)
        manifests = transcribe_file(audio, output_dir / request.recording_id, request.recording_id, config, whisper, diarizer)
        for manifest in manifests:
            write_manifest(manifest, output_dir / request.recording_id / f"{manifest.kind}.manifest.json")
        return ResultEnvelope(request.job_id, "completed", artifact_id=manifests[0].artifact_id)
    return process
