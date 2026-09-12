from pathlib import Path

import pytest

from transcribe_intelligence.exchange import ExchangeError, FileExchange, JobEnvelope, ResultEnvelope


def test_request_and_result_round_trip(tmp_path: Path) -> None:
    exchange = FileExchange(tmp_path / "exchange")
    request = JobEnvelope("r1:asr", "r1", "asr", "normalized:r1")
    result = ResultEnvelope("r1:asr", "completed", artifact_id="asr:r1")

    exchange.put_request(request)
    exchange.put_result(result)

    assert exchange.get_request("r1:asr") == request
    assert exchange.get_result("r1:asr") == result
    assert exchange.list_requests() == [tmp_path / "exchange" / "jobs" / "r1:asr.json"]


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
