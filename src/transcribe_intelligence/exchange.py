"""Atomic filesystem exchange for orchestrator and Colab workers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class JobEnvelope:
    job_id: str
    recording_id: str
    stage: str
    input_artifact_id: str | None = None
    input_artifact_ids: tuple[str, ...] = ()
    input_path: str | None = None
    worker: str | None = None
    lease_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResultEnvelope:
    job_id: str
    status: str
    artifact_id: str | None = None
    error: str | None = None
    worker: str | None = None
    lease_id: str | None = None


class ExchangeError(RuntimeError):
    """Raised when an exchange record is malformed or inconsistent."""


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExchangeError(f"cannot read exchange record {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExchangeError(f"exchange record {path} must contain an object")
    return payload


class FileExchange:
    """Simple Drive-compatible contract using atomic JSON files."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.requests = self.root / "jobs"
        self.results = self.root / "results"

    def put_request(self, request: JobEnvelope) -> Path:
        if not request.job_id.strip() or not request.recording_id.strip() or not request.stage.strip():
            raise ValueError("job_id, recording_id and stage must not be empty")
        path = self.requests / f"{request.job_id}.json"
        _write_json_atomic(path, asdict(request))
        return path

    def get_request(self, job_id: str) -> JobEnvelope:
        payload = _read_json(self.requests / f"{job_id}.json")
        try:
            request = JobEnvelope(**payload)
        except TypeError as exc:
            raise ExchangeError(f"invalid job request {job_id}") from exc
        if request.job_id != job_id:
            raise ExchangeError(f"job request id mismatch: expected {job_id}, got {request.job_id}")
        return request

    def put_result(self, result: ResultEnvelope) -> Path:
        if not result.job_id.strip() or not result.status.strip():
            raise ValueError("job_id and status must not be empty")
        if result.status == "completed" and not result.artifact_id:
            raise ValueError("completed result requires artifact_id")
        path = self.results / f"{result.job_id}.json"
        _write_json_atomic(path, asdict(result))
        return path

    def get_result(self, job_id: str) -> ResultEnvelope:
        payload = _read_json(self.results / f"{job_id}.json")
        try:
            result = ResultEnvelope(**payload)
        except TypeError as exc:
            raise ExchangeError(f"invalid job result {job_id}") from exc
        if result.job_id != job_id:
            raise ExchangeError(f"job result id mismatch: expected {job_id}, got {result.job_id}")
        return result

    def list_requests(self) -> list[Path]:
        self.requests.mkdir(parents=True, exist_ok=True)
        return sorted(self.requests.glob("*.json"))
