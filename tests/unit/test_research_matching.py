from __future__ import annotations

import pytest

from know_your_fan.research import matching
from know_your_fan.text_matching import match_name

CARD = "KNOW YOUR FAN - FAN CARD\nName: João Lima Lima\nCity: Vila Aurora\nDemo ID: KYF-DEMO-AAAA"


def test_m0_is_exactly_the_application_matcher() -> None:
    for candidate in ("João Lima", "Ivo Lima", "Lima João"):
        assert matching.m0_baseline(candidate, CARD) == match_name(candidate, CARD).all_found


def test_m0_ignores_order_and_repeats_while_m1_does_not() -> None:
    assert matching.m0_baseline("Lima João", CARD)  # tokens present anywhere
    assert not matching.m1_token_sequence("Lima João", CARD)  # wrong order
    assert matching.m1_token_sequence("João Lima Lima", CARD)
    assert matching.m0_baseline("João Lima", "Name: João Lima Lima")
    assert not matching.m1_token_sequence("João Lima Lima Lima", CARD)  # one repeat too many


def test_m1_requires_tokens_on_one_line() -> None:
    split_lines = "Name: João\nLima Lima"
    assert matching.m0_baseline("João Lima Lima", split_lines)
    assert not matching.m1_token_sequence("João Lima Lima", split_lines)


def test_m1_folds_accents_and_case() -> None:
    assert matching.m1_token_sequence("joao LIMA lima", CARD)


@pytest.mark.parametrize(
    ("candidate", "text", "expected"),
    [
        ("Ana Lima", "Name: Ana Lima", 0.0),
        ("Ana Lima", "Name: Ana Lina", 0.25),  # 1 edit / 4 letters
        ("Ana Lima", "Name: Ama Lina", 1 / 3),  # worst token: 1 edit / 3 letters
        ("Ana Lima", "Ana", 1.0),  # no window long enough
        ("Ana Lima", "Name: Ana", 0.75),  # the label forms a window: name/ana 3/4, ana/lima 3/4
        ("", "anything", 1.0),
    ],
)
def test_m2_score_hand_calculated(candidate: str, text: str, expected: float) -> None:
    assert matching.m2_score(candidate, text) == pytest.approx(expected)


def test_m2_threshold_controls_tolerance() -> None:
    text = "Name: Ana Lina"
    assert not matching.m2_tolerant(0.0)("Ana Lima", text)
    assert matching.m2_tolerant(0.25)("Ana Lima", text)


@pytest.mark.parametrize(
    "candidate", ["João Lima Lima", "Lima João", "Ivo Lima", "Vila Aurora", "joão lima", ""]
)
def test_m2_at_zero_tolerance_equals_m1(candidate: str) -> None:
    assert matching.m2_tolerant(0.0)(candidate, CARD) == matching.m1_token_sequence(candidate, CARD)


@pytest.mark.parametrize("tau", [-0.1, 1.0, 1.5])
def test_m2_rejects_invalid_thresholds(tau: float) -> None:
    with pytest.raises(ValueError, match="tau"):
        matching.m2_tolerant(tau)


@pytest.mark.parametrize(
    ("ocr_text", "expected"),
    [
        ("Name: J0ão Lima", True),  # digit zero for o
        ("Name: Joao 1ima", True),  # digit one for l
        ("Name: João Lirna", True),  # rn -> m: "Lirna" canonicalizes like "Lima"
        ("Name: João Lina", False),  # n/m is not in the table
        ("Name: Joao Iima", True),  # capital I for l
        ("Name: Joao Lama", False),  # not a look-alike substitution
    ],
)
def test_m3_confusable_table(ocr_text: str, expected: bool) -> None:
    assert matching.m3_confusable("João Lima", ocr_text) is expected


def test_m3_handles_rn_m_confusion() -> None:
    assert matching.m3_confusable("Moura", "Name: Rnoura")


def test_canonicalize_applies_both_tables() -> None:
    assert matching.canonicalize("Clóvis") == "dovls"
    assert matching.canonicalize("Rn0") == "mo"


def test_strategies_registry() -> None:
    registry = matching.strategies(0.25)
    assert set(registry) == {"M0_baseline", "M1_token_sequence", "M2_tolerant", "M3_confusable"}
    assert registry["M2_tolerant"]("Ana Lima", "Name: Ana Lina")
