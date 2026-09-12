"""Small deterministic text-analysis helpers for the intelligence pipeline."""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[\wА-Яа-яЁёІіЇїЄєҐґ'-]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Collapse whitespace while preserving the original words and punctuation."""
    return " ".join(text.split())


def words(text: str) -> list[str]:
    """Return Unicode-aware word-like tokens in source order."""
    return _WORD_RE.findall(text)


def candidate_name_mentions(text: str) -> list[str]:
    """Return conservative capitalized-token candidates for later model review.

    This is intentionally only candidate extraction. It does not assert identity.
    """
    return [token for token in words(text) if token[:1].isupper() and len(token) > 1]
