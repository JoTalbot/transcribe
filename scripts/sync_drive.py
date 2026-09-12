#!/usr/bin/env python3
"""Inspect a Drive/local transcription queue and prepare local directories."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".webm"}


def load_credentials(path: str | None) -> Any:
    if not path:
        return None
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="./transcribe", help="Mounted Drive root")
    parser.add_argument("--credentials", default=os.getenv("GDRIVE_CREDENTIALS"))
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    incoming, output, state = root / "input", root / "output", root / "state"
    for directory in (incoming, output, state):
        directory.mkdir(parents=True, exist_ok=True)

    registry = state / "processed.json"
    try:
        processed = json.loads(registry.read_text(encoding="utf-8")) if registry.exists() else {}
        if not isinstance(processed, dict):
            processed = {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {registry}: {exc}")
        return 2

    files = sorted(p for p in incoming.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
    pending = [p for p in files if str(p.relative_to(incoming)) not in processed]
    print(f"Root: {root}\nAudio files: {len(files)}\nProcessed: {len(processed)}\nPending: {len(pending)}")
    for path in pending:
        print(f"PENDING {path.relative_to(incoming)}")

    if args.credentials:
        try:
            credentials = load_credentials(args.credentials)
            from googleapiclient.discovery import build
            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            service.files().list(pageSize=1, fields="files(id,name)").execute()
            print("Drive API: credentials accepted")
        except Exception as exc:  # noqa: BLE001
            print(f"Drive API check failed: {exc}")
            return 3
    else:
        print("Drive API: not configured; using mounted/local filesystem mode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
