from transcribe_intelligence.relations import extract_event_candidates, extract_relation_candidates


def test_relation_candidate_requires_action_signal():
    assert extract_relation_candidates("r", "s", "Отправь договор", speaker="SPEAKER_00")[0].subject_id == "SPEAKER_00"
    assert extract_relation_candidates("r", "s", "Сегодня хорошая погода") == []


def test_event_candidate_has_time_evidence():
    event = extract_event_candidates("r", "s", "Завтра встреча", start=2, end=4)[0]
    assert event.evidence.start == 2
    assert event.evidence.end == 4
