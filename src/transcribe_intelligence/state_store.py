"""Persistent, dependency-free stage state for resumable processing."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StageState:
    recording_id: str
    stage: str
    status: str = "pending"
    artifact_id: str | None = None
    model_version: str | None = None
    error: str | None = None
    updated_at: str | None = None


class StateStore:
    """Atomically persist stage state keyed by recording and stage."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, StageState]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: StageState(**value) for key, value in raw.items()}

    def get(self, recording_id: str, stage: str) -> StageState | None:
        return self.load().get(self.key(recording_id, stage))

    @staticmethod
    def key(recording_id: str, stage: str) -> str:
        return f"{recording_id}:{stage}"

    def set(self, state: StageState) -> None:
        records = self.load()
        updated = StageState(
            **{**asdict(state), "updated_at": state.updated_at or now_iso()}
        )
        records[self.key(state.recording_id, state.stage)] = updated
        payload = {key: asdict(value) for key, value in sorted(records.items())}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
