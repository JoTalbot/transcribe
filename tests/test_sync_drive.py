from pathlib import Path

import pytest

from scripts import sync_drive
from scripts.sync_drive import _processed_paths, _safe_relative_name, list_drive_media


class _Files:
    def list(self, **kwargs):
        self.kwargs = kwargs
        return self

    def execute(self):
        return {
            "files": [
                {"id": "a1", "name": "call.wav", "mimeType": "audio/wav"},
                {"id": "v1", "name": "video.mp4", "mimeType": "video/mp4"},
                {"id": "t1", "name": "notes.txt", "mimeType": "text/plain"},
            ]
        }


class _Service:
    def __init__(self):
        self._files = _Files()

    def files(self):
        return self._files


def test_list_drive_media_filters_non_media():
    result = list_drive_media(_Service(), "folder-1")
    assert [item["id"] for item in result] == ["a1", "v1"]


def test_safe_relative_name_rejects_absolute_path():
    with pytest.raises(ValueError):
        _safe_relative_name("/escape.wav")


def test_safe_relative_name_accepts_nested_relative_path():
    assert _safe_relative_name("calls/2026/call.wav") == Path("calls/2026/call.wav")


def test_processed_paths_reconciles_drive_records_and_legacy_paths():
    processed = {
        "drive:file-1": {"path": "calls/drive.wav", "modifiedTime": "2026-09-15T10:00:00Z"},
        "calls/local.wav": {"completed": True},
        "drive:legacy": "legacy-marker",
    }

    assert _processed_paths(processed) == {"calls/drive.wav", "calls/local.wav"}


def test_download_drive_media_redownloads_modified_file(monkeypatch, tmp_path):
    processed = {
        "drive:file-1": {
            "path": "call.wav",
            "modifiedTime": "2026-09-15T10:00:00Z",
        }
    }
    (tmp_path / "call.wav").write_bytes(b"old")
    downloaded = []

    monkeypatch.setattr(
        sync_drive,
        "list_drive_media",
        lambda service, folder_id: [
            {
                "id": "file-1",
                "name": "call.wav",
                "modifiedTime": "2026-09-16T10:00:00Z",
                "size": "4",
            }
        ],
    )
    monkeypatch.setattr(
        sync_drive,
        "download_drive_file",
        lambda service, file_id, destination: downloaded.append((file_id, destination)),
    )

    count = sync_drive.download_drive_media(object(), "folder-1", tmp_path, processed)

    assert count == 1
    assert downloaded == [("file-1", tmp_path / "call.wav")]
    assert processed["drive:file-1"]["modifiedTime"] == "2026-09-16T10:00:00Z"
    assert processed["drive:file-1"]["size"] == "4"


def test_download_drive_media_skips_unchanged_existing_file(monkeypatch, tmp_path):
    processed = {
        "drive:file-1": {
            "path": "call.wav",
            "modifiedTime": "2026-09-15T10:00:00Z",
        }
    }
    (tmp_path / "call.wav").write_bytes(b"existing")
    downloaded = []

    monkeypatch.setattr(
        sync_drive,
        "list_drive_media",
        lambda service, folder_id: [
            {
                "id": "file-1",
                "name": "call.wav",
                "modifiedTime": "2026-09-15T10:00:00Z",
                "size": "8",
            }
        ],
    )
    monkeypatch.setattr(
        sync_drive,
        "download_drive_file",
        lambda service, file_id, destination: downloaded.append((file_id, destination)),
    )

    count = sync_drive.download_drive_media(object(), "folder-1", tmp_path, processed)

    assert count == 0
    assert downloaded == []
