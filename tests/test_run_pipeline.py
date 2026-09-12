from pathlib import Path

from transcribe_intelligence.planner import plan_from_manifest
from transcribe_intelligence.state_store import StageState, StateStore


def test_plan_from_manifest_is_deterministic(tmp_path: Path):
    store = StateStore(tmp_path / "pipeline.json")
    manifest = {"schema_version": "2.0", "recordings": [{"recording_id": "rec-2"}, {"recording_id": "rec-1"}]}
    plan = plan_from_manifest(manifest, store)
    assert [item.recording_id for item in plan[:2]] == ["rec-2", "rec-2"]
    assert len(plan) == 18


def test_plan_from_manifest_skips_completed_stage(tmp_path: Path):
    store = StateStore(tmp_path / "pipeline.json")
    store.set(StageState("rec-1", "ingest", "completed", "artifact-1"))
    manifest = {"recordings": [{"recording_id": "rec-1"}]}
    plan = plan_from_manifest(manifest, store)
    assert all(item.stage.value != "ingest" for item in plan)
    assert len(plan) == 8
