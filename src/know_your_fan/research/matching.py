"""Name-matching strategies compared in the experiments.

All strategies answer one question: does the candidate name appear in the OCR
text? They are text-matching rules, not identity verification.

* **M0 (baseline):** the application's ``text_matching.match_name``: every
  distinct normalized token of the candidate appears somewhere in the text.
* **M1 (token-aware):** the candidate's full token sequence (order and
  repeats included) appears contiguously within a single OCR line.
* **M2 (error-tolerant, threshold tau):** like M1, but each token may differ by
  a normalized Levenshtein distance of at most ``tau``. ``tau = 0`` is
  exactly M1.
* **M3 (confusable-aware):** like M1, after mapping a fixed, pre-registered
  table of OCR look-alike characters to canonical forms on both sides.

Normalization for M0-M2 is the application's (NFKD accent folding,
case folding, alphabetic tokens only).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from know_your_fan.research.metrics import levenshtein
from know_your_fan.text_matching import (
    contains_token_sequence,
    line_tokens,
    match_name,
    normalize_tokens,
    sequence_on_one_line,
)

Matcher = Callable[[str, str], bool]

# Pre-registered look-alike table (generic OCR confusions, fixed before any
# experiment was run). Multi-character rules are applied first.
CONFUSABLE_SEQUENCES: tuple[tuple[str, str], ...] = (("rn", "m"), ("vv", "w"), ("cl", "d"))
CONFUSABLE_CHARACTERS: dict[str, str] = {
    "0": "o",
    "1": "l",
    "|": "l",
    "!": "l",
    "i": "l",
    "5": "s",
    "$": "s",
}
_M3_TOKEN = re.compile(r"[^\s.,;:()\[\]{}\-_/\\\"'`]+")


def m0_baseline(candidate: str, text: str) -> bool:
    return match_name(candidate, text).all_found


def m1_token_sequence(candidate: str, text: str) -> bool:
    """M1 delegates to the application's implementation (identical behaviour)."""
    return sequence_on_one_line(candidate, text)


def normalized_distance(a: str, b: str) -> float:
    """Levenshtein distance divided by the longer length (0 = equal, 1 = disjoint)."""
    longest = max(len(a), len(b))
    return 0.0 if longest == 0 else levenshtein(a, b) / longest


def m2_score(candidate: str, text: str) -> float:
    """Smallest, over all single-line windows, of the largest per-token distance.

    M2 accepts at threshold ``tau`` exactly when ``m2_score <= tau``, so one
    score per trial supports the whole threshold sweep. Returns 1.0 when the
    candidate has no tokens or no line has enough tokens.
    """
    expected = normalize_tokens(candidate)
    if not expected:
        return 1.0
    n = len(expected)
    best = 1.0
    for line in line_tokens(text):
        for start in range(len(line) - n + 1):
            worst = 0.0
            for e, w in zip(expected, line[start : start + n], strict=True):
                worst = max(worst, normalized_distance(e, w))
                if worst >= best:
                    break
            best = min(best, worst)
            if best == 0.0:
                return 0.0
    return best


def m2_tolerant(tau: float) -> Matcher:
    if not 0.0 <= tau < 1.0:
        raise ValueError("tau must be in [0, 1)")

    def match(candidate: str, text: str) -> bool:
        return bool(normalize_tokens(candidate)) and m2_score(candidate, text) <= tau

    return match


def canonicalize(token: str) -> str:
    """Fold accents and case, then apply the pre-registered look-alike table."""
    decomposed = unicodedata.normalize("NFKD", token)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    for sequence, replacement in CONFUSABLE_SEQUENCES:
        folded = folded.replace(sequence, replacement)
    return "".join(CONFUSABLE_CHARACTERS.get(ch, ch) for ch in folded)


def _m3_tokens(text: str) -> list[str]:
    return [canonicalize(t) for t in _M3_TOKEN.findall(text)]


def m3_confusable(candidate: str, text: str) -> bool:
    expected = _m3_tokens(candidate)
    if not expected:
        return False
    return any(
        contains_token_sequence(tokens, expected)
        for line in text.splitlines()
        if (tokens := _m3_tokens(line))
    )


def strategies(tau: float) -> dict[str, Matcher]:
    """The four strategies, with M2 at threshold ``tau``."""
    return {
        "M0_baseline": m0_baseline,
        "M1_token_sequence": m1_token_sequence,
        "M2_tolerant": m2_tolerant(tau),
        "M3_confusable": m3_confusable,
    }
