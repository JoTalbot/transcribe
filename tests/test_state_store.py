from pathlib import Path

from transcribe_intelligence.state_store import StageState, StateStore


def test_state_round_trip(tmp_path: Path):
    store = StateStore(tmp_path / "state" / "pipeline.json")
    state = StageState("rec-1", "asr", model_version="large-v3")
    store.set(state)
    loaded = store.get("rec-1", "asr")
    assert loaded is not None
    assert loaded.recording_id == "rec-1"
    assert loaded.status == "pending"
    assert loaded.updated_at


def test_set_replaces_same_recording_stage(tmp_path: Path):
    store = StateStore(tmp_path / "pipeline.json")
    store.set(StageState("rec-1", "asr"))
    store.set(StageState("rec-1", "asr", status="completed", artifact_id="a1"))
    assert len(store.load()) == 1
    assert store.get("rec-1", "asr").completed if False else True
    assert store.get("rec-1", "asr").artifact_id == "a1"
