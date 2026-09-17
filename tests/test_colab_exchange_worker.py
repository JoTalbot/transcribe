from pathlib import Path
import time

import pytest

from scripts.colab_exchange_worker import claim_request, dry_run_processor, process_one, write_metrics
from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope


def test_process_one_claims_and_publishes_result(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j1", "r1", "asr", "input-1", worker="colab-gpu", lease_id="lease-1"))

    result = process_one(exchange, "j1", dry_run_processor)

    assert result.status == "completed"
    assert result.artifact_id == "dry-run:j1"
    assert result.worker == "colab-gpu"
    assert result.lease_id == "lease-1"
    assert not (exchange.requests / "j1.json").exists()
    assert not (exchange.root / "processing" / "j1.json").exists()
    assert exchange.get_result("j1") == result


def test_process_one_publishes_failure_for_processor_error(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j2", "r2", "diarization", worker="colab-gpu", lease_id="lease-2"))

    def broken(_request):
        raise RuntimeError("GPU unavailable")

    result = process_one(exchange, "j2", broken)

    assert result.status == "failed"
    assert result.error == "GPU unavailable"
    assert result.artifact_id is None
    assert result.worker == "colab-gpu"
    assert result.lease_id == "lease-2"
    assert exchange.get_result("j2") == result


def test_process_one_quarantines_missing_worker_instead_of_leaking_processing_marker(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j3", "r3", "asr"))

    with pytest.raises(ExchangeError, match="missing worker or lease_id"):
        process_one(exchange, "j3", dry_run_processor)

    assert not (exchange.root / "processing" / "j3.json").exists()
    assert (exchange.results / "quarantine" / "j3.json").exists()


def test_process_one_quarantines_request_owned_by_oracle_local(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j-local", "r-local", "text_analysis", worker="oracle-local", lease_id="lease-local"))

    with pytest.raises(ExchangeError, match="cannot claim request for worker 'oracle-local'"):
        process_one(exchange, "j-local", dry_run_processor)

    assert not (exchange.root / "processing" / "j-local.json").exists()
    assert (exchange.results / "quarantine" / "j-local.json").exists()
    assert not (exchange.results / "j-local.json").exists()


def test_process_one_quarantines_unsupported_stage(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j-unsupported", "r", "text_analysis", worker="colab-gpu", lease_id="lease"))

    with pytest.raises(ExchangeError, match="does not support stage 'text_analysis'"):
        process_one(exchange, "j-unsupported", dry_run_processor)

    assert not (exchange.root / "processing" / "j-unsupported.json").exists()
    assert (exchange.results / "quarantine" / "j-unsupported.json").exists()


def test_process_one_releases_processing_marker_when_result_publish_fails(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j4", "r4", "asr", worker="colab-gpu", lease_id="lease-4"))

    original_put_result = exchange.put_result

    def broken_publish(_result):
        raise OSError("exchange storage unavailable")

    exchange.put_result = broken_publish  # type: ignore[method-assign]
    with pytest.raises(OSError, match="exchange storage unavailable"):
        process_one(exchange, "j4", dry_run_processor)

    exchange.put_result = original_put_result  # type: ignore[method-assign]
    assert not (exchange.requests / "j4.json").exists()
    assert not (exchange.root / "processing" / "j4.json").exists()


def test_process_one_never_overwrites_existing_processing_claim(tmp_path: Path):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j5", "r5", "asr", worker="colab-gpu", lease_id="lease-new"))
    processing = exchange.root / "processing"
    processing.mkdir(parents=True, exist_ok=True)
    (processing / "j5.json").write_text(
        '{"job_id":"j5","recording_id":"r5","stage":"asr","worker":"colab-gpu","lease_id":"lease-old"}',
        encoding="utf-8",
    )

    with pytest.raises(ExchangeError, match="processing claim already exists"):
        process_one(exchange, "j5", dry_run_processor)

    assert (exchange.requests / "j5.json").exists()
    assert (processing / "j5.json").read_text(encoding="utf-8").find("lease-old") >= 0
    assert not (exchange.results / "j5.json").exists()


def test_claim_request_preserves_exclusive_claim_when_source_unlink_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("j6", "r6", "asr", "input-6", worker="colab-gpu", lease_id="lease-6"))
    source = exchange.requests / "j6.json"
    processing = exchange.root / "processing" / "j6.json"
    original_unlink = Path.unlink

    def fail_source_unlink(path: Path, *args, **kwargs):
        if path == source:
            raise OSError("request storage temporarily unavailable")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source_unlink)

    with pytest.raises(OSError, match="request storage temporarily unavailable"):
        claim_request(exchange, "j6")

    assert source.exists()
    assert processing.exists()
    assert processing.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_write_metrics_uses_monotonic_elapsed_time(tmp_path: Path):
    started_at_unix = time.time()
    started_perf = time.perf_counter()
    time.sleep(0.001)

    path = write_metrics(tmp_path, started_at_unix, started_perf, {"total_model_load_seconds": 1.25}, [])
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert payload["started_at_unix"] == started_at_unix
    assert payload["wall_clock_seconds"] >= 0
    assert payload["model_load_seconds"]["total_model_load_seconds"] == 1.25
    assert payload["jobs"] == []
    assert path.name.startswith("worker-metrics-")
