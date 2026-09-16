"""Audit artifact manifests and payloads without modifying the artifact store."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for root in (PROJECT_ROOT, SRC_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from transcribe_intelligence.artifacts import ArtifactManifest, verify_manifest


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _payload_candidates(manifest_path: Path, manifest: ArtifactManifest, root: Path) -> list[Path]:
    declared = Path(manifest.path).expanduser()
    candidates: list[Path] = []
    if declared.is_absolute():
        candidates.append(declared.resolve())
        candidates.append((manifest_path.parent / declared.name).resolve())
    else:
        candidates.append((root / declared).resolve())
    return list(dict.fromkeys(candidates))


def audit_artifacts(root: Path) -> dict[str, object]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"artifact root is not a directory: {root}")

    issues: list[dict[str, str]] = []
    manifests: list[tuple[Path, ArtifactManifest]] = []
    by_id: dict[str, list[Path]] = {}
    expected_payloads: set[Path] = set()

    for manifest_path in sorted(root.rglob("*.manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = ArtifactManifest(**payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            issues.append({"type": "invalid_manifest", "path": _relative(manifest_path, root), "error": str(exc)})
            continue
        manifests.append((manifest_path, manifest))
        by_id.setdefault(manifest.artifact_id, []).append(manifest_path)

    for artifact_id, paths in sorted(by_id.items()):
        if len(paths) > 1:
            for path in paths:
                issues.append(
                    {
                        "type": "duplicate_artifact_id",
                        "artifact_id": artifact_id,
                        "path": _relative(path, root),
                    }
                )

    for manifest_path, manifest in manifests:
        declared = Path(manifest.path).expanduser()
        candidates = _payload_candidates(manifest_path, manifest, root)
        declared_resolved = (declared if declared.is_absolute() else root / declared).resolve()
        if not (root == declared_resolved or root in declared_resolved.parents):
            issues.append(
                {
                    "type": "path_outside_root",
                    "artifact_id": manifest.artifact_id,
                    "path": _relative(manifest_path, root),
                    "declared_path": manifest.path,
                }
            )
        in_root = [candidate for candidate in candidates if root == candidate or root in candidate.parents]
        if not in_root:
            continue
        payload_path = next((candidate for candidate in in_root if candidate.is_file()), None)
        if payload_path is None:
            issues.append(
                {
                    "type": "missing_payload",
                    "artifact_id": manifest.artifact_id,
                    "path": _relative(manifest_path, root),
                    "declared_path": manifest.path,
                }
            )
            continue
        expected_payloads.add(payload_path)
        try:
            verified = verify_manifest(
                ArtifactManifest(
                    artifact_id=manifest.artifact_id,
                    recording_id=manifest.recording_id,
                    stage=manifest.stage,
                    kind=manifest.kind,
                    path=str(payload_path),
                    sha256=manifest.sha256,
                    size_bytes=manifest.size_bytes,
                    producer=manifest.producer,
                    model_version=manifest.model_version,
                )
            )
        except OSError as exc:
            verified = False
            error = str(exc)
        else:
            error = "checksum or size verification failed"
        if not verified:
            issues.append(
                {
                    "type": "checksum_mismatch",
                    "artifact_id": manifest.artifact_id,
                    "path": _relative(payload_path, root),
                    "error": error,
                }
            )

    ignored_names = {".DS_Store"}
    for payload_path in sorted(root.rglob("*")):
        if not payload_path.is_file() or payload_path.name in ignored_names:
            continue
        if payload_path.name.endswith(".manifest.json") or payload_path.name.endswith(".tmp") or payload_path.name.startswith("."):
            continue
        resolved = payload_path.resolve()
        if resolved not in expected_payloads:
            issues.append({"type": "orphan_payload", "path": _relative(payload_path, root)})

    return {
        "schema_version": 1,
        "root": str(root),
        "manifest_count": len(manifests),
        "verified_payload_count": len(expected_payloads),
        "issue_count": len(issues),
        "healthy": not issues,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="artifact root to audit")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = audit_artifacts(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Artifact audit: {'HEALTHY' if report['healthy'] else 'ISSUES FOUND'}")
        print(f"manifests={report['manifest_count']} verified={report['verified_payload_count']} issues={report['issue_count']}")
        for issue in report["issues"]:
            print(f"- {issue['type']}: {issue.get('path', issue.get('artifact_id', ''))} {issue.get('error', '')}".rstrip())
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
