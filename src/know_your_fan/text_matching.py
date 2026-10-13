"""Name-to-text matching for OCR output.

This only reports whether the words of an expected name appear in extracted
text. It says nothing about whether a document is authentic or who presented it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
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

    This is the original matching rule (M0 in the Phase 4 study): it ignores token
    order and repetition. It is kept unchanged as the research baseline and for
    word-level feedback; the application's decision uses :func:`match_name_sequence`.

    Raises ``ValueError`` for blank, overly long, or non-alphabetic names.
    """
    expected = _validated_tokens(expected_name)
    unique = tuple(dict.fromkeys(expected))
    available = set(normalize_tokens(extracted_text))
    found = tuple(t for t in unique if t in available)
    missing = tuple(t for t in unique if t not in available)
    return MatchResult(expected_tokens=unique, found_tokens=found, missing_tokens=missing)


def _validated_tokens(expected_name: str) -> list[str]:
    if len(expected_name) > MAX_EXPECTED_NAME_LENGTH:
        raise ValueError(f"Expected name must be at most {MAX_EXPECTED_NAME_LENGTH} characters.")
    tokens = normalize_tokens(expected_name)
    if not tokens:
        raise ValueError("Expected name must contain at least one letter.")
    return tokens


def line_tokens(text: str) -> list[list[str]]:
    """Normalized tokens of every non-empty line of ``text``."""
    return [tokens for line in text.splitlines() if (tokens := normalize_tokens(line))]


def contains_token_sequence(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """True if ``needle`` occurs as a contiguous run of whole tokens in ``haystack``."""
    n = len(needle)
    return any(list(haystack[i : i + n]) == list(needle) for i in range(len(haystack) - n + 1))


def sequence_on_one_line(expected_name: str, extracted_text: str) -> bool:
    """M1: the name's full token sequence (order and repeats) appears on one OCR line.

    Accents and case are folded; tokens are whole words, so "Ana" never matches
    inside "Mariana". Returns False for a name without letters.
    """
    expected = normalize_tokens(expected_name)
    return bool(expected) and any(
        contains_token_sequence(line, expected) for line in line_tokens(extracted_text)
    )


@dataclass(frozen=True, slots=True)
class SequenceMatch:
    """The application's matching result (M1 decision plus word-level feedback)."""

    matched: bool
    words: MatchResult

    @property
    def verdict(self) -> str:
        """``match``, ``words_not_in_sequence``, ``partial``, or ``none``."""
        if self.matched:
            return "match"
        if self.words.all_found:
            return "words_not_in_sequence"
        return "partial" if self.words.found_tokens else "none"


def match_name_sequence(expected_name: str, extracted_text: str) -> SequenceMatch:
    """Application matching rule, chosen from the Phase 4 study (docs/decisions/0007).

    A match requires the whole name, as an ordered sequence of words, on a single
    line of the extracted text. This is text matching, not identity verification.

    Raises ``ValueError`` for blank, overly long, or non-alphabetic names.
    """
    _validated_tokens(expected_name)
    return SequenceMatch(
        matched=sequence_on_one_line(expected_name, extracted_text),
        words=match_name(expected_name, extracted_text),
    )
