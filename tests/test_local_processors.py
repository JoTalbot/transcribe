from pathlib import Path
import struct
import wave

import pytest

from transcribe_intelligence.exchange import JobEnvelope
from transcribe_intelligence.local_processors import LocalAudioProcessor, LocalProcessorError


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(struct.pack("<hh", 1000, -1000) * 8)


def test_ingest_creates_canonical_source_artifact(tmp_path: Path):
    source = tmp_path / "input" / "call.wav"
    source.parent.mkdir()
    source.write_bytes(b"source-audio")
    root = tmp_path / "exchange"

    result = LocalAudioProcessor(root).process(
        JobEnvelope("j1", "rec1", "ingest", input_path=str(source), worker="oracle-1", lease_id="l1")
    )

    assert result.status == "completed"
    assert result.artifact_id == "rec1:ingest:source"
    artifact = root / "rec1" / "ingest" / "rec1.source.wav"
    assert artifact.read_bytes() == b"source-audio"
    assert (root / "rec1" / "ingest" / "rec1_ingest_source.manifest.json").is_file()


def test_ingest_does_not_replace_existing_artifact(tmp_path: Path):
    source = tmp_path / "input.wav"
    source.write_bytes(b"source-audio")
    root = tmp_path / "exchange"
    processor = LocalAudioProcessor(root)

    first = processor.process(JobEnvelope("j1", "rec1", "ingest", input_path=str(source)))
    artifact = root / "rec1" / "ingest" / "rec1.source.wav"
    original = artifact.read_bytes()

    source.write_bytes(b"different-source")
    with pytest.raises(ValueError, match="artifact manifest already exists with different content"):
        processor.process(JobEnvelope("j2", "rec1", "ingest", input_path=str(source)))

    assert first.artifact_id == "rec1:ingest:source"
    assert artifact.read_bytes() == original


def test_normalize_resolves_input_artifact_and_produces_pcm_wav(tmp_path: Path):
    source = tmp_path / "input.wav"
    _wav(source)
    root = tmp_path / "exchange"
    processor = LocalAudioProcessor(root)

    ingest = processor.process(JobEnvelope("j1", "rec1", "ingest", input_path=str(source)))
    result = processor.process(
        JobEnvelope("j2", "rec1", "normalize", input_artifact_id=ingest.artifact_id, worker="oracle-1", lease_id="l2")
    )

    assert result.status == "completed"
    assert result.artifact_id == "rec1:normalize:audio"
    normalized = root / "rec1" / "normalize" / "rec1.normalized.wav"
    assert normalized.is_file()
    with wave.open(str(normalized), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 16000
        assert handle.getsampwidth() == 2
    assert (root / "rec1" / "normalize" / "rec1_normalize_audio.manifest.json").is_file()


def test_normalize_rejects_wrong_dependency_artifact(tmp_path: Path):
    source = tmp_path / "input.wav"
    source.write_bytes(b"source")
    root = tmp_path / "exchange"
    processor = LocalAudioProcessor(root)
    processor.process(JobEnvelope("j1", "rec1", "ingest", input_path=str(source)))

    with pytest.raises(Exception, match="normalize input artifact"):
        processor.normalize(JobEnvelope("j2", "rec1", "normalize", input_artifact_id="missing"))


def test_local_processor_rejects_unsupported_stage(tmp_path: Path):
    with pytest.raises(LocalProcessorError, match="unsupported local stage"):
        LocalAudioProcessor(tmp_path / "exchange").process(JobEnvelope("j1", "rec1", "asr"))
