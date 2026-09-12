from pathlib import Path

import pytest

from transcribe_intelligence.exchange import JobEnvelope
from scripts.colab_inference import InferenceConfig, make_processor, resolve_audio


class FakeSegment:
    start = 0.0
    end = 1.5
    text = " Сергей, отправь договор "


class FakeWhisper:
    def transcribe(self, path, **kwargs):
        assert kwargs["word_timestamps"] is True
        return iter([FakeSegment()]), None


class Turn:
    start = 0.0
    end = 2.0


class FakeDiarizer:
    def __call__(self, path):
        class Result:
            def itertracks(self, yield_label=True):
                assert yield_label is True
                yield Turn(), None, "SPEAKER_00"
        return Result()


def test_resolve_audio_uses_manifest_path(tmp_path: Path):
    audio = tmp_path / "nested" / "call.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"audio")
    request = JobEnvelope("job1", "a1b2c3", "diarization", input_path="nested/call.wav")
    assert resolve_audio(tmp_path, request) == audio.resolve()


def test_resolve_audio_blocks_escape(tmp_path: Path):
    request = JobEnvelope("job1", "rec1", "diarization", input_path="../secret.wav")
    with pytest.raises(ValueError):
        resolve_audio(tmp_path, request)


def test_asr_and_diarization_are_distinct(tmp_path: Path):
    audio = tmp_path / "nested" / "call.wav"
    audio.parent.mkdir(); audio.write_bytes(b"audio")
    processor = make_processor(tmp_path, tmp_path / "out", FakeWhisper(), FakeDiarizer())
    asr = processor(JobEnvelope("job-asr", "rec1", "asr", input_path="nested/call.wav"))
    assert asr.artifact_id == "rec1:asr:json"
    diar = processor(JobEnvelope("job-dia", "rec1", "diarization", input_path="nested/call.wav"))
    assert diar.artifact_id == "rec1:diarization:json"
    assert (tmp_path / "out" / "rec1" / "diarization" / "diarized.json").is_file()


def test_diarization_requires_asr(tmp_path: Path):
    audio = tmp_path / "call.wav"; audio.write_bytes(b"audio")
    processor = make_processor(tmp_path, tmp_path / "out", FakeWhisper(), FakeDiarizer())
    with pytest.raises(FileNotFoundError, match="ASR artifact required"):
        processor(JobEnvelope("job-dia", "rec1", "diarization", input_path="call.wav"))
