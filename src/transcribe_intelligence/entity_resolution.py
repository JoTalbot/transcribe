"""Conservative entity resolution using explicit aliases and evidence scores."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .entities import EntityMention


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


@dataclass(frozen=True, slots=True)
class CanonicalEntity:
    canonical_id: str
    entity_type: str
    canonical_name: str
    aliases: tuple[str, ...] = ()


def resolve_entities(mentions: Iterable[EntityMention], catalog: Iterable[CanonicalEntity]) -> list[EntityMention]:
    """Resolve only exact normalized aliases; ambiguous matches remain unresolved."""
    index: dict[tuple[str, str], set[str]] = {}
    for entity in catalog:
        for alias in (entity.canonical_name, *entity.aliases):
            index.setdefault((entity.entity_type, _key(alias)), set()).add(entity.canonical_id)
    resolved: list[EntityMention] = []
    for mention in mentions:
        ids = index.get((mention.entity_type, _key(mention.text)), set())
        canonical = next(iter(ids)) if len(ids) == 1 else None
        resolved.append(EntityMention(
            mention.entity_id, mention.recording_id, mention.text, mention.entity_type,
            mention.confidence, mention.evidence, canonical,
        ))
    return resolved
