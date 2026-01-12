from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass(frozen=True)
class TextSnippet:
    value: str
    start: int
    end: int
    snippet: str


def _word_spans(text: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in _WORD_RE.finditer(text)]


def snippet_for_span(
    text: str,
    start: int,
    end: int,
    *,
    words_before: int = 10,
    words_after: int = 10,
) -> str:
    """
    Return a snippet containing the match at [start:end] with >=10 words before/after
    when available.
    """
    if not text:
        return ""

    spans = _word_spans(text)
    if not spans:
        return text[max(0, start - 120) : min(len(text), end + 120)].strip()

    # Find the word index that contains (or is closest before) the match start.
    match_word_idx = 0
    for i, (ws, we) in enumerate(spans):
        if ws <= start < we:
            match_word_idx = i
            break
        if we <= start:
            match_word_idx = i

    left_idx = max(0, match_word_idx - words_before)
    right_idx = min(len(spans) - 1, match_word_idx + words_after)

    snippet_start = spans[left_idx][0]
    snippet_end = spans[right_idx][1]
    return " ".join(text[snippet_start:snippet_end].split())


def find_snippets(
    text: str,
    value: str,
    *,
    case_insensitive: bool = True,
    max_snippets: int = 3,
    words_before: int = 10,
    words_after: int = 10,
) -> List[TextSnippet]:
    if not text or not value:
        return []

    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile(re.escape(value), flags)

    results: List[TextSnippet] = []
    for match in pattern.finditer(text):
        snip = snippet_for_span(
            text,
            match.start(),
            match.end(),
            words_before=words_before,
            words_after=words_after,
        )
        results.append(TextSnippet(value=value, start=match.start(), end=match.end(), snippet=snip))
        if len(results) >= max_snippets:
            break

    return results


def first_snippet(
    text: str,
    value: str,
    *,
    case_insensitive: bool = True,
    words_before: int = 10,
    words_after: int = 10,
) -> Optional[str]:
    snippets = find_snippets(
        text,
        value,
        case_insensitive=case_insensitive,
        max_snippets=1,
        words_before=words_before,
        words_after=words_after,
    )
    if not snippets:
        return None
    return snippets[0].snippet

