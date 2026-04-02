from __future__ import annotations

import re

from rich.markup import escape

_STOP_WORDS = {
    "this", "that", "with", "from", "have", "been", "were", "they", "their",
    "what", "when", "where", "will", "would", "could", "should", "about",
    "into", "than", "then", "also", "more", "some", "over", "after", "your",
    "news", "says", "said", "just", "like", "make",
}


def extract_keywords(title: str, max_keywords: int = 0) -> list[str]:
    tokens = re.split(r"\W+", title.lower())
    seen: dict[str, None] = {}
    for t in tokens:
        if len(t) >= 4 and t not in _STOP_WORDS:
            seen[t] = None
    words = list(seen.keys())
    if max_keywords:
        words = sorted(words, key=len, reverse=True)[:max_keywords]
    return words


def highlight_keywords(text: str, keywords: list[str]) -> str:
    escaped = escape(text)
    if not keywords:
        return escaped
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f"[bold #ddb96a]{m.group(0)}[/bold #ddb96a]", escaped)
