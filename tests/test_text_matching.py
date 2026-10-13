import pytest

from know_your_fan.text_matching import MAX_EXPECTED_NAME_LENGTH, match_name, normalize_tokens


def test_normalize_folds_accents_and_case():
    assert normalize_tokens("JOÃO Conceição-Gonçalves") == ["joao", "conceicao", "goncalves"]


def test_whole_words_only():
    # The legacy substring check accepted "Ana" inside "Mariana".
    result = match_name("Ana", "Name: Mariana Santana")
    assert not result.all_found
    assert result.missing_tokens == ("ana",)


def test_all_tokens_found_despite_lost_accents():
    result = match_name("João Simões Prado", "NAME: JOAO SIMOES PRADO\nDemo ID: KYF-DEMO-AAAA-BBBB")
    assert result.all_found
    assert result.coverage == 1.0


def test_partial_match_reports_missing_tokens():
    result = match_name("Paula Lima Barros", "Paula Lima")
    assert result.found_tokens == ("paula", "lima")
    assert result.missing_tokens == ("barros",)
    assert result.coverage == pytest.approx(2 / 3)


@pytest.mark.parametrize("bad", ["", "   ", "123 456", "---"])
def test_blank_or_non_alphabetic_names_are_rejected(bad):
    with pytest.raises(ValueError):
        match_name(bad, "anything")


def test_overlong_name_is_rejected():
    with pytest.raises(ValueError):
        match_name("a" * (MAX_EXPECTED_NAME_LENGTH + 1), "text")
