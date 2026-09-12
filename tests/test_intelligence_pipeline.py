import pytest

from transcribe_intelligence.intelligence_pipeline import SegmentInput, group_by_recording, run_stage
from transcribe_intelligence.pipeline_contract import Stage


def test_run_stage_is_stable_and_sorted():
    items = [
        SegmentInput("b", "rec", 2, 3, "two"),
        SegmentInput("a", "rec", 1, 2, "one"),
    ]
    assert run_stage(items, Stage.TOPICS, lambda item: [item.text]) == ["one", "two"]


def test_group_by_recording_sorts_segments():
    items = [SegmentInput("b", "r", 2, 3, "b"), SegmentInput("a", "r", 1, 2, "a")]
    assert [x.segment_id for x in group_by_recording(items)["r"]] == ["a", "b"]


def test_run_stage_rejects_non_intelligence_stage():
    with pytest.raises(ValueError):
        run_stage([], Stage.ASR, lambda _: [])
