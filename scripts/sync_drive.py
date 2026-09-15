"""Inspect a Drive/local transcription queue and optionally download Drive audio."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".webm", ".mp4", ".mov", ".mkv"}


def load_credentials(path: str | None) -> Any:
    if not path:
        return None
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )


def _is_media(name: str, mime_type: str | None = None) -> bool:
    suffix = Path(name).suffix.lower()
    return suffix in AUDIO_EXTS or bool(
        mime_type and mime_type.startswith(("audio/", "video/"))
    )


def _safe_relative_name(name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe Drive path: {name!r}")
    return path


def list_drive_media(service: Any, folder_id: str) -> list[dict[str, Any]]:
    """List media files directly under a Drive folder, handling pagination."""
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None
    files: list[dict[str, Any]] = []
    while True:
        response = service.files().list(
            q=query,
            pageSize=1000,
            pageToken=page_token,
            fields="nextPageToken,files(id,name,mimeType,modifiedTime,size)",
        ).execute()
        files.extend(
            item
            for item in response.get("files", [])
            if _is_media(item.get("name", ""), item.get("mimeType"))
        )
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def download_drive_file(service: Any, file_id: str, destination: Path) -> None:
    """Stream one Drive file to disk atomically."""
    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        request = service.files().get_media(fileId=file_id)
        with temporary.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _processed_paths(processed: dict[str, Any]) -> set[str]:
    """Return paths recorded by both local and Drive processing."""
    paths: set[str] = set()
    for key, value in processed.items():
        if isinstance(value, dict) and isinstance(value.get("path"), str):
            paths.add(value["path"])
        elif not key.startswith("drive:"):
            paths.add(key)
    return paths


def download_drive_media(service: Any, folder_id: str, incoming: Path, processed: dict[str, Any]) -> int:
    """Download unprocessed media files from a Drive folder into input/."""
    downloaded = 0
    for item in list_drive_media(service, folder_id):
        relative = _safe_relative_name(item["name"])
        key = f"drive:{item['id']}"
        destination = incoming / relative
        record = processed.get(key)
        if isinstance(record, dict) and destination.is_file():
            stored_mtime = record.get("modifiedTime")
            if stored_mtime is None or stored_mtime == item.get("modifiedTime"):
                continue
        download_drive_file(service, item["id"], destination)
        processed[key] = {
            "name": item["name"],
            "path": str(relative),
            "modifiedTime": item.get("modifiedTime"),
            "size": item.get("size"),
        }
        downloaded += 1
    return downloaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="./transcribe", help="Mounted/local transcription root")
    parser.add_argument("--credentials", default=os.getenv("GDRIVE_CREDENTIALS"))
    parser.add_argument(
        "--folder-id",
        default=os.getenv("GDRIVE_FOLDER_ID"),
        help="Drive folder ID to download from",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download audio/video from --folder-id into input/",
    )
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

    if args.download and not args.folder_id:
        print("ERROR: --download requires --folder-id or GDRIVE_FOLDER_ID")
        return 2

    if args.credentials:
        try:
            credentials = load_credentials(args.credentials)
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            service.files().list(pageSize=1, fields="files(id,name)").execute()
            print("Drive API: credentials accepted")
            if args.download:
                count = download_drive_media(service, args.folder_id, incoming, processed)
                registry.write_text(
                    json.dumps(processed, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"Drive download: {count} file(s)")
        except Exception as exc:
            print(f"Drive API check failed: {exc}")
            return 3
    elif args.download:
        print("ERROR: --download requires --credentials")
        return 2
    else:
        print("Drive API: not configured; using mounted/local filesystem mode")

    files = sorted(
        p for p in incoming.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )
    processed_paths = _processed_paths(processed)
    pending = [p for p in files if str(p.relative_to(incoming)) not in processed_paths]
    print(f"Root: {root}\nAudio/video files: {len(files)}\nProcessed: {len(processed_paths)}\nPending: {len(pending)}")
    for path in pending:
        print(f"PENDING {path.relative_to(incoming)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
