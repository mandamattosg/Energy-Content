from __future__ import annotations

import re
import unicodedata
from html import unescape


_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")
# Termos curtos (siglas como "ons", "epe", "ia") so casam como palavra inteira.
_SHORT_KEYWORD_LENGTH = 4


def strip_html(value: str) -> str:
    cleaned_value = _HTML_TAG_PATTERN.sub(" ", value)
    return unescape(cleaned_value)


def compact_whitespace(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def normalize_text(value: str) -> str:
    return compact_whitespace(strip_html(value))


def truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "…"


def fold_text(value: str) -> str:
    """Minusculas e sem acentos, para comparacao e matching."""
    decomposed = unicodedata.normalize("NFKD", normalize_text(value).lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    folded = fold_text(keyword)
    suffix = r"(?!\w)" if len(folded) <= _SHORT_KEYWORD_LENGTH else ""
    return re.compile(rf"(?<!\w){re.escape(folded)}{suffix}")


class KeywordMatcher:
    def __init__(self, keywords: list[str]) -> None:
        self._patterns = [(keyword, _keyword_pattern(keyword)) for keyword in keywords if keyword.strip()]

    def matches(self, text: str) -> list[str]:
        folded = fold_text(text)
        return [keyword for keyword, pattern in self._patterns if pattern.search(folded)]

    def any_match(self, text: str) -> bool:
        folded = fold_text(text)
        return any(pattern.search(folded) for _, pattern in self._patterns)
