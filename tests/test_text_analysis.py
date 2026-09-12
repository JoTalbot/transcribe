from transcribe_intelligence.text_analysis import candidate_name_mentions, normalize_text, words


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  hello\n  world  ") == "hello world"


def test_words_handles_unicode():
    assert words("Привет, Сергей!") == ["Привет", "Сергей"]


def test_name_candidates_are_conservative():
    assert candidate_name_mentions("Сергей отправил договор") == ["Сергей"]
