"""Build a resumable execution plan without running inference."""
from __future__ import annotations

from dataclasses import dataclass

from .pipeline_contract import Stage
from .state_store import StateStore


@dataclass(frozen=True, slots=True)
class PlanItem:
    recording_id: str
    stage: Stage
    status: str


def plan_recording(recording_id: str, state: StateStore) -> list[PlanItem]:
    """Return stages that are not already completed, preserving pipeline order."""
    items: list[PlanItem] = []
    for stage in Stage:
        current = state.get(recording_id, stage.value)
        if current and current.status == "completed" and current.artifact_id:
            continue
        items.append(PlanItem(recording_id, stage, current.status if current else "pending"))
    return items


def plan_from_manifest(manifest: dict[str, object], state: StateStore) -> list[PlanItem]:
    """Create a deterministic plan for every recording in a manifest."""
    recordings = manifest.get("recordings", [])
    if not isinstance(recordings, list):
        raise ValueError("manifest recordings must be a list")
    result: list[PlanItem] = []
    for recording in recordings:
        if not isinstance(recording, dict) or not recording.get("recording_id"):
            raise ValueError("each recording needs a recording_id")
        result.extend(plan_recording(str(recording["recording_id"]), state))
    return result
