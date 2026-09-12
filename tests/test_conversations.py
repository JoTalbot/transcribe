from transcribe_intelligence.conversations import link_topic_mentions
from transcribe_intelligence.entities import TopicMention
from transcribe_intelligence.evidence import Evidence


def topic(tid, rec):
    ev = Evidence(f"{tid}:e", rec, 1, 2, .8, tid, "topic", "test", "v1")
    return TopicMention(tid, rec, "topic", .8, ev)


def test_links_similar_topics_across_recordings():
    links = link_topic_mentions([topic("t1", "r1"), topic("t2", "r2")], {"t1": (1, 0), "t2": (1, 0)}, .8)
    assert links[0].recording_ids == ("r1", "r2")


def test_does_not_link_missing_embeddings():
    assert link_topic_mentions([topic("t1", "r1"), topic("t2", "r2")], {"t1": (1, 0)}, .8) == []
