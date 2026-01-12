from __future__ import annotations


from PACMAN.snippets import find_snippets, snippet_for_span


def test_snippet_for_span_includes_word_window():
    words = [f"w{i}" for i in range(1, 31)]
    words[15] = "TARGET"  # middle
    text = " ".join(words)

    start = text.index("TARGET")
    end = start + len("TARGET")

    snippet = snippet_for_span(text, start, end, words_before=10, words_after=10)
    assert snippet.split() == words[5:26]


def test_find_snippets_returns_match_snippet():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"
    snippets = find_snippets(text, "epsilon", max_snippets=2)
    assert snippets
    assert snippets[0].value == "epsilon"
    assert "epsilon" in snippets[0].snippet

