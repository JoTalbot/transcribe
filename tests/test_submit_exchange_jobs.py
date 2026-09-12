from pathlib import Path

from scripts.submit_exchange_jobs import recording_paths
from transcribe_intelligence.exchange import FileExchange, JobEnvelope


def test_recording_paths_uses_manifest_ids():
    manifest = {"recordings": [{"recording_id": "abc123", "path": "calls/2026/call.wav"}]}
    assert recording_paths(manifest) == {"abc123": "calls/2026/call.wav"}


def test_exchange_request_preserves_exact_manifest_path(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    path = exchange.put_request(JobEnvelope("abc123:asr", "abc123", "asr", input_path="calls/2026/call.wav"))
    assert path.exists()
    loaded = exchange.get_request("abc123:asr")
    assert loaded.input_path == "calls/2026/call.wav"
