"""Conservative relation and event extraction contracts from utterance text."""
from __future__ import annotations

import re
from typing import Iterable

from .entities import EventMention, RelationMention
from .evidence import Evidence

_REQUEST = re.compile(r"\b(позвони|перезвони|отправь|пришли|сделай|проверь|call|send|check)\b", re.I)
_EVENT = re.compile(r"\b(встреч|созвон|звонок|оплат|встреча|meeting|call|payment)\w*\b", re.I)


def extract_relation_candidates(recording_id: str, segment_id: str, text: str, *, speaker: str | None = None) -> list[RelationMention]:
    """Return only high-signal action relations; no entity identity is inferred."""
    if not _REQUEST.search(text):
        return []
    evidence = Evidence(f"{recording_id}:{segment_id}:relation", recording_id, 0.0, 0.0, 0.55, segment_id, text, "rule_relation", "rules-v1")
    subject = speaker or "UNKNOWN_SPEAKER"
    return [RelationMention(f"{recording_id}:{segment_id}:relation", recording_id, subject, "requested_action", "UNRESOLVED_OBJECT", .55, evidence)]


def extract_event_candidates(recording_id: str, segment_id: str, text: str, *, start: float = 0.0, end: float = 0.0) -> list[EventMention]:
    """Detect event-like lexical cues while retaining conservative uncertainty."""
    if not _EVENT.search(text):
        return []
    evidence = Evidence(f"{recording_id}:{segment_id}:event", recording_id, start, end, .55, segment_id, text, "rule_event", "rules-v1")
    return [EventMention(f"{recording_id}:{segment_id}:event", recording_id, "conversation_event", .55, evidence)]
