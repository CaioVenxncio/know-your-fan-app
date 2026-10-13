"""Metrics and statistics, checked against small hand-calculated examples."""

from __future__ import annotations

import pytest

from know_your_fan.research import metrics, stats
from know_your_fan.research.metrics import Confusion


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("kitten", "sitting", 3),  # classic: 2 substitutions + 1 insertion
        ("", "abc", 3),
        ("abc", "", 3),
        ("abc", "abc", 0),
        ("flaw", "lawn", 2),
        (["a", "b"], ["b"], 1),  # works on token sequences too
    ],
)
def test_levenshtein(a: str, b: str, expected: int) -> None:
    assert metrics.levenshtein(a, b) == expected


def test_transcript_normalization_collapses_whitespace_but_keeps_case_and_accents() -> None:
    assert metrics.normalize_transcript("  João\n\n  LIMA\t x ") == "João LIMA x"


def test_cer_hand_calculated() -> None:
    # reference "Ana Lima" (8 chars); hypothesis "Ana Lma" deletes one char -> 1/8
    counts = metrics.character_errors("Ana Lima", "Ana Lma")
    assert (counts.edits, counts.reference_length) == (1, 8)
    assert counts.rate == pytest.approx(0.125)


def test_cer_counts_accent_loss_as_one_error() -> None:
    assert metrics.character_errors("João", "Joao").edits == 1


def test_cer_line_breaks_are_not_errors() -> None:
    assert metrics.character_errors("Name: Ana\nCity: X", "Name: Ana City: X").edits == 0


def test_wer_hand_calculated() -> None:
    # 3 reference words; one substitution, one deletion -> 2/3
    counts = metrics.word_errors("Ana Lima Prado", "Ana Lina")
    assert (counts.edits, counts.reference_length) == (2, 3)


def test_empty_reference_gives_none_not_zero() -> None:
    assert metrics.character_errors("", "anything").rate is None
    assert metrics.ratio(1, 0) is None


def test_name_extraction_uses_the_name_line_only() -> None:
    text = "KNOW YOUR FAN\nName: Ana  Lima\nCity: Vila Aurora"
    assert metrics.extract_name_tokens(text) == ["ana", "lima"]
    assert metrics.extract_name_tokens("City: Ana Lima") == []


def test_name_token_counts_use_multisets() -> None:
    # expected Lima twice; OCR found it once plus a spurious token
    counts = metrics.name_token_counts("Ivo Lima Lima", "Name: Ivo Lima Xyz")
    assert (counts.true_positive, counts.extracted, counts.expected) == (2, 3, 3)
    assert counts.precision == pytest.approx(2 / 3)
    assert counts.recall == pytest.approx(2 / 3)
    assert counts.f1 == pytest.approx(2 / 3)


def test_name_token_counts_with_nothing_extracted() -> None:
    counts = metrics.name_token_counts("Ivo Lima", "")
    assert counts.precision is None  # nothing extracted: undefined, not 0
    assert counts.recall == 0.0
    assert counts.f1 == 0.0


def test_confusion_rates_and_denominators() -> None:
    c = Confusion()
    for actual, predicted in [(True, True), (True, False), (False, True), (False, False)] + [
        (False, False)
    ] * 2:
        c = c.add(actual=actual, predicted=predicted)
    assert (c.tp, c.fn, c.fp, c.tn) == (1, 1, 1, 3)
    assert c.far == pytest.approx(1 / 4)  # FP / negatives
    assert c.frr == pytest.approx(1 / 2)  # FN / positives
    assert c.precision == pytest.approx(1 / 2)
    assert c.recall == pytest.approx(1 / 2)
    assert c.f1 == pytest.approx(1 / 2)


def test_confusion_without_negatives_has_undefined_far() -> None:
    c = Confusion().add(actual=True, predicted=True)
    assert c.far is None
    assert c.frr == 0.0


# ------------------------------------------------------------------ bootstrap


def test_bootstrap_ratio_is_micro_average_and_deterministic() -> None:
    data = {"a": (1.0, 10.0), "b": (3.0, 10.0), "c": (0.0, 20.0)}
    first = stats.bootstrap_ratio(data, resamples=500, seed=7)
    second = stats.bootstrap_ratio(data, resamples=500, seed=7)
    assert first == second
    assert first.estimate == pytest.approx(4 / 40)
    assert first.low is not None
    assert first.high is not None
    assert first.estimate is not None
    assert first.low <= first.estimate <= first.high
    assert first.n_sources == 3


def test_bootstrap_of_constant_ratio_has_zero_width() -> None:
    interval = stats.bootstrap_ratio(dict.fromkeys("abcde", (1.0, 4.0)), resamples=200, seed=1)
    assert interval.low == interval.high == pytest.approx(0.25)


def test_bootstrap_resamples_sources_not_observations() -> None:
    # One source holds all errors; resampling sources gives a wide interval.
    data = {"bad": (50.0, 50.0), **{f"ok{i}": (0.0, 50.0) for i in range(9)}}
    interval = stats.bootstrap_ratio(data, resamples=2000, seed=3)
    assert interval.low is not None
    assert interval.high is not None
    assert interval.low == 0.0
    assert interval.high >= 0.25


def test_paired_difference_of_identical_arms_is_zero() -> None:
    data = {"a": (1.0, 5.0), "b": (2.0, 5.0)}
    interval = stats.bootstrap_paired_difference(data, data, resamples=300, seed=2)
    assert interval.estimate == 0.0
    assert interval.low == interval.high == 0.0


def test_paired_difference_uses_only_shared_sources() -> None:
    first = {"a": (2.0, 4.0), "b": (0.0, 4.0), "only_first": (4.0, 4.0)}
    second = {"a": (1.0, 4.0), "b": (0.0, 4.0)}
    interval = stats.bootstrap_paired_difference(first, second, resamples=300, seed=2)
    assert interval.n_sources == 2
    assert interval.estimate == pytest.approx(2 / 8 - 1 / 8)


def test_empty_and_zero_denominator_inputs() -> None:
    assert stats.bootstrap_ratio({}).estimate is None
    zero = stats.bootstrap_ratio({"a": (0.0, 0.0)}, resamples=50, seed=0)
    assert zero.estimate is None
    assert zero.resamples_used == 0
