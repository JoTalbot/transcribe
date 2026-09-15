from pathlib import Path

import pytest

from scripts.sync_drive import _safe_relative_name, list_drive_media


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
