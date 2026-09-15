from transcribe_intelligence.colab_backend import ColabExecutionBackend, ColabJobRequest, FileColabSubmitter
from transcribe_intelligence.execution import ExecutionResult
from transcribe_intelligence.exchange import FileExchange
from transcribe_intelligence.job_store import ExecutionJob


def test_colab_backend_builds_transport_request_with_lease_identity():
    seen = []

    def submit(request: ColabJobRequest):
        seen.append(request)
        return ExecutionResult(request.job_id, "completed", "artifact:1")

    job = ExecutionJob("r:asr", "r", "asr", "running", 1, worker="oracle", lease_id="lease-1")
    result = ColabExecutionBackend(submit).execute(job)

    assert seen == [ColabJobRequest("r:asr", "r", "asr", worker="oracle", lease_id="lease-1")]
    assert result.artifact_id == "artifact:1"


def test_colab_backend_rejects_invalid_transport_result():
    import pytest

    with pytest.raises(TypeError):
        ColabExecutionBackend(lambda _: "bad").execute(ExecutionJob("r:asr", "r", "asr"))


def test_file_colab_submitter_preserves_worker_and_lease_identity(tmp_path):
    exchange = FileExchange(tmp_path / "exchange")
    request = ColabJobRequest("r:asr", "r", "asr", "r:normalize:audio", worker="colab-gpu", lease_id="lease-9")

    def worker():
        queued = exchange.get_request("r:asr")
        assert queued.worker == "colab-gpu"
        assert queued.lease_id == "lease-9"
        exchange.put_result(__import__("transcribe_intelligence.exchange", fromlist=["ResultEnvelope"]).ResultEnvelope("r:asr", "completed", "r:asr:json", worker=queued.worker, lease_id=queued.lease_id))

    import threading
    thread = threading.Thread(target=lambda: (threading.Event().wait(0.05), worker()))
    thread.start()
    result = FileColabSubmitter(exchange, poll_seconds=0.01, timeout_seconds=1)(request)
    thread.join(timeout=1)

    assert result.status == "completed"
    assert result.artifact_id == "r:asr:json"
