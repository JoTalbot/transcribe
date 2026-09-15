from pathlib import Path

from scripts.oracle_local_worker import process_one
from transcribe_intelligence.exchange import FileExchange, JobEnvelope, ResultEnvelope


class StubProcessor:
    def __init__(self, artifact_id: str):
        self.artifact_id = artifact_id
        self.calls: list[str] = []

    def process(self, request: JobEnvelope) -> ResultEnvelope:
        self.calls.append(request.job_id)
        return ResultEnvelope(request.job_id, "completed", artifact_id=self.artifact_id)


def test_process_one_claims_routes_and_publishes_local_job(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    audio = StubProcessor("recording:ingest:source")
    intelligence = StubProcessor("recording:text_analysis:json")
    request = JobEnvelope(
        "recording:ingest",
        "recording",
        "ingest",
        worker="oracle-local",
        lease_id="lease-1",
    )
    exchange.put_request(request)

    result = process_one(exchange, request.job_id, audio, intelligence)

    assert result == ResultEnvelope(
        request.job_id,
        "completed",
        artifact_id="recording:ingest:source",
        worker="oracle-local",
        lease_id="lease-1",
    )
    assert audio.calls == [request.job_id]
    assert intelligence.calls == []
    assert exchange.get_result(request.job_id) == result
    assert not (exchange.requests / f"{request.job_id}.json").exists()
    assert not (exchange.root / "processing" / f"{request.job_id}.json").exists()


def test_process_one_routes_intelligence_stage(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    audio = StubProcessor("audio")
    intelligence = StubProcessor("recording:graph:json")
    request = JobEnvelope(
        "recording:graph",
        "recording",
        "graph",
        input_artifact_id="recording:linking:json",
        worker="oracle-local",
        lease_id="lease-2",
    )
    exchange.put_request(request)

    result = process_one(exchange, request.job_id, audio, intelligence)

    assert result is not None
    assert result.status == "completed"
    assert result.artifact_id == "recording:graph:json"
    assert result.worker == "oracle-local"
    assert result.lease_id == "lease-2"
    assert audio.calls == []
    assert intelligence.calls == [request.job_id]


def test_process_one_ignores_non_local_stage(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    audio = StubProcessor("audio")
    intelligence = StubProcessor("text")
    request = JobEnvelope(
        "recording:asr",
        "recording",
        "asr",
        worker="colab-gpu",
        lease_id="lease-3",
    )
    exchange.put_request(request)

    assert process_one(exchange, request.job_id, audio, intelligence) is None
    assert exchange.get_request(request.job_id) == request
    assert audio.calls == []
    assert intelligence.calls == []
