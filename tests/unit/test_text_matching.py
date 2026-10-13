from __future__ import annotations

import unicodedata

import pytest

from know_your_fan.text_matching import (
    MAX_EXPECTED_NAME_LENGTH,
    match_name,
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
