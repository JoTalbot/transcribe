from pathlib import Path

import pytest

from transcribe_intelligence.exchange import JobEnvelope
from scripts.colab_inference import InferenceConfig, make_processor, transcribe_file


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


def test_transcribe_file_writes_artifacts(tmp_path: Path):
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"audio")
    manifests = transcribe_file(audio, tmp_path / "out", "rec1", InferenceConfig(), FakeWhisper(), FakeDiarizer())
    assert {m.kind for m in manifests} == {"txt", "json", "srt"}
    assert (tmp_path / "out" / "rec1.txt").read_text(encoding="utf-8").startswith("[00:00:00 - SPEAKER_00]")


def test_processor_returns_completed_result(tmp_path: Path):
    audio = tmp_path / "rec1.wav"
    audio.write_bytes(b"audio")
    processor = make_processor(tmp_path, tmp_path / "out", FakeWhisper(), FakeDiarizer())
    result = processor(JobEnvelope("job1", "rec1", "diarization"))
    assert result.status == "completed"
    assert result.artifact_id == "rec1:txt"


def test_processor_rejects_missing_audio(tmp_path: Path):
    processor = make_processor(tmp_path, tmp_path / "out", FakeWhisper(), FakeDiarizer())
    with pytest.raises(FileNotFoundError):
        processor(JobEnvelope("job1", "missing", "diarization"))
