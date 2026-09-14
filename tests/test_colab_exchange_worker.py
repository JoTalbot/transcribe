from pathlib import Path

import pytest

from scripts.colab_exchange_worker import dry_run_processor, process_one
from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope


def test_process_one_claims_and_publishes_result(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j1", "r1", "asr", "input-1", worker="worker-a", lease_id="lease-1"))

    result = process_one(exchange, "j1", dry_run_processor)

    assert result.status == "completed"
    assert result.artifact_id == "dry-run:j1"
    assert result.worker == "worker-a"
    assert result.lease_id == "lease-1"
    assert not (exchange.requests / "j1.json").exists()
    assert not (exchange.root / "processing" / "j1.json").exists()
    assert exchange.get_result("j1") == result


def test_process_one_publishes_failure_for_processor_error(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j2", "r2", "diarization", worker="worker-a", lease_id="lease-2"))

    def broken(_request):
        raise RuntimeError("GPU unavailable")

    result = process_one(exchange, "j2", broken)

    assert result.status == "failed"
    assert result.error == "GPU unavailable"
    assert result.artifact_id is None
    assert result.worker == "worker-a"
    assert result.lease_id == "lease-2"
    assert exchange.get_result("j2") == result


def test_process_one_quarantines_malformed_claim_instead_of_leaking_processing_marker(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j3", "r3", "asr"))

    with pytest.raises(ExchangeError, match="missing worker or lease_id"):
        process_one(exchange, "j3", dry_run_processor)

    assert not (exchange.root / "processing" / "j3.json").exists()
    assert (exchange.results / "quarantine" / "j3.json").exists()
