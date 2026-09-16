from pathlib import Path
import threading

import pytest

from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope, ResultEnvelope


def test_request_and_result_round_trip(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    request = JobEnvelope("r1:asr", "r1", "asr", "normalized:r1", worker="colab-1", lease_id="lease-1")
    result = ResultEnvelope("r1:asr", "completed", artifact_id="asr:r1", worker="colab-1", lease_id="lease-1")

    exchange.put_request(request)
    exchange.put_result(result)

    assert exchange.get_request("r1:asr") == request
    assert exchange.get_result("r1:asr") == result
    assert exchange.list_requests() == [tmp_path / "exchange" / "requests" / "r1:asr.json"]


def test_result_requires_artifact_when_completed(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    with pytest.raises(ValueError):
        exchange.put_result(ResultEnvelope("r1:asr", "completed"))


def test_request_id_mismatch_is_rejected(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    exchange.put_request(JobEnvelope("actual", "r1", "asr"))
    path = exchange.requests / "claimed.json"
    path.write_text('{"job_id":"other","recording_id":"r1","stage":"asr"}\n', encoding="utf-8")
    with pytest.raises(ExchangeError, match="id mismatch"):
        exchange.get_request("claimed")


def test_lease_identity_round_trip_is_optional_for_legacy_exchange_records(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    result = ResultEnvelope("r1:asr", "failed", error="legacy worker")
    exchange.put_result(result)
    assert exchange.get_result("r1:asr") == result


@pytest.mark.parametrize("job_id", ["../escape", "nested/job", "nested\\job", ".", ".."])
def test_job_id_cannot_escape_exchange_directory(tmp_path: Path, job_id: str) -> None:
    exchange = FileExchange(tmp_path / "exchange")

    with pytest.raises(ValueError, match="single filesystem-safe path component"):
        exchange.put_request(JobEnvelope(job_id, "r1", "asr"))

    with pytest.raises(ValueError, match="single filesystem-safe path component"):
        exchange.get_request(job_id)

    with pytest.raises(ValueError, match="single filesystem-safe path component"):
        exchange.put_result(ResultEnvelope(job_id, "failed", error="invalid id"))

    with pytest.raises(ValueError, match="single filesystem-safe path component"):
        exchange.get_result(job_id)


def test_concurrent_writers_do_not_share_exchange_temp_file(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def writer(worker: str) -> None:
        try:
            barrier.wait(timeout=5)
            exchange.put_request(JobEnvelope("concurrent", "r1", "asr", worker=worker, lease_id=worker))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(worker,)) for worker in ("worker-a", "worker-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    stored = exchange.get_request("concurrent")
    assert stored.worker in {"worker-a", "worker-b"}
    assert not list((exchange.requests).glob(".*.tmp"))
