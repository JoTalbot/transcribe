"""Build and inspect a resumable execution plan for the audio corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transcribe_intelligence.planner import PlanItem, plan_from_manifest
from transcribe_intelligence.state_store import StateStore


def load_manifest(path: Path) -> dict[str, object]:
    """Load and minimally validate a build_manifest.py output."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def format_plan(items: list[PlanItem]) -> str:
    """Render a stable human-readable plan."""
    if not items:
        return "No pending stages."
    lines = [f"Pending stages: {len(items)}"]
    current_recording: str | None = None
    for item in items:
        if item.recording_id != current_recording:
            current_recording = item.recording_id
            lines.append(f"\n{current_recording}")
        lines.append(f"  - {item.stage.value}: {item.status}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path("state/pipeline.json"))
    parser.add_argument("--recording", help="Restrict the plan to one recording_id")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the plan without mutating state or running inference",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest.expanduser().resolve())
    store = StateStore(args.state.expanduser().resolve())
    items = plan_from_manifest(manifest, store)
    if args.recording:
        items = [item for item in items if item.recording_id == args.recording]
    print(format_plan(items))
    if args.plan_only or items:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
