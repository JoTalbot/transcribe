from pathlib import Path

from transcribe_intelligence.pipeline_contract import Stage
from transcribe_intelligence.state_store import StageState, StateStore
from transcribe_intelligence.planner import plan_recording


def test_plan_contains_all_stages_when_empty(tmp_path: Path):
    store = StateStore(tmp_path / "pipeline.json")
    plan = plan_recording("rec-1", store)
    assert [item.stage for item in plan] == list(Stage)


def test_plan_skips_completed_stage(tmp_path: Path):
    store = StateStore(tmp_path / "pipeline.json")
    store.set(StageState("rec-1", Stage.INGEST.value, "completed", "artifact-1"))
    plan = plan_recording("rec-1", store)
    assert plan[0].stage is Stage.NORMALIZE
    assert all(item.stage is not Stage.INGEST for item in plan)
