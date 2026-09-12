from transcribe_intelligence.stage_artifacts import DiarizedSegment, TranscriptSegment, diarized_payload, transcript_payload


def test_payloads_are_stage_specific():
    transcript = [TranscriptSegment(0.0, 1.0, "hello")]
    diarized = [DiarizedSegment(0.0, 1.0, "SPEAKER_00", "hello")]
    assert "speaker" not in transcript_payload("r", "a.wav", "whisper/x", transcript)["segments"][0]
    assert diarized_payload("r", "a.wav", "pyannote/x", diarized)["segments"][0]["speaker"] == "SPEAKER_00"
