"""Small dependency-free registry for resumable pipeline artifacts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    stage: str
    input_id: str
    status: str = "completed"
    model_version: str | None = None


class ArtifactRegistry:
    """Persist stage results atomically in a JSON registry."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Artifact]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: Artifact(**value) for key, value in raw.items()}

    def record(self, artifact: Artifact) -> None:
        records = self.load()
        records[artifact.artifact_id] = artifact
        payload = {key: asdict(value) for key, value in sorted(records.items())}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
