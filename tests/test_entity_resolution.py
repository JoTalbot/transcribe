from transcribe_intelligence.entities import EntityMention
from transcribe_intelligence.entity_resolution import CanonicalEntity, resolve_entities
from transcribe_intelligence.evidence import Evidence


def mention(text, kind="person"):
    ev = Evidence("e", "r", 0, 1, .8, "s", text, "test", "v1")
    return EntityMention("m", "r", text, kind, .8, ev)


def test_exact_alias_resolves():
    result = resolve_entities([mention("Иван Иванов")], [CanonicalEntity("p1", "person", "Ivan Ivanov", ("Иван Иванов",))])
    assert result[0].canonical_id == "p1"


def test_ambiguous_alias_stays_unresolved():
    catalog = [CanonicalEntity("p1", "person", "Ivan", ()), CanonicalEntity("p2", "person", "Иван", ())]
    assert resolve_entities([mention("Иван")], catalog)[0].canonical_id is None
