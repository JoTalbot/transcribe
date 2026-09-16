"""Oracle-local processors for the first two canonical pipeline stages."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .artifact_resolver import ArtifactResolutionError, ArtifactResolver
from .artifacts import ArtifactManifest, build_manifest, sha256_file, write_manifest
from .exchange import ExchangeError, JobEnvelope, ResultEnvelope


class LocalProcessorError(RuntimeError):
    """Raised when an Oracle-local pipeline processor cannot produce an artifact."""


class LocalAudioProcessor:
    """Produce canonical, checksummed artifacts for ingest and normalize."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.resolver = ArtifactResolver(self.root)

    def _recording_dir(self, recording_id: str) -> Path:
        if not recording_id.strip() or "/" in recording_id or "\\" in recording_id:
            raise ValueError("recording_id must be a non-empty path-safe identifier")
        return self.root / recording_id

    def _source(self, request: JobEnvelope) -> Path:
        if not request.input_path:
            raise LocalProcessorError("ingest request requires input_path")
        candidate = Path(request.input_path).expanduser()
        if not candidate.is_absolute():
            candidate = (self.root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def _write_manifest(self, path: Path, *, artifact_id: str, recording_id: str, stage: str, kind: str, producer: str) -> ArtifactManifest:
        manifest = build_manifest(
            path,
            artifact_id=artifact_id,
            recording_id=recording_id,
            stage=stage,
            kind=kind,
            producer=producer,
        )
        write_manifest(manifest, path.parent / f"{artifact_id.replace(':', '_')}.manifest.json")
        return manifest

    def ingest(self, request: JobEnvelope) -> ResultEnvelope:
        """Copy source bytes into canonical storage without modifying them."""
        source = self._source(request)
        target_dir = self._recording_dir(request.recording_id) / "ingest"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{request.recording_id}.source{source.suffix.lower()}"
        if target.exists():
            if target.stat().st_size != source.stat().st_size or sha256_file(target) != sha256_file(source):
                raise ValueError(f"artifact manifest already exists with different content: {target}")
        else:
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            try:
                target.hardlink_to(temporary)
            except FileExistsError:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise LocalProcessorError(f"cannot publish ingest artifact atomically: {target}") from exc
            else:
                temporary.unlink(missing_ok=True)
        if not target.is_file():
            raise LocalProcessorError(f"ingest artifact was not created: {target}")
        manifest = self._write_manifest(
            target,
            artifact_id=f"{request.recording_id}:ingest:source",
            recording_id=request.recording_id,
            stage="ingest",
            kind="source_audio",
            producer="oracle-local",
        )
        return ResultEnvelope(request.job_id, "completed", artifact_id=manifest.artifact_id, worker=request.worker, lease_id=request.lease_id)

    def normalize(self, request: JobEnvelope) -> ResultEnvelope:
        """Convert audio to deterministic PCM WAV using ffmpeg when needed."""
        if not request.input_artifact_id:
            raise ExchangeError("normalize input artifact is required")
        try:
            manifest = self.resolver.resolve(request.input_artifact_id)
        except (FileNotFoundError, ValueError, ArtifactResolutionError) as exc:
            raise ExchangeError(f"normalize input artifact not found: {request.input_artifact_id}") from exc
        if manifest.stage != "ingest" or manifest.kind != "source_audio":
            raise ExchangeError(
                f"normalize input artifact must be ingest source_audio, got {manifest.stage}/{manifest.kind}"
            )
        source = self.resolver.resolve_path(request.input_artifact_id)
        target_dir = self._recording_dir(request.recording_id) / "normalize"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{request.recording_id}.normalized.wav"
        if not target.exists():
            temporary = target.with_suffix(".tmp.wav")
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(temporary),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise LocalProcessorError("ffmpeg is required for normalize") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or "ffmpeg failed").strip()
                raise LocalProcessorError(f"ffmpeg normalize failed: {detail}") from exc
            try:
                target.hardlink_to(temporary)
            except FileExistsError:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise LocalProcessorError(f"cannot publish normalize artifact atomically: {target}") from exc
            else:
                temporary.unlink(missing_ok=True)
        if not target.is_file():
            raise LocalProcessorError(f"normalize artifact was not created: {target}")
        output = self._write_manifest(
            target,
            artifact_id=f"{request.recording_id}:normalize:audio",
            recording_id=request.recording_id,
            stage="normalize",
            kind="audio_wav_pcm16_mono_16khz",
            producer="oracle-local-ffmpeg",
        )
        return ResultEnvelope(request.job_id, "completed", artifact_id=output.artifact_id, worker=request.worker, lease_id=request.lease_id)

    def process(self, request: JobEnvelope) -> ResultEnvelope:
        if request.stage == "ingest":
            return self.ingest(request)
        if request.stage == "normalize":
            return self.normalize(request)
        raise LocalProcessorError(f"unsupported local stage: {request.stage}")
