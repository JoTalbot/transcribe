import pytest

from transcribe_intelligence.colab_backend import ColabExecutionBackend, ColabJobRequest
from transcribe_intelligence.execution import ExecutionResult
from transcribe_intelligence.job_store import ExecutionJob


def test_colab_backend_builds_transport_request():
    seen = []

    def submit(request: ColabJobRequest):
        seen.append(request)
        return ExecutionResult(request.job_id, "completed", "artifact:1")

    job = ExecutionJob("r:asr", "r", "asr")
    result = ColabExecutionBackend(submit).execute(job)

    assert seen == [ColabJobRequest("r:asr", "r", "asr")]
    assert result.artifact_id == "artifact:1"


def test_colab_backend_rejects_invalid_transport_result():
    with pytest.raises(TypeError):
        ColabExecutionBackend(lambda _: "bad").execute(ExecutionJob("r:asr", "r", "asr"))
