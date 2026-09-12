from transcribe_intelligence.pipeline_contract import Stage, StageResult


def test_stage_values_are_stable():
    assert Stage.ASR.value == "asr"
    assert Stage.DIARIZATION.value == "diarization"


def test_stage_result_completion_requires_artifact():
    assert StageResult(Stage.ASR, "completed", "artifact-1").completed
    assert not StageResult(Stage.ASR, "completed").completed
    assert not StageResult(Stage.ASR, "failed", "artifact-1").completed
