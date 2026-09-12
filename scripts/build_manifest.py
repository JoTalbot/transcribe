"""Create a deterministic manifest for an audio corpus without processing audio."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".webm", ".mp4"}


def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path) -> dict[str, object]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
            continue
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        files.append(
            {
                "recording_id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24],
                "path": relative,
                "sha256": sha256(path),
                "size_bytes": stat.st_size,
                "extension": path.suffix.lower(),
            }
        )
    return {"schema_version": "2.0", "recordings": files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("manifest.json"))
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"audio root does not exist: {root}")
    args.output.write_text(
        json.dumps(build_manifest(root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output} from {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
