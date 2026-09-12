"""Evidence-backed entity, name, topic, intent, relation and event contracts."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .evidence import Evidence


@dataclass(frozen=True, slots=True)
class EntityMention:
    entity_id: str
    recording_id: str
    text: str
    entity_type: str
    confidence: float
    evidence: Evidence
    canonical_id: str | None = None


@dataclass(frozen=True, slots=True)
class NameMention:
    name: str
    recording_id: str
    confidence: float
    evidence: Evidence
    speaker_label: str | None = None


@dataclass(frozen=True, slots=True)
class TopicMention:
    topic_id: str
    recording_id: str
    label: str
    confidence: float
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class IntentMention:
    intent_id: str
    recording_id: str
    label: str
    confidence: float
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class RelationMention:
    relation_id: str
    recording_id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class EventMention:
    event_id: str
    recording_id: str
    event_type: str
    confidence: float
    evidence: Evidence
    participants: tuple[str, ...] = ()


def evidence_payload(item: Any) -> dict[str, Any]:
    """Serialize an intelligence object while retaining its provenance."""
    payload = asdict(item)
    payload["evidence"] = asdict(item.evidence)
    return payload
