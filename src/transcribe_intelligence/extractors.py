"""Conservative, dependency-free extractors used before model-backed enrichment."""
from __future__ import annotations

import re
from collections.abc import Iterable

from .entities import NameMention
from .evidence import Evidence
from .text_analysis import candidate_name_mentions

_PERSON_CONTEXT = re.compile(r"\b(?:имя|зовут|это|познакомься|меня)\s+([А-ЯЁІЇЄҐ][\wА-Яа-яЁёІіЇїЄєҐґ'-]{1,30})", re.IGNORECASE)


def extract_name_candidates(text: str, recording_id: str, segment_id: str, start: float, end: float, speaker: str | None = None) -> list[NameMention]:
    """Extract name hypotheses with evidence; never resolve them to people."""
    matches = _PERSON_CONTEXT.findall(text)
    candidates = matches or candidate_name_mentions(text)
    seen: set[str] = set()
    result: list[NameMention] = []
    for name in candidates:
        normalized = name.strip(".,!?;:()[]{}\"")
        key = normalized.casefold()
        if len(normalized) < 2 or key in seen:
            continue
        seen.add(key)
        confidence = 0.82 if matches else 0.45
        evidence = Evidence(
            evidence_id=f"{recording_id}:{segment_id}:name:{key}",
            recording_id=recording_id,
            start=start,
            end=end,
            confidence=confidence,
            segment_id=segment_id,
            text=text,
            method="name-context-rule" if matches else "capitalized-token-candidate",
            model_version="rules-v1",
        )
        result.append(NameMention(normalized, recording_id, confidence, evidence, speaker))
    return result


def extract_topics(text: str, topic_rules: dict[str, Iterable[str]]) -> list[tuple[str, float]]:
    """Return deterministic topic candidates from configurable keyword rules."""
    normalized = text.casefold()
    found: list[tuple[str, float]] = []
    for topic, keywords in sorted(topic_rules.items()):
        hits = sum(1 for keyword in keywords if str(keyword).casefold() in normalized)
        if hits:
            found.append((topic, min(1.0, 0.35 + 0.15 * hits)))
    return found
