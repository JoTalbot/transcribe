from pathlib import Path

from scripts.colab_exchange_worker import dry_run_processor, process_one
from transcribe_intelligence.exchange import FileExchange, JobEnvelope


def test_process_one_claims_and_publishes_result(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j1", "r1", "asr", "input-1"))

    result = process_one(exchange, "j1", dry_run_processor)

    assert result.status == "completed"
    assert result.artifact_id == "dry-run:j1"
    assert not (exchange.requests / "j1.json").exists()
    assert not (exchange.root / "processing" / "j1.json").exists()
    assert exchange.get_result("j1") == result


def test_process_one_publishes_failure_for_processor_error(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j2", "r2", "diarization"))

    def broken(_request):
        raise RuntimeError("GPU unavailable")

    result = process_one(exchange, "j2", broken)

    assert result.status == "failed"
    assert result.error == "GPU unavailable"
    assert result.artifact_id is None
    assert exchange.get_result("j2") == result
