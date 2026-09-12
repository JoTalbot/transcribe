from transcribe_intelligence.extractors import extract_name_candidates, extract_topics


def test_name_context_gets_higher_confidence():
    items = extract_name_candidates("Меня зовут Иван", "r1", "s1", 1.0, 2.0, "SPEAKER_00")
    assert items[0].name == "Иван"
    assert items[0].confidence > 0.8
    assert items[0].evidence.segment_id == "s1"


def test_topic_rules_are_configurable():
    assert extract_topics("обсудим договор и оплату", {"sales": ["договор", "оплату"]}) == [("sales", 0.65)]
