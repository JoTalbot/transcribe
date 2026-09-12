from transcribe_intelligence.entities import EntityMention, NameMention, evidence_payload
from transcribe_intelligence.evidence import Evidence


def evidence():
    return Evidence("ev1", "rec1", 1.0, 2.0, 0.9, "seg1", "Иван позвонил", "rule", "test")


def test_entity_keeps_provenance():
    item = EntityMention("e1", "rec1", "Иван", "person", 0.8, evidence())
    payload = evidence_payload(item)
    assert payload["evidence"]["segment_id"] == "seg1"
    assert payload["canonical_id"] is None


def test_name_is_not_identity():
    item = NameMention("Иван", "rec1", 0.7, evidence(), "SPEAKER_00")
    assert item.speaker_label == "SPEAKER_00"
    assert not hasattr(item, "person_id")
