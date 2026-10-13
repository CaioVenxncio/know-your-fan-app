from __future__ import annotations

import unicodedata

import pytest

from know_your_fan.text_matching import (
    MAX_EXPECTED_NAME_LENGTH,
    contains_token_sequence,
    line_tokens,
    match_name,
    match_name_sequence,
    normalize_tokens,
)


def test_normalize_folds_case_and_accents() -> None:
    assert normalize_tokens("JOÃO Conceição-Gonçalves") == ["joao", "conceicao", "goncalves"]


def test_composed_and_decomposed_unicode_are_equivalent() -> None:
    nfc = unicodedata.normalize("NFC", "Simões")
    nfd = unicodedata.normalize("NFD", "Simões")
    assert nfc != nfd
    assert match_name(nfc, f"Name: {nfd}").all_found


def test_case_insensitive_match() -> None:
    assert match_name("paula lima barros", "NAME: PAULA LIMA BARROS").all_found


def test_accents_lost_by_ocr_still_match() -> None:
    result = match_name("João Simões Prado", "NAME: JOAO SIMOES PRADO\nDemo ID: KYF-DEMO-AAAA-BBBB")
    assert result.all_found
    assert result.coverage == 1.0


@pytest.mark.parametrize(
    ("expected", "text"),
    [
        ("Ana", "Name: Mariana Santana"),  # legacy substring check accepted this
        ("Lima", "Name: Limaverde"),
        ("Rafael", "Rafaela"),
        ("Yuri", "Yurij"),
    ],
)
def test_false_positive_regressions_require_whole_words(expected: str, text: str) -> None:
    assert not match_name(expected, text).all_found


def test_compound_hyphenated_names_are_split_into_words() -> None:
    result = match_name("Ana Conceição-Gonçalves", "ANA CONCEICAO GONCALVES")
    assert result.all_found
    assert result.expected_tokens == ("ana", "conceicao", "goncalves")


def test_missing_tokens_are_reported_in_order() -> None:
    result = match_name("Paula Lima Barros", "Paula Lima")
    assert result.found_tokens == ("paula", "lima")
    assert result.missing_tokens == ("barros",)
    assert result.coverage == pytest.approx(2 / 3)


def test_extra_tokens_in_text_do_not_matter() -> None:
    assert match_name("Ana Lima", "KNOW YOUR FAN Name: Ana Lima City: Vila Aurora").all_found


def test_repeated_expected_tokens_are_counted_once() -> None:
    result = match_name("Lima Lima", "Lima")
    assert result.expected_tokens == ("lima",)
    assert result.all_found


def test_digits_and_punctuation_in_text_are_ignored() -> None:
    assert match_name("Ana Lima", "N4me: |Ana| _Lima_ 123").all_found


def test_nothing_found() -> None:
    result = match_name("Heitor", "")
    assert result.found_tokens == ()
    assert result.coverage == 0.0


@pytest.mark.parametrize("bad", ["", "   ", "123 456", "---", "😀😀", "_\t_"])
def test_blank_or_non_alphabetic_names_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="at least one letter"):
        match_name(bad, "anything")


def test_overlong_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="at most"):
        match_name("a" * (MAX_EXPECTED_NAME_LENGTH + 1), "text")


def test_name_at_length_limit_is_accepted() -> None:
    assert match_name("a" * MAX_EXPECTED_NAME_LENGTH, "a" * MAX_EXPECTED_NAME_LENGTH).all_found


# ------------------------------------------------------------------ Phase 5: M1 is the app rule


@pytest.mark.parametrize(
    ("true_name", "decoy"),
    [
        # The three test-split names behind all 33 of M0's false accepts in Phase 4.
        ("Tânia Tainá Rios Moraes", "Tânia Tânia Rios Moraes"),
        ("Rosimeire Telles Teles", "Rosimeire Telles Telles"),
        ("Edu Moura Mourão", "Edu Mourão Mourão"),
    ],
)
def test_m1_rejects_repeated_token_decoys_that_m0_accepted(true_name: str, decoy: str) -> None:
    card = f"KNOW YOUR FAN - FAN CARD\nName: {true_name}\nCity: Vila Aurora"
    assert match_name(decoy, card).all_found  # M0 (historical baseline) accepts
    result = match_name_sequence(decoy, card)
    assert not result.matched  # the application's rule rejects
    assert result.verdict == "words_not_in_sequence"
    assert match_name_sequence(true_name, card).matched


def test_m1_requires_order_and_a_single_line() -> None:
    assert not match_name_sequence("Lima Ana", "Name: Ana Lima").matched
    assert not match_name_sequence("Ana Lima", "Name: Ana\nLima").matched
    assert match_name_sequence("Ana Lima", "Name: Ana Lima\nCity: X").matched


def test_m1_whole_words_only() -> None:
    result = match_name_sequence("Ana", "Name: Mariana Santana")
    assert not result.matched
    assert result.verdict == "none"


def test_m1_folds_accents_case_and_punctuation() -> None:
    assert match_name_sequence("joão CONCEIÇÃO", "Name: JOAO Conceicao").matched
    assert match_name_sequence("Ana Conceição-Gonçalves", "Name: Ana Conceição Gonçalves").matched


def test_m1_compound_names_with_particles() -> None:
    card = "Name: Maria da Conceição Prado Lima"
    assert match_name_sequence("Maria da Conceição Prado Lima", card).matched
    assert match_name_sequence("Conceição Prado", card).matched  # contiguous part of the line
    assert not match_name_sequence("Maria Conceição", card).matched  # particle skipped


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("Name: Ana Lima Barros", "match"),
        ("Name: Barros Lima Ana", "words_not_in_sequence"),
        ("Name: Ana Lima", "partial"),
        ("Name: Ivo Prado", "none"),
        ("", "none"),
    ],
)
def test_sequence_match_verdicts(text: str, verdict: str) -> None:
    assert match_name_sequence("Ana Lima Barros", text).verdict == verdict


def test_sequence_match_reports_word_level_feedback() -> None:
    result = match_name_sequence("Ana Lima Barros", "Name: Ana Lima")
    assert result.words.found_tokens == ("ana", "lima")
    assert result.words.missing_tokens == ("barros",)


@pytest.mark.parametrize("bad", ["", "   ", "123", "a" * (MAX_EXPECTED_NAME_LENGTH + 1)])
def test_sequence_match_validates_input_like_the_baseline(bad: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - messages are covered by the baseline tests
        match_name_sequence(bad, "anything")


def test_line_tokens_and_contains_token_sequence() -> None:
    assert line_tokens("A b\n\n  \nC") == [["a", "b"], ["c"]]
    assert contains_token_sequence(["x", "a", "b", "y"], ["a", "b"])
    assert not contains_token_sequence(["a", "x", "b"], ["a", "b"])
    assert not contains_token_sequence(["a"], ["a", "b"])
