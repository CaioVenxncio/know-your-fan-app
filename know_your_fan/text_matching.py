"""Name-to-text matching for OCR output.

This only reports whether the words of an expected name appear in extracted
text. It says nothing about whether a document is authentic or who presented it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_EXPECTED_NAME_LENGTH = 100
_TOKEN_RE = re.compile(r"[^\W\d_]+")


def normalize_tokens(text: str) -> list[str]:
    """Split ``text`` into accent-folded, case-folded alphabetic tokens."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _TOKEN_RE.findall(stripped.casefold())


@dataclass(frozen=True, slots=True)
class MatchResult:
    expected_tokens: tuple[str, ...]
    found_tokens: tuple[str, ...]
    missing_tokens: tuple[str, ...]

    @property
    def all_found(self) -> bool:
        return not self.missing_tokens

    @property
    def coverage(self) -> float:
        return len(self.found_tokens) / len(self.expected_tokens)


def match_name(expected_name: str, extracted_text: str) -> MatchResult:
    """Check which whole-word tokens of ``expected_name`` occur in ``extracted_text``.

    Raises ``ValueError`` for blank, overly long, or non-alphabetic names.
    """
    if len(expected_name) > MAX_EXPECTED_NAME_LENGTH:
        raise ValueError(f"Expected name must be at most {MAX_EXPECTED_NAME_LENGTH} characters.")
    expected = tuple(dict.fromkeys(normalize_tokens(expected_name)))
    if not expected:
        raise ValueError("Expected name must contain at least one letter.")
    available = set(normalize_tokens(extracted_text))
    found = tuple(t for t in expected if t in available)
    missing = tuple(t for t in expected if t not in available)
    return MatchResult(expected_tokens=expected, found_tokens=found, missing_tokens=missing)
