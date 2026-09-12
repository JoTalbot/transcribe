from pathlib import Path

from transcribe_intelligence.job_store import JobStore
from transcribe_intelligence.state_store import StateStore


def test_cli_queue_contract(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"recordings":[{"recording_id":"rec-1"}]}', encoding="utf-8")
    state = StateStore(tmp_path / "pipeline.json")
    from transcribe_intelligence.planner import plan_from_manifest
    from transcribe_intelligence.queue import enqueue

    jobs = enqueue(plan_from_manifest({"recordings":[{"recording_id":"rec-1"}]}, state), JobStore(tmp_path / "jobs.json"))
    assert len(jobs) == 9
    assert jobs[0].job_id == "rec-1:ingest"
