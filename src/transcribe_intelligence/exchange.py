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

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_artifact_ids", tuple(self.input_artifact_ids))
        if self.input_artifact_id is None and self.input_artifact_ids:
            object.__setattr__(self, "input_artifact_id", self.input_artifact_ids[0])


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


def _validate_job_id(job_id: str) -> None:
    """Reject IDs that could escape an exchange subdirectory as path components."""
    if not job_id.strip():
        raise ValueError("job_id must not be empty")
    if (
        Path(job_id).name != job_id
        or job_id in {".", ".."}
        or "/" in job_id
        or "\\" in job_id
        or "\x00" in job_id
    ):
        raise ValueError("job_id must be a single filesystem-safe path component")


class FileExchange:
    """Drive-compatible exchange contract using atomic JSON files."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.requests = self.root / "requests"
        self.results = self.root / "results"

    def _request_path(self, job_id: str) -> Path:
        _validate_job_id(job_id)
        return self.requests / f"{job_id}.json"

    def _result_path(self, job_id: str) -> Path:
        _validate_job_id(job_id)
        return self.results / f"{job_id}.json"

    def put_request(self, request: JobEnvelope) -> Path:
        _validate_job_id(request.job_id)
        if not request.recording_id.strip() or not request.stage.strip():
            raise ValueError("recording_id and stage must not be empty")
        path = self._request_path(request.job_id)
        _write_json_atomic(path, asdict(request))
        return path

    def get_request(self, job_id: str) -> JobEnvelope:
        payload = _read_json(self._request_path(job_id))
        try:
            request = JobEnvelope(**payload)
        except TypeError as exc:
            raise ExchangeError(f"invalid job request {job_id}") from exc
        if request.job_id != job_id:
            raise ExchangeError(f"job request id mismatch: expected {job_id}, got {request.job_id}")
        return request

    def put_result(self, result: ResultEnvelope) -> Path:
        _validate_job_id(result.job_id)
        if not result.status.strip():
            raise ValueError("status must not be empty")
        if result.status == "completed" and not result.artifact_id:
            raise ValueError("completed result requires artifact_id")
        path = self._result_path(result.job_id)
        _write_json_atomic(path, asdict(result))
        return path

    def get_result(self, job_id: str) -> ResultEnvelope:
        payload = _read_json(self._result_path(job_id))
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
