from transcribe_intelligence.linking import link_speakers
from transcribe_intelligence.speaker_embeddings import SpeakerEmbedding


def emb(eid, rec, vector):
    return SpeakerEmbedding(eid, rec, "SPEAKER_00", tuple(vector), "v1")


def test_links_only_cross_recording():
    items = [emb("a", "r1", [1, 0]), emb("b", "r2", [1, 0]), emb("c", "r1", [1, 0])]
    links = link_speakers(items, .9)
    assert [(x.left_recording_id, x.right_recording_id) for x in links] == [("r1", "r2")]


def test_threshold_controls_candidates():
    assert link_speakers([emb("a", "r1", [1, 0]), emb("b", "r2", [0, 1])], .9) == []
