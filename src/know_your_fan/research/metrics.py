"""Evaluation metrics with explicit definitions and denominators.

Transcription text normalization (for CER and WER): Unicode NFC, every run of
whitespace (including line breaks) collapsed to one space, leading/trailing
whitespace removed. Case and diacritics are preserved: ``"João"`` vs ``"Joao"``
is one character error.

* **CER** = character edit distance / reference characters.
* **WER** = word edit distance / reference words (words = whitespace tokens).
* Aggregates are **micro** averages (sum of edits / sum of reference units)
  unless stated otherwise; per-sample (macro) values are kept for distributions.
* **Name-token P/R/F1** compare the multiset of tokens *extracted from the
  "Name:" line* of the OCR output with the ground-truth name tokens (app
  normalization). If no "Name" line is found, nothing is extracted.
* Zero denominators return ``None`` (reported as n/a), never 0 or 1.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from know_your_fan.text_matching import normalize_tokens

_WHITESPACE = re.compile(r"\s+")
_NAME_LABEL = re.compile(r"^\W*name\W*", re.IGNORECASE)


def levenshtein(a: Sequence[object], b: Sequence[object]) -> int:
    """Edit distance (insertions, deletions, substitutions; all cost 1)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (item_a != item_b))
            )
        previous = current
    return previous[-1]


def normalize_transcript(text: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


@dataclass(frozen=True, slots=True)
class EditCounts:
    edits: int
    reference_length: int

    @property
    def rate(self) -> float | None:
        return ratio(self.edits, self.reference_length)


def ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def character_errors(reference: str, hypothesis: str) -> EditCounts:
    ref, hyp = normalize_transcript(reference), normalize_transcript(hypothesis)
    return EditCounts(levenshtein(ref, hyp), len(ref))


def word_errors(reference: str, hypothesis: str) -> EditCounts:
    ref = normalize_transcript(reference).split()
    hyp = normalize_transcript(hypothesis).split()
    return EditCounts(levenshtein(ref, hyp), len(ref))


def extract_name_tokens(ocr_text: str) -> list[str]:
    """Normalized tokens after the first line that starts with a "Name" label."""
    for line in ocr_text.splitlines():
        stripped = unicodedata.normalize("NFKD", line)
        match = _NAME_LABEL.match(stripped)
        if match:
            return normalize_tokens(stripped[match.end() :])
    return []


@dataclass(frozen=True, slots=True)
class TokenCounts:
    true_positive: int
    extracted: int
    expected: int

    @property
    def precision(self) -> float | None:
        return ratio(self.true_positive, self.extracted)

    @property
    def recall(self) -> float | None:
        return ratio(self.true_positive, self.expected)

    @property
    def f1(self) -> float | None:
        return f1_from_counts(self.true_positive, self.extracted, self.expected)


def f1_from_counts(true_positive: int, predicted: int, actual: int) -> float | None:
    """F1 = 2TP / (predicted + actual); n/a when both are zero."""
    return ratio(2 * true_positive, predicted + actual)


def name_token_counts(expected_name: str, ocr_text: str) -> TokenCounts:
    expected = Counter(normalize_tokens(expected_name))
    extracted = Counter(extract_name_tokens(ocr_text))
    overlap = sum((expected & extracted).values())
    return TokenCounts(overlap, sum(extracted.values()), sum(expected.values()))


@dataclass(frozen=True, slots=True)
class Confusion:
    """Matching outcomes. Positive = the candidate is the specimen's true name."""

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, *, actual: bool, predicted: bool) -> Confusion:
        return Confusion(
            self.tp + (actual and predicted),
            self.fp + (not actual and predicted),
            self.tn + (not actual and not predicted),
            self.fn + (actual and not predicted),
        )

    @property
    def positives(self) -> int:
        return self.tp + self.fn

    @property
    def negatives(self) -> int:
        return self.fp + self.tn

    @property
    def far(self) -> float | None:
        """False acceptance rate = FP / (FP + TN), over negative trials."""
        return ratio(self.fp, self.negatives)

    @property
    def frr(self) -> float | None:
        """False rejection rate = FN / (TP + FN), over positive trials."""
        return ratio(self.fn, self.positives)

    @property
    def precision(self) -> float | None:
        return ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return ratio(self.tp, self.positives)

    @property
    def f1(self) -> float | None:
        return f1_from_counts(self.tp, self.tp + self.fp, self.positives)
