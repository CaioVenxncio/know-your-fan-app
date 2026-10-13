"""Rendering-safety tests for the static HTML helpers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from know_your_fan import ui

SRC = Path(ui.__file__).resolve().parent
PAYLOAD = '<img src=x onerror="alert(1)"><script>alert(1)</script>'


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_markdown(body: str, *, unsafe_allow_html: bool = False) -> None:
        assert unsafe_allow_html
        calls.append(body)

    monkeypatch.setattr("know_your_fan.ui.st.markdown", fake_markdown)
    return calls


def test_monogram_renders_escaped_letters_only(rendered: list[str]) -> None:
    ui.monogram(PAYLOAD)
    ui.monogram("Ana <b>x</b> Lima")
    for body in rendered:
        assert "<script>" not in body
        assert "<img" not in body
        assert "<b>" not in body
    assert ">AL<" in rendered[1]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Ana Lima", "AL"), ("João Conceição Gonçalves", "JG"), ("Yuri", "Y"), ("", ""), ("123", "")],
)
def test_initials(name: str, expected: str) -> None:
    assert ui.initials(name) == expected


def test_step_number_accepts_integers_only(rendered: list[str]) -> None:
    ui.step_number(3)
    assert ">03<" in rendered[0]


def test_stylesheet_leaves_the_main_container_top_padding_to_streamlit() -> None:
    # Regression test for the clipped wordmark: overriding the main container's top
    # padding pushed content under Streamlit's fixed header whenever its toolbar had
    # items (as on Community Cloud). See docs/design-system.md, "Header clipping".
    css = ui._CSS.replace(" ", "")
    for selector in ("block-container", "stMainBlockContainer", "stAppViewBlockContainer"):
        for rule in css.split("}"):
            if selector in rule:
                assert "padding-top" not in rule, rule
                assert "margin-top:-" not in rule, rule


def test_raw_html_is_only_emitted_by_the_ui_module() -> None:
    # Any other module passing unsafe_allow_html=True would bypass the static-string
    # policy documented in ui.py and app.py.
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "ui.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "unsafe_allow_html":
                offenders.append(f"{path.relative_to(SRC)}:{node.value.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in {"html", "components"}:
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} st.{node.attr}")
    assert offenders == []
